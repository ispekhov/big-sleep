from encounter.embeddings.fallback import PerceptualEmbedder
from encounter.importer.crawler import FetchedPage
from encounter.importer.pipeline import DownloadedImage, ImportPipeline
from encounter.models import Brand, Image, Product
from encounter.storage.local import LocalStorage
from encounter.vectorstore.memory import InMemoryVectorStore
from tests.conftest import make_jpeg


def _product_html(name, sku, price, img):
    return f"""<html><head>
    <meta property="og:site_name" content="Tom Dixon" />
    <script type="application/ld+json">
    {{"@type":"Product","name":"{name}","sku":"{sku}","category":"Lighting",
      "description":"Lovely.","image":["{img}"],
      "offers":{{"price":"{price}","priceCurrency":"USD"}}}}
    </script></head><body><a href="/">home</a></body></html>"""


PAGES = {
    "https://tomdixon.net/robots.txt": FetchedPage("https://tomdixon.net/robots.txt", 200, "User-agent: *\nAllow: /", "text/plain"),
    "https://tomdixon.net": FetchedPage(
        "https://tomdixon.net", 200,
        '<meta property="og:site_name" content="Tom Dixon" />'
        '<a href="/products/melt">Melt</a><a href="/products/beat">Beat</a>'
        '<a href="/about">About</a>', "text/html"),
    "https://tomdixon.net/products/melt": FetchedPage(
        "https://tomdixon.net/products/melt", 200,
        _product_html("Melt Pendant", "MELT", 950, "https://cdn.x/melt.jpg"), "text/html"),
    "https://tomdixon.net/products/beat": FetchedPage(
        "https://tomdixon.net/products/beat", 200,
        _product_html("Beat Light", "BEAT", 560, "https://cdn.x/beat.jpg"), "text/html"),
    "https://tomdixon.net/about": FetchedPage("https://tomdixon.net/about", 200, "<p>about</p>", "text/html"),
}

IMAGES = {
    "https://cdn.x/melt.jpg": make_jpeg(color=(255, 140, 0), seed=1),
    "https://cdn.x/beat.jpg": make_jpeg(color=(30, 30, 30), seed=2),
}


def fetcher(url):
    return PAGES.get(url)


def downloader(url):
    data = IMAGES.get(url)
    return DownloadedImage(url=url, data=data) if data else None


def _pipeline(session):
    return ImportPipeline(
        session, fetcher=fetcher, downloader=downloader,
        embedder=PerceptualEmbedder(dim=256),
        storage=LocalStorage(), vector_store=InMemoryVectorStore(),
    )


def test_full_import(session):
    summary = _pipeline(session).run("https://tomdixon.net")
    assert summary.brand == "Tom Dixon"
    assert summary.products_imported == 2
    assert summary.images_imported == 2
    assert summary.products_need_review == 0

    assert session.query(Brand).count() == 1
    assert session.query(Product).count() == 2
    assert session.query(Image).count() == 2
    melt = session.query(Product).filter_by(name="Melt Pendant").one()
    assert melt.price == 950.0
    assert melt.images[0].embedding is not None


def test_import_is_idempotent(session):
    _pipeline(session).run("https://tomdixon.net")
    _pipeline(session).run("https://tomdixon.net")
    assert session.query(Product).count() == 2  # no duplicates
