"""Re-fingerprint and re-index the catalogue.

Two jobs, on demand:

* **Rebuild the vector index** from the embeddings already stored in the
  database (repair a process-local in-memory index, or re-seed a fresh
  collection) — the default.
* **Re-fingerprint** (``--embed``): re-run the *currently configured* embedder
  over each catalogue image's bytes, overwrite the stored embedding, then
  rebuild the index. This is the step you run after switching
  ``ENCOUNTER_EMBEDDER_BACKEND`` (e.g. ``fallback`` -> ``siglip``): old
  fingerprints are from a different model and are not comparable to new query
  vectors, so every catalogue image must be re-embedded.

Bytes come from object storage when available (``storage_key``), else they are
re-fetched from the image's public URL (the serverless profile references brand
CDN URLs instead of re-hosting bytes).

    python -m encounter.reindex                      # rebuild index from DB
    python -m encounter.reindex --embed              # re-fingerprint everything
    python -m encounter.reindex --embed --brand "Roll & Hill"
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .embeddings import Embedder, get_embedder
from .enums import ImageType
from .models import Brand, Image, Product
from .storage import ObjectStorage, get_storage
from .vectorstore import VectorStore, get_vector_store

# Image types that belong in the search index (everything but raw user queries
# and unverified field captures). Mirrors main._reindex_from_db.
INDEXABLE = (
    ImageType.official_product_image,
    ImageType.retailer_image,
    ImageType.catalogue_image,
    ImageType.field_capture_verified,
)


@dataclass
class ReindexStats:
    images: int = 0          # catalogue images considered
    re_embedded: int = 0     # successfully re-fingerprinted
    indexed: int = 0         # upserted into the vector store
    fetch_failed: int = 0    # bytes unavailable (skipped)

    def __str__(self) -> str:
        out = (
            f"images={self.images} indexed={self.indexed}"
            f" re_embedded={self.re_embedded}"
        )
        if self.fetch_failed:
            out += f" fetch_failed={self.fetch_failed}"
        return out


def _fetch_bytes(storage: ObjectStorage, image: Image) -> bytes | None:
    """Original image bytes: object storage first, then the public URL."""
    if image.storage_key:
        try:
            if storage.exists(image.storage_key):
                return storage.get(image.storage_key)
        except Exception:  # storage miss / null backend — fall through to URL
            pass
    url = image.image_url or ""
    if url.startswith("http"):
        import httpx

        settings = get_settings()
        try:
            resp = httpx.get(
                url,
                timeout=settings.crawl_request_timeout,
                follow_redirects=True,
                headers={"User-Agent": settings.crawl_user_agent},
            )
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception:
            return None
    return None


def reindex(
    session: Session,
    *,
    embedder: Embedder,
    store: VectorStore,
    storage: ObjectStorage,
    brand: str | None = None,
    re_embed: bool = False,
) -> ReindexStats:
    """Rebuild the vector index (optionally re-fingerprinting first)."""
    stmt = (
        select(Image)
        .join(Product, Image.product_id == Product.id)
        .where(
            Image.image_type.in_(INDEXABLE),
            Image.product_id.is_not(None),
            Product.deleted_at.is_(None),
        )
    )
    if brand:
        stmt = stmt.join(Brand, Product.brand_id == Brand.id).where(
            Brand.name == brand
        )

    stats = ReindexStats()
    for image in session.scalars(stmt):
        stats.images += 1
        if re_embed:
            data = _fetch_bytes(storage, image)
            if data is None:
                stats.fetch_failed += 1
                continue
            try:
                vec = embedder.embed(data)
            except Exception:
                stats.fetch_failed += 1
                continue
            image.embedding = [float(x) for x in vec.tolist()]
            image.embedding_model = embedder.name
            stats.re_embedded += 1
        else:
            if not image.embedding:
                continue
            vec = np.asarray(image.embedding, dtype=np.float32)

        store.upsert(
            image.id,
            vec,
            {
                "product_id": image.product_id,
                "image_type": image.image_type.value,
            },
        )
        stats.indexed += 1
    session.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m encounter.reindex",
        description="Rebuild the vector index, optionally re-fingerprinting "
                    "the catalogue with the configured embedder.",
    )
    parser.add_argument(
        "--embed", action="store_true",
        help="Re-fingerprint every image with the configured embedder before "
             "indexing (run this after switching ENCOUNTER_EMBEDDER_BACKEND).",
    )
    parser.add_argument(
        "--brand", default=None, help='Scope to one brand (e.g. "Roll & Hill").'
    )
    args = parser.parse_args(argv)

    from .db import init_db, session_scope

    settings = get_settings()
    embedder = get_embedder()
    init_db()

    if args.embed and embedder.dim != settings.embedding_dim:
        # Durable indexes (pgvector/qdrant) are created at a fixed dimension; a
        # new model with a different width needs the collection recreated too.
        print(
            f"NOTE: '{embedder.name}' produces dim={embedder.dim} but "
            f"ENCOUNTER_EMBEDDING_DIM={settings.embedding_dim}. Set "
            f"ENCOUNTER_EMBEDDING_DIM={embedder.dim} and recreate the "
            f"pgvector/qdrant collection at that width before indexing there.",
            file=sys.stderr,
        )

    with session_scope() as session:
        stats = reindex(
            session,
            embedder=embedder,
            store=get_vector_store(),
            storage=get_storage(),
            brand=args.brand,
            re_embed=args.embed,
        )
    scope = f'brand "{args.brand}"' if args.brand else "full catalogue"
    print(f"Reindex ({scope}, embedder={embedder.name}): {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
