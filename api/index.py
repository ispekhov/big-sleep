"""Vercel serverless entry point for the Encounter Object ID web interface.

Vercel's Python runtime serves the module-level ``app`` (an ASGI application).
Non-secret backend selection is set here so the deployment is deterministic;
the database connection string is supplied via the ``ENCOUNTER_DATABASE_URL``
Vercel env var (it is a secret and is intentionally not in the repo).
"""

import os
import sys
import traceback

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

try:
    from encounter.main import app  # noqa: E402
except Exception:  # pragma: no cover - diagnostic fallback
    _TB = traceback.format_exc()

    async def app(scope, receive, send):  # minimal pure-ASGI error reporter
        if scope["type"] != "http":
            return
        body = ("Encounter import failed:\n\n" + _TB).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": body})

__all__ = ["app"]
