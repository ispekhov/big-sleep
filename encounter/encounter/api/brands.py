"""Brand import + browse endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..importer.pipeline import (
    ImportPipeline,
    make_http_downloader,
    make_http_fetcher,
)
from ..models import Brand, BrandQueue, Product
from ..schemas import BrandOut, ImportRequest, ImportSummary, ProductOut

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("/queue")
def queue_status(session: Session = Depends(get_session)) -> dict:
    """Batch queue overview: per-brand status + rollup counts."""
    from collections import Counter

    rows = list(session.scalars(select(BrandQueue).order_by(BrandQueue.id)).all())
    counts = Counter(r.status for r in rows)
    total_products = sum(r.products_imported for r in rows)
    return {
        "total_brands": len(rows),
        "counts": dict(counts),
        "total_products_imported": total_products,
        "brands": [
            {
                "id": r.id,
                "name": r.name,
                "url": r.url,
                "status": r.status,
                "classification": r.classification,
                "products": r.products_imported,
                "images": r.images_imported,
                "attempts": r.attempts,
                "error": r.error,
            }
            for r in rows
        ],
    }


@router.get("/queue/run")
def queue_run(
    budget_seconds: int = 40,
    max_pages: int = 10,
    session: Session = Depends(get_session),
) -> dict:
    """Process pending queued brands for up to ``budget_seconds`` (one job each).

    Safe to call concurrently: brands are claimed with ``FOR UPDATE SKIP
    LOCKED`` so parallel workers never grab the same brand. Stale ``running``
    rows (a worker that exceeded the time limit) are recycled, then parked as
    ``failed_timeout`` after 3 attempts so the batch always makes progress.
    """
    import time

    from sqlalchemy import text

    is_pg = session.bind.dialect.name == "postgresql"

    # Recycle brands left 'running' by a worker that hit the serverless limit.
    if is_pg:
        try:
            session.execute(
                text(
                    "update brand_queue set status = case when attempts >= 3 "
                    "then 'failed_timeout' else 'pending' end, updated_at = now() "
                    "where status = 'running' "
                    # Above the Firecrawl whole-site wait (~220s) and the
                    # function ceiling (300s) so a long extract job isn't
                    # recycled out from under a still-running worker.
                    "and updated_at < now() - interval '290 seconds'"
                )
            )
            session.commit()
        except Exception:
            session.rollback()

    deadline = time.monotonic() + budget_seconds
    processed = []
    while time.monotonic() < deadline:
        stmt = (
            select(BrandQueue)
            .where(BrandQueue.status == "pending")
            .order_by(BrandQueue.id)
            .limit(1)
        )
        if is_pg:
            stmt = stmt.with_for_update(skip_locked=True)
        row = session.scalar(stmt)
        if row is None:
            break
        row.status = "running"
        row.attempts += 1
        session.commit()  # release the row lock; 'running' now guards it

        try:
            pipeline = ImportPipeline(
                session,
                fetcher=make_http_fetcher(),
                downloader=make_http_downloader(),
            )
            # Bulk mode: pull the full catalogue (metadata) fast and defer
            # image download/embedding to the /queue/embed worker.
            summary = pipeline.run(
                row.url, max_pages=max_pages, download_images=False
            )
            row.products_imported = summary.products_imported
            row.images_imported = summary.images_imported
            if "Firecrawl" in (summary.message or ""):
                row.classification = "firecrawl"
            elif summary.pages_crawled == 0 and summary.products_imported:
                row.classification = "shopify"
            else:
                row.classification = "http"
            row.status = "done" if summary.products_imported > 0 else "empty"
            if not row.name and summary.brand:
                row.name = summary.brand
        except Exception as exc:  # noqa: BLE001
            row.status = "failed"
            row.error = str(exc)[:300]
        session.commit()
        processed.append(
            {
                "name": row.name,
                "status": row.status,
                "products": row.products_imported,
            }
        )

    # Self-perpetuate: if work remains, trigger one successor so the queue
    # drains autonomously without an external driver.
    remaining = session.scalar(
        select(BrandQueue).where(BrandQueue.status == "pending").limit(1)
    )
    if remaining is not None:
        _kick_self(1)
    return {"processed": len(processed), "items": processed}


def _kick_self(n: int) -> int:
    """Fire-and-forget GETs to our own queue/run to chain the next batch(es).

    Each request reaches Vercel and starts a fresh 60s worker; we don't wait
    for the response (short read timeout), so this returns almost immediately.
    """
    base = get_settings().self_base_url
    if not base:
        return 0
    import httpx

    sent = 0
    for _ in range(n):
        try:
            httpx.get(
                f"{base}/brands/queue/run?budget_seconds=55&max_pages=10",
                timeout=httpx.Timeout(5.0, read=1.0),
            )
        except Exception:
            pass
        sent += 1  # the worker was triggered even though we time out the read
    return sent


@router.get("/queue/kick")
def queue_kick(n: int = 5) -> dict:
    """Start the autonomous batch engine with ``n`` self-sustaining workers."""
    return {"kicked": _kick_self(n)}


@router.get("/queue/embed")
def queue_embed(
    n: int = 40, session: Session = Depends(get_session)
) -> dict:
    """Download + embed a batch of pending product images (the deferred pass).

    Picks images with no embedding yet, fetches the bytes (Chrome-impersonating
    client), embeds them, and indexes them for visual search. Failed downloads
    are marked so they aren't retried forever.
    """
    from ..embeddings import get_embedder
    from ..enums import ImageType
    from ..importer.pipeline import make_http_downloader
    from ..models import Image
    from ..vectorstore import get_vector_store

    embedder = get_embedder()
    store = get_vector_store()
    download = make_http_downloader()

    rows = list(
        session.scalars(
            select(Image)
            .where(
                Image.embedding.is_(None),
                Image.embedding_model.is_(None),
                Image.product_id.is_not(None),
                Image.image_type == ImageType.official_product_image,
            )
            .limit(n)
        ).all()
    )
    embedded = 0
    for img in rows:
        downloaded = download(img.image_url)
        if downloaded is None or not downloaded.data:
            img.embedding_model = "failed"  # don't retry forever
            continue
        try:
            vector = embedder.embed(downloaded.data)
        except Exception:  # noqa: BLE001
            img.embedding_model = "failed"
            continue
        img.embedding = [float(x) for x in vector.tolist()]
        img.embedding_model = embedder.name
        session.flush()
        store.upsert(
            img.id,
            vector,
            {"product_id": img.product_id, "image_type": img.image_type.value},
        )
        embedded += 1
    session.commit()
    return {"candidates": len(rows), "embedded": embedded}


@router.get("/diagnose")
def diagnose_brand(url: str) -> dict:
    """Classify how (and whether) a brand site can be auto-imported.

    Used by the batch pipeline to triage a list of brands into: works via the
    Shopify API, works via structured markup, or needs the headless renderer /
    a per-brand adapter. Cheap: a homepage fetch, a products.json probe, and a
    tiny crawl.
    """
    from ..importer.crawler import Crawler
    from ..importer.extractor import extract_product
    from ..importer.shopify import fetch_shopify_products
    from ..util import make_soup

    fetcher = make_http_fetcher()
    home = fetcher(url)
    if home is None or home.status >= 400:
        return {
            "url": url,
            "home_status": home.status if home else None,
            "classification": "blocked_or_unreachable",
        }

    html = home.html
    shopify = fetch_shopify_products(url, fetcher, max_pages=1)
    has_jsonld_product = "ld+json" in html and '"Product"' in html
    has_og = "og:type" in html or "og:image" in html

    crawler = Crawler(fetcher, max_pages=4)
    crawl = crawler.crawl(url)
    extractable = sum(
        1 for p in crawl.product_pages[:4] if extract_product(p.html, p.url)
    )

    if shopify:
        cls = "shopify_ok"
    elif extractable:
        cls = "structured_ok"
    elif has_jsonld_product:
        cls = "structured_maybe"
    else:
        cls = "needs_headless_or_custom"

    return {
        "url": url,
        "home_status": home.status,
        "home_bytes": len(html),
        "shopify_products": len(shopify) if shopify else 0,
        "has_jsonld_product": has_jsonld_product,
        "has_opengraph": has_og,
        "pages_crawled": crawl.pages_crawled,
        "product_pages_found": len(crawl.product_pages),
        "extractable_sample": extractable,
        "classification": cls,
    }


@router.get("/extract-test")
def extract_test(url: str) -> dict:
    """Temporary: start a whole-site Firecrawl extract job; returns the id."""
    from ..importer.firecrawl import get_firecrawl_client

    client = get_firecrawl_client()
    if client is None:
        return {"configured": False}
    return {"job_id": client.start_extract(url)}


@router.get("/extract-poll")
def extract_poll(id: str) -> dict:
    """Temporary: poll an extract job and show how many products it found."""
    from ..importer.firecrawl import get_firecrawl_client

    client = get_firecrawl_client()
    if client is None:
        return {"configured": False}
    status, products = client.poll_extract(id)
    return {
        "status": status,
        "count": len(products),
        "sample": [
            {"name": p.name, "price": p.price, "images": len(p.image_urls)}
            for p in products[:8]
        ],
    }


@router.get("/firecrawl-test")
def firecrawl_test(url: str) -> dict:
    """Temporary: validate Firecrawl connectivity via a fast map() call."""
    from ..importer.firecrawl import get_firecrawl_client, looks_like_product_url

    client = get_firecrawl_client()
    if client is None:
        return {"configured": False, "hint": "firecrawl key not found"}
    urls = client.map_urls(url)
    product_urls = [u for u in urls if looks_like_product_url(u)]
    return {
        "configured": True,
        "mapped_urls": len(urls),
        "product_urls_found": len(product_urls),
        "product_urls_sample": product_urls[:12],
    }


@router.post("/import", response_model=ImportSummary)
def import_brand(
    req: ImportRequest, session: Session = Depends(get_session)
) -> ImportSummary:
    """Crawl a brand website and import its product catalogue.

    Example: ``{"url": "https://www.tomdixon.net"}`` ->
    ``427 products imported, 3842 images imported, 46 need review``.
    """
    pipeline = ImportPipeline(
        session, fetcher=make_http_fetcher(), downloader=make_http_downloader()
    )
    # Defer image download/embedding so the (60s) request returns fast with the
    # full product list; the /queue/embed worker fills in images afterward.
    return pipeline.run(
        req.url, max_pages=req.max_pages or 80, download_images=False
    )


@router.get("/import-progress")
def import_progress(
    url: str, session: Session = Depends(get_session)
) -> dict:
    """Live counts for the brand at ``url`` — drives the import progress ticker.

    The importer commits products in small batches, so polling this while an
    import runs shows the catalogue filling up in real time.
    """
    from sqlalchemy import func, or_

    from ..importer.pipeline import _registrable_domain
    from ..models import Image

    domain = _registrable_domain(url)
    brand_ids = list(
        session.scalars(
            select(Brand.id).where(
                or_(
                    Brand.website.ilike(f"%/{domain}%"),
                    Brand.website.ilike(f"%.{domain}%"),
                )
            )
        ).all()
    )
    if not brand_ids:
        return {"domain": domain, "products": 0, "images": 0, "needs_review": 0}
    products = (
        session.scalar(
            select(func.count(Product.id)).where(
                Product.brand_id.in_(brand_ids), Product.deleted_at.is_(None)
            )
        )
        or 0
    )
    flagged = (
        session.scalar(
            select(func.count(Product.id)).where(
                Product.brand_id.in_(brand_ids), Product.needs_review.is_(True)
            )
        )
        or 0
    )
    images = (
        session.scalar(
            select(func.count(Image.id))
            .select_from(Image)
            .join(Product, Product.id == Image.product_id)
            .where(Product.brand_id.in_(brand_ids))
        )
        or 0
    )
    return {
        "domain": domain,
        "products": int(products),
        "images": int(images),
        "needs_review": int(flagged),
    }


@router.get("/import", response_model=ImportSummary)
def import_brand_get(
    url: str,
    max_pages: int | None = None,
    session: Session = Depends(get_session),
) -> ImportSummary:
    """GET convenience for importing a single brand (handy for batch runs)."""
    pipeline = ImportPipeline(
        session, fetcher=make_http_fetcher(), downloader=make_http_downloader()
    )
    return pipeline.run(
        url, max_pages=max_pages or 80, download_images=False
    )


@router.post("/normalize-names")
def normalize_names(
    brand_id: int | None = None, session: Session = Depends(get_session)
) -> dict:
    """Recompute precise product names from URL handles for existing products.

    Generic storefront titles ("Cloud") become specific ("Cloud Pendant 14\"").
    Renames in place; idempotent. ``brand_id`` scopes to one brand (the pilot);
    omit it to normalise every brand.
    """
    from ..importer.naming import derive_product_name

    stmt = select(Product)
    if brand_id is not None:
        stmt = stmt.where(Product.brand_id == brand_id)
    prods = list(session.scalars(stmt).all())
    renamed = 0
    for p in prods:
        new = derive_product_name(p.name, p.product_url)
        if new and new != p.name:
            p.name = new
            renamed += 1
    session.commit()
    return {"scope": brand_id or "all", "products": len(prods), "renamed": renamed}


@router.get("/overview")
def brands_overview(session: Session = Depends(get_session)) -> list[dict]:
    """Per-brand rollup for the by-brand catalogue view: product count,
    how many are flagged for review, and a sample thumbnail. Sorted by size."""
    from sqlalchemy import case, func

    from ..models import Image

    sample = (
        select(Image.image_url)
        .join(Product, Product.id == Image.product_id)
        .where(
            Product.brand_id == Brand.id,
            Product.deleted_at.is_(None),
            Image.image_url.is_not(None),
        )
        .order_by(Image.id)
        .limit(1)
        .correlate(Brand)
        .scalar_subquery()
    )
    flagged = func.coalesce(
        func.sum(case((Product.needs_review.is_(True), 1), else_=0)), 0
    )
    stmt = (
        select(
            Brand.id,
            Brand.name,
            Brand.website,
            func.count(Product.id).label("products"),
            flagged.label("needs_review"),
            sample.label("sample"),
        )
        .join(
            Product,
            (Product.brand_id == Brand.id) & (Product.deleted_at.is_(None)),
            isouter=True,
        )
        .group_by(Brand.id, Brand.name, Brand.website)
        .having(func.count(Product.id) > 0)
        .order_by(func.count(Product.id).desc())
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "website": r.website,
            "products": int(r.products),
            "needs_review": int(r.needs_review),
            "sample": r.sample,
        }
        for r in session.execute(stmt).all()
    ]


@router.get("", response_model=list[BrandOut])
def list_brands(session: Session = Depends(get_session)) -> list[Brand]:
    return list(session.scalars(select(Brand).order_by(Brand.name)).all())


@router.get("/{brand_id}", response_model=BrandOut)
def get_brand(brand_id: int, session: Session = Depends(get_session)) -> Brand:
    brand = session.get(Brand, brand_id)
    if brand is None:
        raise HTTPException(404, "Brand not found")
    return brand


@router.get("/{brand_id}/products", response_model=list[ProductOut])
def brand_products(
    brand_id: int, session: Session = Depends(get_session)
) -> list[Product]:
    if session.get(Brand, brand_id) is None:
        raise HTTPException(404, "Brand not found")
    stmt = (
        select(Product)
        .where(Product.brand_id == brand_id)
        .options(
            selectinload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.variants),
        )
        .order_by(Product.name)
    )
    return list(session.scalars(stmt).all())
