"""Vercel serverless entry point for the Encounter Object ID web interface.

Vercel statically scans this file for a top-level ``app`` symbol to classify it
as a Serverless Function, so ``app`` is defined unconditionally as a thin ASGI
wrapper. It lazily imports the real FastAPI app on first use and, if that
import fails, serves the traceback instead of an opaque 500.

The database connection string is supplied via the ``ENCOUNTER_DATABASE_URL``
Vercel env var (a secret, intentionally not in the repo).
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
os.environ.setdefault("ENCOUNTER_AUTO_CREATE_TABLES", "false")
os.environ.setdefault("ENCOUNTER_DB_SCHEMA", "object_id,public")
os.environ.setdefault("ENCOUNTER_CRAWL_MAX_PAGES", "40")
os.environ.setdefault("ENCOUNTER_CRAWL_MAX_IMAGES_PER_PRODUCT", "3")

_real_app = None
_import_error = None


def _get_app():
    global _real_app, _import_error
    if _real_app is None and _import_error is None:
        try:
            from encounter.main import app as real_app
            _real_app = real_app
        except Exception:
            _import_error = traceback.format_exc()
    return _real_app


async def app(scope, receive, send):
    real = _get_app()
    if real is not None:
        await real(scope, receive, send)
        return
    # Import failed: drain lifespan events and report the traceback on HTTP.
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    body = ("Encounter import failed:\n\n" + (_import_error or "")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": body})

# Redeploy trigger: corrected Supabase pooler host (aws-1-eu-north-1).
