"""Orchestrates a full brand import and persists the results.

Network I/O is injected (``fetcher`` for HTML, ``downloader`` for image bytes)
so the whole pipeline can be exercised offline in tests. The default factory
wires up httpx-backed implementations.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..embeddings import Embedder, get_embedder
from ..enums import ImageType, SourceType, VerificationStatus
from ..models import Brand, Image, Product, Source, Variant
from ..schemas import ImportSummary
from ..storage import ObjectStorage, get_storage
from ..util import make_soup
from ..vectorstore import VectorStore, get_vector_store
from .crawler import Crawler, FetchedPage, Fetcher
from .extractor import ExtractedProduct, extract_product
from .firecrawl import (
    firecrawl_extract_all,
    firecrawl_import,
    get_firecrawl_client,
)
from .shopify import fetch_shopify_products

ImageDownloader = Callable[[str], "DownloadedImage | None"]


@dataclass
class DownloadedImage:
    url: str
    data: bytes
    content_type: str = "image/jpeg"


def _registrable_domain(url: str) -> str:
    """Normalised host used as a brand's stable identity (drops www + port)."""
    netloc = urlparse(url).netloc.lower()
    return netloc.split(":")[0].removeprefix("www.")


def _brand_name_from_site(start_url: str, homepage: FetchedPage | None) -> str:
    if homepage and homepage.html:
        soup = make_soup(homepage.html)
        tag = soup.find("meta", property="og:site_name")
        if tag and tag.get("content"):
            return tag["content"].strip()
    host = _registrable_domain(start_url)
    root = host.split(".")[0]
    return root.replace("-", " ").title()


class ImportPipeline:
    def __init__(
        self,
        session: Session,
        fetcher: Fetcher,
        downloader: ImageDownloader,
        *,
        embedder: Embedder | None = None,
        storage: ObjectStorage | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.session = session
        self.fetcher = fetcher
        self.downloader = downloader
        self.embedder = embedder or get_embedder()
        self.storage = storage or get_storage()
        self.vector_store = vector_store or get_vector_store()
        self.settings = get_settings()

    def run(
        self,
        start_url: str,
        max_pages: int | None = None,
        *,
        download_images: bool = True,
        product_limit: int | None = None,
    ) -> ImportSummary:
        homepage = self.fetcher(start_url)
        brand_name = _brand_name_from_site(start_url, homepage)
        brand = self._get_or_create_brand(brand_name, start_url)
        # Report the canonical brand name (which may differ from the per-page
        # og:site_name when we merged into an existing brand by domain).
        brand_name = brand.name
        source = self._get_or_create_source(brand_name, start_url)

        products_imported = 0
        images_imported = 0
        needs_review = 0
        cap = max_pages or self.settings.crawl_max_pages
        # No product cap by default — import the brand's FULL catalogue. A
        # limit is only applied if a caller explicitly passes one.
        plimit = product_limit

        # Pre-fetch this brand's existing product URLs once (in-memory dedup)
        # instead of a SELECT per product — critical for big catalogues.
        existing_urls: set[str] = set(
            self.session.scalars(
                select(Product.product_url).where(
                    Product.brand_id == brand.id,
                    Product.product_url.is_not(None),
                )
            ).all()
        )

        def _ingest(ex) -> None:
            nonlocal products_imported, images_imported, needs_review
            product, n_images, flagged = self._persist_product(
                brand, source, ex, download_images=download_images,
                existing_urls=existing_urls,
            )
            if product is None:
                return
            products_imported += 1
            images_imported += n_images
            needs_review += 1 if flagged else 0

        # Layer 1: Shopify products.json (clean, complete) when available.
        shopify = fetch_shopify_products(start_url, self.fetcher)
        if shopify:
            for ex in shopify[:plimit]:
                _ingest(ex)
            self.session.commit()
            return ImportSummary(
                brand=brand_name,
                products_imported=products_imported,
                images_imported=images_imported,
                products_need_review=needs_review,
                pages_crawled=0,
            )

        # Layers 2-3: crawl + structured-markup / HTML extraction.
        crawler = Crawler(self.fetcher, max_pages=cap)
        crawl = crawler.crawl(start_url)
        for page in crawl.product_pages:
            extracted = extract_product(page.html, page.url)
            if extracted is None:
                continue
            _ingest(extracted)

        # Layer 4: Firecrawl fallback for JS-rendered / WAF-blocked sites that
        # the free HTTP path couldn't read. Whole-site extract first (gets the
        # FULL catalogue of relic/custom sites in one job); fall back to
        # per-page scraping only if the extract job came back empty.
        used_firecrawl = False
        if products_imported == 0:
            client = get_firecrawl_client()
            if client is not None:
                used_firecrawl = True
                for ex in firecrawl_extract_all(start_url, client):
                    _ingest(ex)
                if products_imported == 0:
                    for ex in firecrawl_import(
                        start_url,
                        client,
                        max_products=self.settings.firecrawl_max_products,
                    ):
                        _ingest(ex)

        self.session.commit()
        return ImportSummary(
            brand=brand_name,
            products_imported=products_imported,
            images_imported=images_imported,
            products_need_review=needs_review,
            pages_crawled=crawl.pages_crawled,
            message=(
                "Ready for visual search (via Firecrawl)"
                if used_firecrawl
                else "Ready for visual search"
            ),
        )

    # --- persistence ------------------------------------------------------
    def _get_or_create_brand(self, name: str, website: str) -> Brand:
        # Identity is the registrable domain, not the (page-dependent) name —
        # so importing a brand's homepage and a deep shop URL like
        # ".../usa/shop/?per_page=-1" merge into ONE brand instead of splitting
        # into "Anglepoise" vs "Anglepoise USA".
        domain = _registrable_domain(website)
        # Require a "/" or "." right before the domain so "made.com" can't
        # match "handmade.com".
        brand = self.session.scalar(
            select(Brand).where(
                or_(
                    Brand.website.ilike(f"%/{domain}%"),
                    Brand.website.ilike(f"%.{domain}%"),
                )
            )
        )
        if brand is None:
            # Fall back to an exact name match for legacy rows with no/odd URLs.
            brand = self.session.scalar(select(Brand).where(Brand.name == name))
        if brand is None:
            brand = Brand(name=name, website=website)
            self.session.add(brand)
            self.session.flush()
        return brand

    def _get_or_create_source(self, name: str, url: str) -> Source:
        source = self.session.scalar(
            select(Source).where(Source.url == url, Source.type == SourceType.brand_site)
        )
        if source is None:
            source = Source(type=SourceType.brand_site, name=name, url=url)
            self.session.add(source)
            self.session.flush()
        return source

    def _persist_product(
        self,
        brand: Brand,
        source: Source,
        ex: ExtractedProduct,
        *,
        download_images: bool = True,
        existing_urls: set[str] | None = None,
    ) -> tuple[Product | None, int, bool]:
        # Skip duplicates (same brand + product URL) using the in-memory set
        # when available (avoids a DB round-trip per product).
        if ex.product_url:
            if existing_urls is not None:
                if ex.product_url in existing_urls:
                    return None, 0, False
                existing_urls.add(ex.product_url)
            else:
                existing = self.session.scalar(
                    select(Product).where(
                        Product.brand_id == brand.id,
                        Product.product_url == ex.product_url,
                    )
                )
                if existing is not None:
                    return None, 0, False

        flagged = not ex.required_present or ex.confidence < 0.4
        product = Product(
            brand_id=brand.id,
            source_id=source.id,
            name=ex.name,
            category=ex.category,
            collection=ex.collection,
            description=ex.description,
            materials=ex.materials,
            dimensions=ex.dimensions,
            price=ex.price,
            currency=ex.currency,
            sku=ex.sku,
            product_url=ex.product_url,
            needs_review=flagged,
            verification_status=(
                VerificationStatus.human_review
                if flagged
                else VerificationStatus.ai_validated
            ),
        )
        self.session.add(product)
        self.session.flush()

        for v in ex.variants[:25]:
            self.session.add(
                Variant(
                    product_id=product.id,
                    name=v.get("name") or "Default",
                    sku=v.get("sku"),
                    color=v.get("option"),
                    price=v.get("price"),
                )
            )

        n_images = 0
        cap = self.settings.crawl_max_images_per_product
        for img_url in ex.image_urls[:cap]:
            if self._persist_image(product, source, img_url, download_images):
                n_images += 1
        return product, n_images, flagged

    def _persist_image(
        self,
        product: Product,
        source: Source,
        img_url: str,
        download_images: bool = True,
    ) -> bool:
        # Deferred mode: record the image (URL only) now; a separate pass
        # downloads + embeds it. Lets bulk imports pull full catalogues fast.
        if not download_images:
            # No per-image flush — added rows commit in one batch with the run.
            self.session.add(
                Image(
                    product_id=product.id,
                    source_id=source.id,
                    image_url=img_url,
                    storage_key=None,
                    image_type=ImageType.official_product_image,
                    embedding=None,
                    verification_status=VerificationStatus.ai_validated,
                )
            )
            return True

        downloaded = self.downloader(img_url)
        if downloaded is None or not downloaded.data:
            return False
        try:
            vector = self.embedder.embed(downloaded.data)
        except Exception:
            return False

        digest = hashlib.sha256(downloaded.data).hexdigest()[:24]
        if self.settings.rehost_images:
            key = f"products/{product.brand_id}/{product.id}/{digest}.jpg"
            public_url = self.storage.put(
                key, downloaded.data, downloaded.content_type
            )
        else:
            # Reference the original brand/CDN URL — no storage round-trip.
            # Embeddings are still computed from the bytes we just fetched.
            key = None
            public_url = img_url

        image = Image(
            product_id=product.id,
            source_id=source.id,
            image_url=public_url,
            storage_key=key,
            image_type=ImageType.official_product_image,
            embedding=[float(x) for x in vector.tolist()],
            embedding_model=self.embedder.name,
            verification_status=VerificationStatus.ai_validated,
        )
        self.session.add(image)
        self.session.flush()

        self.vector_store.upsert(
            image.id,
            vector,
            {
                "product_id": product.id,
                "brand_id": product.brand_id,
                "image_type": image.image_type.value,
            },
        )
        return True


# --- default browser-impersonating factory -------------------------------
# Prefer curl_cffi (impersonates Chrome's TLS/JA3 + HTTP-2 fingerprint, which
# defeats fingerprint-based WAFs) and fall back to httpx where unavailable.
def _browser_get():
    settings = get_settings()
    try:
        from curl_cffi import requests as creq

        session = creq.Session(
            impersonate="chrome",
            timeout=settings.crawl_request_timeout,
            allow_redirects=True,
        )

        def get(url: str):
            return session.get(url)

        return get
    except Exception:
        client = httpx.Client(
            headers={"User-Agent": settings.crawl_user_agent},
            timeout=settings.crawl_request_timeout,
            follow_redirects=True,
        )

        def get(url: str):
            return client.get(url)

        return get


def make_http_fetcher() -> Fetcher:
    get = _browser_get()

    def fetch(url: str) -> FetchedPage | None:
        try:
            resp = get(url)
        except Exception:
            return None
        return FetchedPage(
            url=str(resp.url),
            status=resp.status_code,
            html=resp.text,
            content_type=resp.headers.get("content-type", "text/html"),
        )

    return fetch


def make_http_downloader() -> ImageDownloader:
    get = _browser_get()

    def download(url: str) -> DownloadedImage | None:
        try:
            resp = get(url)
        except Exception:
            return None
        if resp.status_code >= 400 or not resp.content:
            return None
        return DownloadedImage(
            url=url,
            data=resp.content,
            content_type=resp.headers.get("content-type", "image/jpeg"),
        )

    return download
