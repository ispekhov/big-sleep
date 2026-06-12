"""Runtime configuration.

Everything has a sensible default so the platform runs end-to-end with zero
external services (SQLite + local disk storage + in-memory vector store +
deterministic perceptual embedder). Point the env vars at Postgres, Qdrant,
Cloudflare R2, and a real embedding/VLM provider for production.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "var"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ENCOUNTER_", env_file=".env", extra="ignore"
    )

    # --- Database ---------------------------------------------------------
    # e.g. postgresql+psycopg://user:pass@host:5432/encounter
    database_url: str = f"sqlite:///{DATA_DIR / 'encounter.db'}"
    # On serverless (Vercel) point at the Supabase transaction pooler and set
    # this true so SQLAlchemy uses NullPool + disables psycopg prepared stmts.
    serverless_db: bool = False
    # Create tables on startup. Disable in prod when schema is migration-managed.
    auto_create_tables: bool = True
    # Pin the Postgres search_path (e.g. "object_id,public") so the app only
    # uses its own schema even when connecting through a shared role.
    db_schema: str | None = None

    # --- Object storage (Cloudflare R2 / S3 compatible) -------------------
    # Backend: "local" or "r2". Local writes under var/storage.
    storage_backend: str = "local"
    storage_local_dir: str = str(DATA_DIR / "storage")
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str = "encounter"
    # Public base URL used to build image URLs (CDN in front of R2).
    storage_public_base_url: str = "/media"
    # When false, the importer references the original brand/CDN image URL
    # instead of re-hosting bytes — ideal for a stateless serverless demo.
    rehost_images: bool = True

    # --- Embeddings -------------------------------------------------------
    # "fallback" (deterministic perceptual, no GPU) or "siglip".
    embedder_backend: str = "fallback"
    embedding_dim: int = 512
    siglip_model: str = "google/siglip-base-patch16-224"

    # --- Vector store -----------------------------------------------------
    # "memory", "qdrant", or "pgvector" (durable, lives in Postgres).
    vector_backend: str = "memory"
    pgvector_table: str = "image_vectors"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "encounter_images"

    # --- Reranker (VLM) ---------------------------------------------------
    # "heuristic" (no API) or "vlm". Provider config read by the reranker.
    reranker_backend: str = "heuristic"

    # --- Firecrawl (headless render + anti-bot extraction fallback) -------
    # When set, the importer falls back to Firecrawl for sites that the free
    # HTTP path can't read (JS-rendered or WAF-blocked). Secret — set via the
    # ENCOUNTER_FIRECRAWL_API_KEY env var, never committed.
    firecrawl_api_key: str | None = None
    firecrawl_base_url: str = "https://api.firecrawl.dev"
    firecrawl_max_products: int = 3
    firecrawl_timeout: float = 45.0

    # Public base URL of this deployment, used by the batch engine to chain
    # self-requests so the queue drains autonomously (no external driver).
    self_base_url: str | None = None

    # --- Importer / crawler ----------------------------------------------
    crawl_max_pages: int = 200
    crawl_max_images_per_product: int = 8
    # Max products to ingest per brand in one import (full catalogues).
    import_product_limit: int = 500
    # Many brand sites sit behind WAFs that 403 non-browser agents, so we
    # present a mainstream browser UA while still honouring robots.txt.
    crawl_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    crawl_request_timeout: float = 15.0

    # --- Search -----------------------------------------------------------
    search_top_k: int = 10
    search_rerank_k: int = 5

    def ensure_dirs(self) -> None:
        # Only needed for the local dev profile (SQLite / local-disk storage).
        # Serverless filesystems are read-only, so tolerate mkdir failures.
        needs_data_dir = (
            self.database_url.startswith("sqlite")
            or self.storage_backend == "local"
        )
        if needs_data_dir:
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        if self.storage_backend == "local":
            try:
                Path(self.storage_local_dir).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
