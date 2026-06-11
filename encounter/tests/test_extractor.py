from encounter.importer.extractor import extract_product, looks_like_product_page

JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Melt Pendant",
  "description": "A mesmerising mouth-blown pendant light.",
  "sku": "MELT-001",
  "category": "Lighting",
  "material": "Polycarbonate",
  "brand": {"@type": "Brand", "name": "Tom Dixon"},
  "image": ["https://cdn.example.com/melt-1.jpg", "https://cdn.example.com/melt-2.jpg"],
  "offers": {"@type": "Offer", "price": "950.00", "priceCurrency": "USD"}
}
</script>
</head><body><h1>Melt</h1></body></html>
"""

OG_PAGE = """
<html><head>
<meta property="og:type" content="product" />
<meta property="og:title" content="Beat Light" />
<meta property="og:description" content="Hand-beaten brass shade." />
<meta property="og:image" content="https://cdn.example.com/beat.jpg" />
<meta property="product:price:amount" content="560" />
<meta property="product:price:currency" content="GBP" />
</head><body>Dimensions: 30 x 30 x 40 cm</body></html>
"""


def test_extracts_jsonld_product():
    p = extract_product(JSONLD_PAGE, "https://x.com/products/melt")
    assert p is not None
    assert p.name == "Melt Pendant"
    assert p.price == 950.0
    assert p.currency == "USD"
    assert p.sku == "MELT-001"
    assert p.category == "Lighting"
    assert p.materials == "Polycarbonate"
    assert len(p.image_urls) == 2
    assert p.required_present


def test_extracts_opengraph_and_dimensions():
    p = extract_product(OG_PAGE, "https://x.com/p/beat")
    assert p is not None
    assert p.name == "Beat Light"
    assert p.price == 560.0
    assert p.image_urls == ["https://cdn.example.com/beat.jpg"]
    assert p.dimensions and "30" in p.dimensions


def test_non_product_returns_none():
    assert extract_product("<html><body>About us</body></html>", "https://x.com/about") is None


def test_looks_like_product_page_url_hint():
    assert looks_like_product_page("https://x.com/products/melt")
    assert not looks_like_product_page("https://x.com/about-us")
