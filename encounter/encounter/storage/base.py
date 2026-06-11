"""Storage interface."""

from __future__ import annotations

import abc


class ObjectStorage(abc.ABC):
    """Stores image bytes and returns a stable key + a public URL."""

    @abc.abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """Store ``data`` under ``key`` and return the public URL."""

    @abc.abstractmethod
    def get(self, key: str) -> bytes:
        """Read raw bytes for ``key``."""

    @abc.abstractmethod
    def url_for(self, key: str) -> str:
        """Public URL for an already-stored ``key``."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool: ...
