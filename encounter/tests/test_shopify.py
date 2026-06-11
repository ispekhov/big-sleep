import json

from encounter.importer.crawler import FetchedPage
from encounter.importer.shopify import fetch_shopify_products

_FEED = {
    "products": [
        {
            "title": "Navy Chair",
            "handle": "navy-chair",
            "product_type": "Chairs",
            "body_html": "<p>Recycled aluminium chair.</p>",
            "images": [{"src": "https://cdn.shopify.com/navy.jpg"}],
            "variants": [
                {"title": "Polished", "price": "495.00", "sku": "NAVY-1", "option1": "Polished"},
                {"title": "Brushed", "price": "455.00", "sku": "NAVY-2", "option1": "Brushed"},
            ],
        }
    ]
}


def _fetcher(url):
    if "products.json" in url and "page=1" in url:
        return FetchedPage(url=url, status=200, html=json.dumps(_FEED), content_type="application/json")
    if "products.json" in url:  # page 2+ empty
        return FetchedPage(url=url, status=200, html='{"products": []}', content_type="application/json")
    return FetchedPage(url=url, status=404, html="not found", content_type="text/html")


def test_shopify_adapter_parses_feed():
    products = fetch_shopify_products("https://brand.com", _fetcher)
    assert products is not None
    assert len(products) == 1
    p = products[0]
    assert p.name == "Navy Chair"
    assert p.category == "Chairs"
    assert p.price == 495.0
    assert p.sku == "NAVY-1"
    assert p.product_url == "https://brand.com/products/navy-chair"
    assert p.image_urls == ["https://cdn.shopify.com/navy.jpg"]
    assert len(p.variants) == 2
    assert p.description and "aluminium" in p.description


def test_shopify_adapter_returns_none_when_absent():
    def fetcher(url):
        return FetchedPage(url=url, status=404, html="<html>nope</html>", content_type="text/html")

    assert fetch_shopify_products("https://brand.com", fetcher) is None
