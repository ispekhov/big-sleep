from encounter.importer.crawler import Crawler, FetchedPage

PAGES = {
    "https://brand.com/robots.txt": FetchedPage("https://brand.com/robots.txt", 200, "User-agent: *\nAllow: /", "text/plain"),
    "https://brand.com/": FetchedPage(
        "https://brand.com/", 200,
        '<a href="/products/a">A</a><a href="/products/b">B</a><a href="/about">about</a>'
        '<a href="https://other.com/x">ext</a>', "text/html"),
    "https://brand.com/products/a": FetchedPage("https://brand.com/products/a", 200, "<h1>A</h1>", "text/html"),
    "https://brand.com/products/b": FetchedPage("https://brand.com/products/b", 200, "<h1>B</h1>", "text/html"),
    "https://brand.com/about": FetchedPage("https://brand.com/about", 200, "<p>about</p>", "text/html"),
}


def fetcher(url):
    return PAGES.get(url)


def test_crawler_finds_product_pages_same_site_only():
    crawler = Crawler(fetcher, max_pages=50)
    result = crawler.crawl("https://brand.com/")
    urls = {p.url for p in result.product_pages}
    assert urls == {"https://brand.com/products/a", "https://brand.com/products/b"}
    # external link never fetched
    assert result.pages_crawled == 4  # home + 2 products + about


def test_crawler_respects_page_budget():
    crawler = Crawler(fetcher, max_pages=2)
    result = crawler.crawl("https://brand.com/")
    assert result.pages_crawled == 2
