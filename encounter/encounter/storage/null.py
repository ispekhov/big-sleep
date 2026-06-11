"""No-op storage backend for stateless/serverless deployments.

Does not persist bytes (the platform's filesystem may be read-only and
ephemeral). Returns a stable pseudo-URL so callers still get a reference.
Used when images are referenced by their original CDN URL and query/field
images only need their embedding persisted, not their bytes.
"""

from __future__ import annotations

from .base import ObjectStorage


class NullStorage(ObjectStorage):
    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        return self.url_for(key)

    def get(self, key: str) -> bytes:  # pragma: no cover - not retrievable
        raise NotImplementedError("NullStorage does not persist bytes")

    def url_for(self, key: str) -> str:
        return f"/unstored/{key.lstrip('/')}"

    def exists(self, key: str) -> bool:
        return False
