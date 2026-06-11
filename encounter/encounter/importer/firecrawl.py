"""Firecrawl fallback: headless rendering + anti-bot + LLM extraction.

Used for brand sites the free HTTP path can't read — JavaScript-rendered
storefronts (e.g. Emeco) and WAF-blocked sites (e.g. Driade). Firecrawl runs a
real browser on residential IPs and returns either rendered HTML or, with a
schema, structured product JSON regardless of the page's layout.

We talk to the REST API directly (httpx) to avoid an extra dependency, and try
the v2 endpoints first, falling back to v1, parsing responses defensively so a
minor API shape change degrades gracefully instead of crashing an import.
"""

from __future__ import annotations

import logging

import httpx

from ..config import get_settings
from .extractor import ExtractedProduct

log = logging.getLogger("encounter.firecrawl")

# schema.org-ish product schema handed to Firecrawl's extractor.
_PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Product name"},
        "category": {"type": "string"},
        "collection": {"type": "string"},
        "description": {"type": "string"},
        "materials": {"type": "string"},
        "dimensions": {"type": "string"},
        "price": {"type": "number"},
        "currency": {"type": "string"},
        "sku": {"type": "string"},
        "images": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Absolute URLs of the product's images",
        },
    },
    "required": ["name"],
}

_EXTRACT_PROMPT = (
    "Extract the single product shown on this page. Use absolute image URLs. "
    "If the page is not a product detail page, return an empty object."
)

# URL fragments that suggest an individual product detail page.
_PRODUCT_HINTS = (
    "/product",
    "/products/",
    "/p/",
    "/item",
    "/shop/",
    "/collections/",
    "/furniture/",
)


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


class FirecrawlClient:
    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def _post(self, paths: list[str], payload: dict) -> dict | None:
        for path in paths:
            try:
                resp = self._http.post(path, json=payload)
            except httpx.HTTPError as exc:
                log.warning("firecrawl %s error: %s", path, exc)
                continue
            if resp.status_code == 404:
                continue  # try the next API version
            if resp.status_code >= 400:
                log.warning("firecrawl %s -> %s: %s", path, resp.status_code, resp.text[:200])
                return None
            try:
                return resp.json()
            except ValueError:
                return None
        return None

    def map_urls(self, url: str, limit: int = 300) -> list[str]:
        """Discover the site's URLs (cheap), biased toward product pages."""
        data = self._post(
            ["/v2/map", "/v1/map"],
            {"url": url, "limit": limit, "sitemap": "include"},
        )
        if not data:
            return []
        links = data.get("links") or data.get("data") or []
        out: list[str] = []
        for link in links:
            u = link.get("url") if isinstance(link, dict) else link
            if isinstance(u, str):
                out.append(u)
        return out

    def scrape_product(self, url: str) -> ExtractedProduct | None:
        """Render a page and extract structured product JSON, or None."""
        # v2 shape: formats:[{type:json,...}] ; v1 shape: formats:["json"]+jsonOptions
        payload_v2 = {
            "url": url,
            "onlyMainContent": True,
            "formats": [
                {"type": "json", "schema": _PRODUCT_SCHEMA, "prompt": _EXTRACT_PROMPT}
            ],
        }
        data = self._post(["/v2/scrape"], payload_v2)
        if data is None:
            payload_v1 = {
                "url": url,
                "onlyMainContent": True,
                "formats": ["json"],
                "jsonOptions": {"schema": _PRODUCT_SCHEMA, "prompt": _EXTRACT_PROMPT},
            }
            data = self._post(["/v1/scrape"], payload_v1)
        if not data:
            return None

        body = data.get("data") or data
        extracted = body.get("json") or body.get("extract") or body.get("llm_extraction")
        if not isinstance(extracted, dict):
            return None
        name = extracted.get("name")
        images = [i for i in (extracted.get("images") or []) if isinstance(i, str)]
        if not name or not images:
            return None
        return ExtractedProduct(
            name=name,
            category=extracted.get("category"),
            collection=extracted.get("collection"),
            description=extracted.get("description"),
            materials=extracted.get("materials"),
            dimensions=extracted.get("dimensions"),
            price=_to_float(extracted.get("price")),
            currency=extracted.get("currency"),
            sku=extracted.get("sku"),
            product_url=url,
            image_urls=images,
        )


def _config_from_db(key: str) -> str | None:
    """Read a secret from the object_id.app_config table (a tiny secret store).

    Lets operators set the Firecrawl key in the DB instead of an env var.
    Best-effort: any failure (table missing, DB down) yields None.
    """
    try:
        from sqlalchemy import text

        from ..db import engine

        with engine.connect() as conn:
            return conn.execute(
                text("select value from app_config where key = :k"), {"k": key}
            ).scalar()
    except Exception:  # noqa: BLE001
        return None


def get_firecrawl_client() -> FirecrawlClient | None:
    settings = get_settings()
    key = settings.firecrawl_api_key or _config_from_db("firecrawl_api_key")
    if not key:
        return None
    return FirecrawlClient(
        key,
        settings.firecrawl_base_url,
        settings.firecrawl_timeout,
    )


def looks_like_product_url(url: str) -> bool:
    return any(h in url.lower() for h in _PRODUCT_HINTS)


def firecrawl_import(
    start_url: str, client: FirecrawlClient, *, max_products: int
) -> list[ExtractedProduct]:
    """Map a site, pick likely product URLs, and extract each via Firecrawl."""
    urls = client.map_urls(start_url)
    if not urls:
        return []
    # Prefer product-looking URLs; de-dup; cap to respect time/credits.
    product_urls, seen = [], set()
    for u in urls:
        if looks_like_product_url(u) and u not in seen:
            seen.add(u)
            product_urls.append(u)
    # If the URL patterns are unusual, fall back to the deepest paths.
    if not product_urls:
        product_urls = sorted(set(urls), key=lambda u: u.count("/"), reverse=True)

    products: list[ExtractedProduct] = []
    for u in product_urls[:max_products]:
        ex = client.scrape_product(u)
        if ex is not None:
            products.append(ex)
    return products
