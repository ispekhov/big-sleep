"""Polite, same-domain BFS crawler that surfaces product pages.

It respects an in-process page budget, stays on the brand's registrable
domain, skips obvious non-HTML assets, and (best-effort) honours
``robots.txt`` Disallow rules. Network access is injected as a ``fetcher``
callable so the crawler is fully unit-testable offline.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from ..config import get_settings
from ..util import make_soup
from .extractor import looks_like_product_page

Fetcher = Callable[[str], "FetchedPage | None"]

_SKIP_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip",
    ".mp4", ".mov", ".css", ".js", ".ico", ".woff", ".woff2", ".ttf",
)


@dataclass
class FetchedPage:
    url: str
    status: int
    html: str
    content_type: str = "text/html"


@dataclass
class CrawlResult:
    product_pages: list[FetchedPage] = field(default_factory=list)
    pages_crawled: int = 0


def _registrable(netloc: str) -> str:
    # Treat www.brand.com and brand.com as the same site.
    return netloc.lower().removeprefix("www.")


def _same_site(a: str, b: str) -> bool:
    return _registrable(urlparse(a).netloc) == _registrable(urlparse(b).netloc)


class Crawler:
    def __init__(
        self, fetcher: Fetcher, max_pages: int | None = None
    ) -> None:
        settings = get_settings()
        self._fetch = fetcher
        self.max_pages = max_pages or settings.crawl_max_pages
        self._robots: RobotFileParser | None = None
        self._user_agent = settings.crawl_user_agent

    def _load_robots(self, start_url: str) -> None:
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        page = self._fetch(robots_url)
        rp = RobotFileParser()
        if page and page.status == 200:
            rp.parse(page.html.splitlines())
        else:
            rp.allow_all = True
        self._robots = rp

    def _allowed(self, url: str) -> bool:
        if self._robots is None:
            return True
        try:
            return self._robots.can_fetch(self._user_agent, url)
        except Exception:
            return True

    def crawl(self, start_url: str) -> CrawlResult:
        self._load_robots(start_url)
        result = CrawlResult()
        seen: set[str] = set()
        # Seed the queue with sitemap URLs first (prioritising likely product
        # pages) so a bounded crawl finds real products fast, then fall back
        # to following links from the homepage.
        sitemap_urls = self._discover_via_sitemap(start_url)
        queue: deque[str] = deque(sitemap_urls)
        queue.append(start_url)

        while queue and result.pages_crawled < self.max_pages:
            url = queue.popleft()
            url, _, _ = url.partition("#")
            if url in seen or not self._allowed(url):
                continue
            seen.add(url)

            page = self._fetch(url)
            if page is None or page.status >= 400:
                continue
            if "html" not in page.content_type:
                continue
            result.pages_crawled += 1

            if looks_like_product_page(page.url, page.html):
                result.product_pages.append(page)

            for link in self._extract_links(page):
                if (
                    link not in seen
                    and _same_site(start_url, link)
                    and not link.lower().endswith(_SKIP_EXT)
                ):
                    queue.append(link)

        return result

    def _discover_via_sitemap(self, start_url: str) -> list[str]:
        """Pull candidate URLs from /sitemap.xml (and nested sitemaps).

        Product URLs (per ``looks_like_product_page`` URL hints) are returned
        first so they are crawled within the page budget. Best-effort: any
        failure just yields an empty list and the crawler falls back to BFS.
        """
        parsed = urlparse(start_url)
        roots = [
            f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
            f"{parsed.scheme}://{parsed.netloc}/sitemap_index.xml",
        ]
        found: list[str] = []
        seen_maps: set[str] = set()
        pending = list(roots)
        # Bound sitemap fetches so a giant sitemap index can't blow the budget.
        while pending and len(seen_maps) < 12:
            sm = pending.pop(0)
            if sm in seen_maps:
                continue
            seen_maps.add(sm)
            page = self._fetch(sm)
            if page is None or page.status >= 400 or "<" not in page.html:
                continue
            soup = make_soup(page.html)
            # Nested sitemap index -> queue child sitemaps.
            for loc in soup.find_all("loc"):
                url = (loc.get_text() or "").strip()
                if not url or not _same_site(start_url, url):
                    continue
                if url.endswith(".xml"):
                    pending.append(url)
                else:
                    found.append(url)
        # Product-looking URLs first, then the rest, de-duplicated.
        products = [u for u in found if looks_like_product_page(u)]
        others = [u for u in found if not looks_like_product_page(u)]
        ordered, seen = [], set()
        for u in products + others:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
        return ordered

    @staticmethod
    def _extract_links(page: FetchedPage) -> list[str]:
        soup = make_soup(page.html)
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            links.append(urljoin(page.url, href))
        return links
