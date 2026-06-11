"""Encounter FastAPI application.

Run locally:  uvicorn encounter.main:app --reload
Then open http://localhost:8000/  for the Correction UI / search console,
and http://localhost:8000/docs  for the API.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import brands, corrections, products, search
from .config import get_settings
from .db import init_db
from .vectorstore import get_vector_store

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Encounter — Product Recognition Platform",
        version=__version__,
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

    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        _reindex_from_db()

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "embedder": settings.embedder_backend,
            "vector_backend": settings.vector_backend,
            "storage_backend": settings.storage_backend,
            "indexed_vectors": get_vector_store().count(),
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
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

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
