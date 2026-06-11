"""Extract structured product records from a product HTML page.

Strategy, in priority order:
  1. schema.org JSON-LD ``Product`` (most reliable, used by most brand sites).
  2. OpenGraph / Twitter meta tags (``og:type=product``, ``og:image`` …).
  3. Heuristic fallback (``<h1>``, meta description, price regex).

The extractor is deliberately tolerant: design-brand sites are inconsistent,
so we collect whatever we can and let the pipeline flag low-confidence
records for human review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..util import make_soup

_PRODUCT_URL_HINTS = ("/product", "/products/", "/shop/", "/p/", "/item/")
_PRICE_RE = re.compile(r"([£$€])\s?([\d.,]+)")
_CURRENCY_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR"}
_DIM_RE = re.compile(
    r"(?:dimensions?|size|measures?)\s*[:\-]?\s*([^\n.;]{3,80})", re.I
)
_MATERIAL_RE = re.compile(r"(?:materials?|made (?:of|from))\s*[:\-]?\s*([^\n.;]{3,80})", re.I)


@dataclass
class ExtractedProduct:
    name: str | None = None
    category: str | None = None
    collection: str | None = None
    description: str | None = None
    materials: str | None = None
    dimensions: str | None = None
    price: float | None = None
    currency: str | None = None
    sku: str | None = None
    product_url: str | None = None
    image_urls: list[str] = field(default_factory=list)
    variants: list[dict] = field(default_factory=list)

    @property
    def required_present(self) -> bool:
        """Spec's required fields that we can realistically auto-extract."""
        return bool(self.name and self.image_urls and self.price is not None)

    @property
    def confidence(self) -> float:
        fields = [
            self.name, self.category, self.description, self.materials,
            self.dimensions, self.price, self.sku,
        ]
        present = sum(1 for f in fields if f) + (1 if self.image_urls else 0)
        return round(present / (len(fields) + 1), 3)


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict):
            # Some sites nest under @graph.
            if "@graph" in data and isinstance(data["@graph"], list):
                yield from data["@graph"]
            else:
                yield data


def _is_product_type(node: dict) -> bool:
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(str(x).lower() == "product" for x in types if x)


def _parse_price(value) -> tuple[float | None, str | None]:
    if value is None:
        return None, None
    try:
        return float(str(value).replace(",", "")), None
    except (ValueError, TypeError):
        m = _PRICE_RE.search(str(value))
        if m:
            return float(m.group(2).replace(",", "")), _CURRENCY_SYMBOLS.get(m.group(1))
    return None, None


def looks_like_product_page(url: str, html: str | None = None) -> bool:
    """Cheap pre-filter used by the crawler to prioritise product pages."""
    if any(h in url.lower() for h in _PRODUCT_URL_HINTS):
        return True
    if html and 'application/ld+json' in html and '"Product"' in html:
        return True
    if html and 'property="og:type"' in html and 'product' in html.lower():
        return True
    return False


def extract_product(html: str, url: str) -> ExtractedProduct | None:
    """Return an ExtractedProduct if ``html`` looks like a product page."""
    soup = make_soup(html)
    product = ExtractedProduct(product_url=url)

    # 1) JSON-LD Product
    jsonld = None
    for node in _iter_jsonld(soup):
        if isinstance(node, dict) and _is_product_type(node):
            jsonld = node
            break

    if jsonld:
        product.name = _clean(jsonld.get("name"))
        product.description = _clean(jsonld.get("description"))
        product.sku = _clean(jsonld.get("sku") or jsonld.get("mpn"))
        product.category = _clean(jsonld.get("category"))
        brand = jsonld.get("brand")
        if isinstance(brand, dict):
            product.collection = _clean(brand.get("name")) or product.collection
        product.image_urls = _collect_images(jsonld.get("image"), url)
        offers = jsonld.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            price, _ = _parse_price(offers.get("price"))
            product.price = price
            product.currency = _clean(offers.get("priceCurrency")) or product.currency
        if isinstance(jsonld.get("material"), str):
            product.materials = _clean(jsonld.get("material"))

    # 1b) schema.org microdata (itemtype Product) backfill
    if not (product.name and product.image_urls):
        micro = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)})
        if micro is not None:
            if not product.name:
                nm = micro.find(attrs={"itemprop": "name"})
                product.name = _clean(nm.get_text() if nm else None)
            if not product.image_urls:
                urls = []
                for im in micro.find_all(attrs={"itemprop": "image"}):
                    src = im.get("content") or im.get("src") or im.get("href")
                    if src:
                        urls.append(urljoin(url, src))
                product.image_urls = urls
            if product.price is None:
                pr = micro.find(attrs={"itemprop": "price"})
                if pr is not None:
                    price, _ = _parse_price(pr.get("content") or pr.get_text())
                    product.price = price

    # 2) OpenGraph backfill
    if not product.name:
        product.name = _meta(soup, "og:title") or _text(soup, "h1")
    if not product.description:
        product.description = (
            _meta(soup, "og:description") or _meta_name(soup, "description")
        )
    if not product.image_urls:
        og_image = _meta(soup, "og:image")
        if og_image:
            product.image_urls = [urljoin(url, og_image)]
    if product.price is None:
        og_amount = _meta(soup, "product:price:amount") or _meta(
            soup, "og:price:amount"
        )
        price, _ = _parse_price(og_amount)
        product.price = price
        product.currency = product.currency or _meta(
            soup, "product:price:currency"
        )

    # 3) Heuristic backfill for the harder fields
    page_text = soup.get_text(" ", strip=True)
    if product.price is None:
        m = _PRICE_RE.search(page_text)
        if m:
            product.price = float(m.group(2).replace(",", ""))
            product.currency = product.currency or _CURRENCY_SYMBOLS.get(m.group(1))
    if not product.materials:
        m = _MATERIAL_RE.search(page_text)
        if m:
            product.materials = _clean(m.group(1))
    if not product.dimensions:
        m = _DIM_RE.search(page_text)
        if m:
            product.dimensions = _clean(m.group(1))

    # 3b) Last-resort image scrape — only on pages that already look like a
    # real product detail page (have a name + a price), so listing/category
    # pages don't turn into junk products.
    if product.name and product.price is not None and not product.image_urls:
        product.image_urls = _scrape_images(soup, url)

    # Only return something if we have at least a name + an image.
    if product.name and product.image_urls:
        # de-dup images, cap handled by pipeline
        seen: set[str] = set()
        product.image_urls = [
            u for u in product.image_urls if not (u in seen or seen.add(u))
        ]
        return product
    return None


# --- small helpers --------------------------------------------------------
def _clean(value) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _collect_images(value, base_url: str) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        urls = [value]
    elif isinstance(value, list):
        for v in value:
            if isinstance(v, str):
                urls.append(v)
            elif isinstance(v, dict) and v.get("url"):
                urls.append(v["url"])
    elif isinstance(value, dict) and value.get("url"):
        urls = [value["url"]]
    return [urljoin(base_url, u) for u in urls if u]


_IMG_SKIP = re.compile(
    r"(sprite|logo|icon|favicon|placeholder|loader|spinner|pixel|blank|\.svg)",
    re.I,
)


def _scrape_images(soup: BeautifulSoup, base_url: str, cap: int = 8) -> list[str]:
    """Collect plausible product images from <img> tags (src/data-src/srcset)."""
    urls: list[str] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-srcset", "").split(" ")[0]
            or img.get("srcset", "").split(" ")[0]
        )
        if not src or src.startswith("data:"):
            continue
        if _IMG_SKIP.search(src):
            continue
        full = urljoin(base_url, src.strip())
        if full not in seen:
            seen.add(full)
            urls.append(full)
        if len(urls) >= cap:
            break
    return urls


def _meta(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", property=prop)
    return _clean(tag.get("content")) if tag else None


def _meta_name(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": name})
    return _clean(tag.get("content")) if tag else None


def _text(soup: BeautifulSoup, selector: str) -> str | None:
    tag = soup.find(selector)
    return _clean(tag.get_text()) if tag else None
