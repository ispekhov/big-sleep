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
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..embeddings import Embedder, get_embedder
from ..enums import ImageType, SourceType, VerificationStatus
from ..models import Brand, Image, Product, Source
from ..schemas import ImportSummary
from ..storage import ObjectStorage, get_storage
from ..vectorstore import VectorStore, get_vector_store
from .crawler import Crawler, FetchedPage, Fetcher
from .extractor import ExtractedProduct, extract_product

ImageDownloader = Callable[[str], "DownloadedImage | None"]


@dataclass
class DownloadedImage:
    url: str
    data: bytes
    content_type: str = "image/jpeg"


def _brand_name_from_site(start_url: str, homepage: FetchedPage | None) -> str:
    if homepage and homepage.html:
        soup = BeautifulSoup(homepage.html, "lxml")
        tag = soup.find("meta", property="og:site_name")
        if tag and tag.get("content"):
            return tag["content"].strip()
    host = urlparse(start_url).netloc.removeprefix("www.")
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

    def run(self, start_url: str, max_pages: int | None = None) -> ImportSummary:
        homepage = self.fetcher(start_url)
        brand_name = _brand_name_from_site(start_url, homepage)
        brand = self._get_or_create_brand(brand_name, start_url)
        source = self._get_or_create_source(brand_name, start_url)

        crawler = Crawler(self.fetcher, max_pages=max_pages)
        crawl = crawler.crawl(start_url)

        products_imported = 0
        images_imported = 0
        needs_review = 0

        for page in crawl.product_pages:
            extracted = extract_product(page.html, page.url)
            if extracted is None:
                continue
            product, n_images, flagged = self._persist_product(
                brand, source, extracted
            )
            if product is None:
                continue
            products_imported += 1
            images_imported += n_images
            needs_review += 1 if flagged else 0

        self.session.commit()
        return ImportSummary(
            brand=brand_name,
            products_imported=products_imported,
            images_imported=images_imported,
            products_need_review=needs_review,
            pages_crawled=crawl.pages_crawled,
        )

    # --- persistence ------------------------------------------------------
    def _get_or_create_brand(self, name: str, website: str) -> Brand:
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
        self, brand: Brand, source: Source, ex: ExtractedProduct
    ) -> tuple[Product | None, int, bool]:
        # Skip duplicates (same brand + product URL).
        if ex.product_url:
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

        n_images = 0
        cap = self.settings.crawl_max_images_per_product
        for img_url in ex.image_urls[:cap]:
            if self._persist_image(product, source, img_url):
                n_images += 1
        return product, n_images, flagged

    def _persist_image(self, product: Product, source: Source, img_url: str) -> bool:
        downloaded = self.downloader(img_url)
        if downloaded is None or not downloaded.data:
            return False
        try:
            vector = self.embedder.embed(downloaded.data)
        except Exception:
            return False

        digest = hashlib.sha256(downloaded.data).hexdigest()[:24]
        ext = ".jpg"
        key = f"products/{product.brand_id}/{product.id}/{digest}{ext}"
        public_url = self.storage.put(key, downloaded.data, downloaded.content_type)

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


# --- default httpx-backed factory ----------------------------------------
def make_http_fetcher() -> Fetcher:
    settings = get_settings()
    client = httpx.Client(
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.crawl_request_timeout,
        follow_redirects=True,
    )

    def fetch(url: str) -> FetchedPage | None:
        try:
            resp = client.get(url)
        except httpx.HTTPError:
            return None
        return FetchedPage(
            url=str(resp.url),
            status=resp.status_code,
            html=resp.text,
            content_type=resp.headers.get("content-type", "text/html"),
        )

    return fetch


def make_http_downloader() -> ImageDownloader:
    settings = get_settings()
    client = httpx.Client(
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.crawl_request_timeout,
        follow_redirects=True,
    )

    def download(url: str) -> DownloadedImage | None:
        try:
            resp = client.get(url)
        except httpx.HTTPError:
            return None
        if resp.status_code >= 400 or not resp.content:
            return None
        return DownloadedImage(
            url=url,
            data=resp.content,
            content_type=resp.headers.get("content-type", "image/jpeg"),
        )

    return download
