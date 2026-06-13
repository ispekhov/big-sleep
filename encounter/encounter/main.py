"""Encounter FastAPI application.

Run locally:  uvicorn encounter.main:app --reload
Then open http://localhost:8000/  for the Correction UI / search console,
and http://localhost:8000/docs  for the API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import __version__
from .api import brands, corrections, products, search
from .config import get_settings
from .db import get_session, init_db
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
        # No-store so a new deploy's UI is picked up immediately instead of a
        # stale cached page (the console is a single inline HTML document).
        return HTMLResponse(
            INDEX_HTML, headers={"Cache-Control": "no-store, must-revalidate"}
        )

    @app.get("/b/{brand_id}", include_in_schema=False)
    def brand_page(
        brand_id: int, session: Session = Depends(get_session)
    ) -> HTMLResponse:
        # A standalone, server-rendered page for one brand's catalogue. Native
        # HTML — no client JS needed to view products — reached via a normal
        # link from the console's brand grid.
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from .models import Brand, Product
        from .webui import render_brand_page

        brand = session.get(Brand, brand_id)
        if brand is None:
            return HTMLResponse(
                "<p style='font:16px system-ui;padding:24px'>Brand not found. "
                "<a href='/'>← Back</a></p>",
                status_code=404,
            )
        products = list(
            session.scalars(
                select(Product)
                .where(Product.brand_id == brand_id)
                .options(selectinload(Product.images))
                .order_by(Product.name)
            ).all()
        )
        return HTMLResponse(
            render_brand_page(brand.name, brand.website, products),
            headers={"Cache-Control": "no-store"},
        )

    return app


def _reindex_from_db() -> None:
    """Rebuild an empty in-memory vector index from stored embeddings.

    The in-memory store is process-local, so on each boot we hydrate it from
    the embeddings persisted in Postgres/SQLite. (No-op for Qdrant/pgvector,
    which are durable — guarded by the count check.)
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
