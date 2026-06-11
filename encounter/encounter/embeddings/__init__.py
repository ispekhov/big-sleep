"""Image embedding backends."""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import Embedder
from .fallback import PerceptualEmbedder


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedder_backend == "siglip":
        from .siglip import SiglipEmbedder

        return SiglipEmbedder()
    return PerceptualEmbedder(dim=settings.embedding_dim)


__all__ = ["Embedder", "PerceptualEmbedder", "get_embedder"]
