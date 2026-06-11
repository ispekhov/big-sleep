"""Encounter FastAPI application.

Run locally:  uvicorn encounter.main:app --reload
Then open http://localhost:8000/  for the Correction UI / search console,
and http://localhost:8000/docs  for the API.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import brands, corrections, products, search
from .config import get_settings
from .db import init_db
from .vectorstore import get_vector_store
from .webui import INDEX_HTML


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Don't let a transient DB hiccup take down the whole app at boot — the
    # console page and /health must still load. Endpoints that need the DB
    # surface their own errors.
    try:
        init_db()
        if get_settings().vector_backend == "memory":
            # Process-local index: rehydrate embeddings persisted in the DB.
            _reindex_from_db()
    except Exception as exc:  # noqa: BLE001
        app.state.last_db_error = str(exc)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Encounter — Product Recognition Platform",
        version=__version__,
        lifespan=lifespan,
        debug=os.environ.get("ENCOUNTER_DEBUG") == "1",
        description=(
            "Point a camera at furniture, lighting, and decor and identify "
            "the exact product. V1: brand import, product DB, image storage, "
            "embeddings, photo search, and corrections."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        # Stay green even if the DB/vector store is unreachable, so the page
        # and this probe still report deployment status.
        try:
            indexed = get_vector_store().count()
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            indexed = None
            db_ok = False
            app.state.last_db_error = str(exc)
        return {
            "status": "ok" if db_ok else "degraded",
            "version": __version__,
            "embedder": settings.embedder_backend,
            "vector_backend": settings.vector_backend,
            "storage_backend": settings.storage_backend,
            "database_connected": db_ok,
            "indexed_vectors": indexed,
        }

    @app.get("/debug/db", include_in_schema=False)
    def debug_db() -> dict:
        # Temporary diagnostic: report the real DB connection error (if any).
        from sqlalchemy import text

        from .db import engine

        try:
            with engine.connect() as conn:
                one = conn.execute(text("select 1")).scalar()
                vectors = conn.execute(
                    text("select count(*) from image_vectors")
                ).scalar()
            return {"ok": True, "select1": one, "image_vectors": vectors}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "type": type(exc).__name__, "error": str(exc)}

    @app.get("/debug/page", include_in_schema=False)
    def debug_page() -> dict:
        # Temporary: surface any exception raised while building the homepage.
        import traceback

        try:
            return {"ok": True, "html_len": len(INDEX_HTML)}
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": traceback.format_exc()}

    @app.get("/debug/crawl", include_in_schema=False)
    def debug_crawl(url: str, pages: int = 15) -> dict:
        # Temporary: inspect what the importer sees for a brand URL.
        from .importer.crawler import Crawler
        from .importer.extractor import extract_product
        from .importer.pipeline import make_http_fetcher

        fetcher = make_http_fetcher()
        home = fetcher(url)
        crawler = Crawler(fetcher, max_pages=pages)
        sitemap = crawler._discover_via_sitemap(url)
        result = crawler.crawl(url)
        samples = []
        for page in result.product_pages[:5]:
            ex = extract_product(page.html, page.url)
            samples.append(
                {
                    "url": page.url,
                    "extracted": ex is not None,
                    "name": ex.name if ex else None,
                    "images": len(ex.image_urls) if ex else 0,
                    "price": ex.price if ex else None,
                }
            )
        return {
            "home_status": home.status if home else None,
            "home_len": len(home.html) if home else 0,
            "sitemap_urls_found": len(sitemap),
            "sitemap_sample": sitemap[:12],
            "pages_crawled": result.pages_crawled,
            "product_pages_found": len(result.product_pages),
            "product_sample_urls": [p.url for p in result.product_pages[:12]],
            "extraction_samples": samples,
        }

    app.include_router(brands.router)
    app.include_router(products.router)
    app.include_router(search.router)
    app.include_router(corrections.router)

    # Serve locally-stored media (no-op when using R2 + CDN).
    if settings.storage_backend == "local":
        Path(settings.storage_local_dir).mkdir(parents=True, exist_ok=True)
        app.mount(
            "/media",
            StaticFiles(directory=settings.storage_local_dir),
            name="media",
        )

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML)

    return app


def _reindex_from_db() -> None:
    """Rebuild an empty in-memory vector index from stored embeddings.

    The in-memory store is process-local, so on each boot we hydrate it from
    the embeddings persisted in Postgres/SQLite. (No-op for Qdrant, which is
    durable — guarded by the count check.)
    """
    import numpy as np
    from sqlalchemy import select

    from .db import SessionLocal
    from .enums import ImageType
    from .models import Image

    store = get_vector_store()
    if store.count() > 0:
        return
    indexable = (
        ImageType.official_product_image,
        ImageType.retailer_image,
        ImageType.catalogue_image,
        ImageType.field_capture_verified,
    )
    with SessionLocal() as session:
        stmt = select(Image).where(
            Image.embedding.is_not(None),
            Image.image_type.in_(indexable),
            Image.product_id.is_not(None),
        )
        for image in session.scalars(stmt):
            store.upsert(
                image.id,
                np.asarray(image.embedding, dtype="float32"),
                {
                    "product_id": image.product_id,
                    "image_type": image.image_type.value,
                },
            )


app = create_app()
