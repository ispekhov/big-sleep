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

    # --- Embeddings -------------------------------------------------------
    # "fallback" (deterministic perceptual, no GPU) or "siglip".
    embedder_backend: str = "fallback"
    embedding_dim: int = 512
    siglip_model: str = "google/siglip-base-patch16-224"

    # --- Vector store -----------------------------------------------------
    # "memory" or "qdrant".
    vector_backend: str = "memory"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "encounter_images"

    # --- Reranker (VLM) ---------------------------------------------------
    # "heuristic" (no API) or "vlm". Provider config read by the reranker.
    reranker_backend: str = "heuristic"

    # --- Importer / crawler ----------------------------------------------
    crawl_max_pages: int = 200
    crawl_max_images_per_product: int = 8
    crawl_user_agent: str = "EncounterBot/1.0 (+https://encounter.app)"
    crawl_request_timeout: float = 15.0

    # --- Search -----------------------------------------------------------
    search_top_k: int = 10
    search_rerank_k: int = 5

    def ensure_dirs(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.storage_backend == "local":
            Path(self.storage_local_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
