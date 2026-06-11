"""Object storage abstraction (Cloudflare R2 in prod, local disk by default)."""

from __future__ import annotations

from ..config import get_settings
from .base import ObjectStorage
from .local import LocalStorage


def get_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.storage_backend == "r2":
        from .r2 import R2Storage

        return R2Storage()
    if settings.storage_backend == "null":
        from .null import NullStorage

        return NullStorage()
    return LocalStorage()


__all__ = ["ObjectStorage", "LocalStorage", "get_storage"]
