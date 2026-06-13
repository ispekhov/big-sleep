"""Platform adapter: Shopify ``/products.json`` (and BigCommerce/Woo hints).

Standard Shopify stores expose a clean, paginated product feed at
``/products.json`` — title, body, type, variants (price/sku/options), and
images. When available this is the fastest, most complete source and avoids
crawling/parsing HTML entirely.

Returns ``None`` when the endpoint is absent (e.g. headless storefronts), so
the pipeline falls back to crawl-based extraction.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from .extractor import ExtractedProduct
from .naming import derive_product_name

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = _TAG_RE.sub(" ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _to_product(node: dict, base: str) -> ExtractedProduct:
    handle = node.get("handle")
    variants = node.get("variants") or []
    images = [
        img.get("src")
        for img in (node.get("images") or [])
        if isinstance(img, dict) and img.get("src")
    ]
    price = None
    sku = None
    if variants:
        first = variants[0]
        try:
            price = float(first.get("price"))
        except (TypeError, ValueError):
            price = None
        sku = first.get("sku") or None

    variant_rows = []
    for v in variants:
        try:
            vprice = float(v.get("price")) if v.get("price") is not None else None
        except (TypeError, ValueError):
            vprice = None
        variant_rows.append(
            {
                "name": v.get("title") or "Default",
                "sku": v.get("sku") or None,
                "price": vprice,
                "option": v.get("option1") or None,
            }
        )

    product_url = f"{base}/products/{handle}" if handle else None
    return ExtractedProduct(
        # Generic Shopify titles ("Cloud") get sharpened using the handle
        # ("cloud-pendant-14" → "Cloud Pendant 14\"").
        name=derive_product_name(node.get("title"), product_url),
        category=node.get("product_type") or None,
        description=_strip_html(node.get("body_html")),
        sku=sku,
        price=price,
        product_url=product_url,
        image_urls=images,
        variants=variant_rows,
    )


def fetch_shopify_products(
    base_url: str,
    fetcher: Callable,
    *,
    max_pages: int = 10,
    page_size: int = 250,
) -> list[ExtractedProduct] | None:
    """Pull all products from a Shopify ``/products.json`` feed, or None."""
    base = base_url.rstrip("/")
    # Normalise to the site root (drop any path component).
    m = re.match(r"(https?://[^/]+)", base)
    if m:
        base = m.group(1)

    products: list[ExtractedProduct] = []
    for page in range(1, max_pages + 1):
        resp = fetcher(f"{base}/products.json?limit={page_size}&page={page}")
        if resp is None or resp.status != 200:
            break
        body = (resp.html or "").lstrip()
        if not body.startswith("{"):
            break
        try:
            data = json.loads(resp.html)
        except json.JSONDecodeError:
            break
        nodes = data.get("products") or []
        if not nodes:
            break
        for node in nodes:
            if node.get("title"):
                products.append(_to_product(node, base))
        if len(nodes) < page_size:
            break
    return products or None
