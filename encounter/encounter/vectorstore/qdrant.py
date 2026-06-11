"""Qdrant vector store backend (production).

``qdrant-client`` is an optional dependency, imported lazily.
"""

from __future__ import annotations

import numpy as np

from ..config import get_settings
from .base import SearchHit, VectorStore


class QdrantVectorStore(VectorStore):
    def __init__(self) -> None:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.models import Distance, VectorParams  # type: ignore

        settings = get_settings()
        if not settings.qdrant_url:
            raise RuntimeError("ENCOUNTER_QDRANT_URL is required for Qdrant backend")
        self.collection = settings.qdrant_collection
        self._client = QdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key
        )
        if not self._client.collection_exists(self.collection):
            self._client.create_collection(
                self.collection,
                vectors_config=VectorParams(
                    size=settings.embedding_dim, distance=Distance.COSINE
                ),
            )

    def upsert(self, image_id: int, vector: np.ndarray, payload: dict) -> None:
        from qdrant_client.models import PointStruct  # type: ignore

        self._client.upsert(
            self.collection,
            points=[
                PointStruct(
                    id=image_id, vector=np.asarray(vector).tolist(), payload=payload
                )
            ],
        )

    def search(self, vector: np.ndarray, top_k: int = 10) -> list[SearchHit]:
        res = self._client.query_points(
            self.collection,
            query=np.asarray(vector).tolist(),
            limit=top_k,
            with_payload=True,
        ).points
        return [
            SearchHit(
                image_id=int(p.id),
                product_id=(p.payload or {}).get("product_id"),
                score=float(p.score),
                payload=p.payload or {},
            )
            for p in res
        ]

    def delete(self, image_id: int) -> None:
        self._client.delete(self.collection, points_selector=[image_id])

    def count(self) -> int:
        return int(self._client.count(self.collection).count)
