"""Vector store backends (Qdrant in prod, in-memory by default)."""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import SearchHit, VectorStore
from .memory import InMemoryVectorStore


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.vector_backend == "qdrant":
        from .qdrant import QdrantVectorStore

        return QdrantVectorStore()
    if settings.vector_backend == "pgvector":
        from .pgvector import PgVectorStore

        return PgVectorStore()
    return InMemoryVectorStore()


__all__ = ["VectorStore", "SearchHit", "InMemoryVectorStore", "get_vector_store"]
