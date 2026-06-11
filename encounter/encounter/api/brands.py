"""Brand import + browse endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..importer.pipeline import (
    ImportPipeline,
    make_http_downloader,
    make_http_fetcher,
)
from ..models import Brand, Product
from ..schemas import BrandOut, ImportRequest, ImportSummary, ProductOut

router = APIRouter(prefix="/brands", tags=["brands"])


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
    return pipeline.run(req.url, max_pages=req.max_pages)


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
    return pipeline.run(url, max_pages=max_pages)


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
