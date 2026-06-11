"""Local-disk storage backend (development / tests)."""

from __future__ import annotations

from pathlib import Path

from ..config import get_settings
from .base import ObjectStorage


class LocalStorage(ObjectStorage):
    def __init__(self) -> None:
        settings = get_settings()
        self.root = Path(settings.storage_local_dir)
        self.public_base = settings.storage_public_base_url.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Guard against path traversal in keys.
        safe = key.lstrip("/").replace("..", "_")
        return self.root / safe

    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.url_for(key)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def url_for(self, key: str) -> str:
        return f"{self.public_base}/{key.lstrip('/')}"

    def exists(self, key: str) -> bool:
        return self._path(key).exists()
