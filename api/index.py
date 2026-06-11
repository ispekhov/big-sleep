"""Vercel serverless entry point for the Encounter Object ID web interface.

Vercel's Python runtime serves the module-level ``app`` (an ASGI application).
Non-secret backend selection is set here so the deployment is deterministic:

  * pgvector for durable similarity search (stateless across invocations).
  * Null storage + remote image URLs (read-only ephemeral filesystem).

The database connection string is a SECRET and is intentionally NOT in the
repo: set ``ENCOUNTER_DATABASE_URL`` as a Vercel project environment variable
(Supabase transaction-pooler URL for the scoped ``objectid_app`` role).
"""

import os
import sys

# Make the `encounter` package importable (it lives in ./encounter/encounter).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "encounter"))

# Non-secret backend configuration (overridable via Vercel env vars).
os.environ.setdefault("ENCOUNTER_SERVERLESS_DB", "true")
os.environ.setdefault("ENCOUNTER_VECTOR_BACKEND", "pgvector")
os.environ.setdefault("ENCOUNTER_EMBEDDING_DIM", "512")
os.environ.setdefault("ENCOUNTER_STORAGE_BACKEND", "null")
os.environ.setdefault("ENCOUNTER_REHOST_IMAGES", "false")
os.environ.setdefault("ENCOUNTER_AUTO_CREATE_TABLES", "true")
os.environ.setdefault("ENCOUNTER_CRAWL_MAX_PAGES", "40")
os.environ.setdefault("ENCOUNTER_CRAWL_MAX_IMAGES_PER_PRODUCT", "3")

from encounter.main import app  # noqa: E402

__all__ = ["app"]
