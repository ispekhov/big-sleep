"""In-memory cosine-similarity vector store (development / tests).

Vectors are assumed L2-normalized by the embedder, so a dot product is the
cosine similarity. Fine for thousands of images; use Qdrant for scale.
"""

from __future__ import annotations

import numpy as np

from .base import SearchHit, VectorStore


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._ids: list[int] = []
        self._payloads: dict[int, dict] = {}
        self._matrix: np.ndarray | None = None  # (n, dim)

    def upsert(self, image_id: int, vector: np.ndarray, payload: dict) -> None:
        vector = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if image_id in self._payloads:
            idx = self._ids.index(image_id)
            self._matrix[idx] = vector
        else:
            self._ids.append(image_id)
            self._matrix = (
                vector if self._matrix is None
                else np.vstack([self._matrix, vector])
            )
        self._payloads[image_id] = payload

    def search(self, vector: np.ndarray, top_k: int = 10) -> list[SearchHit]:
        if self._matrix is None or not self._ids:
            return []
        q = np.asarray(vector, dtype=np.float32).reshape(-1)
        scores = self._matrix @ q
        order = np.argsort(-scores)[:top_k]
        hits = []
        for i in order:
            image_id = self._ids[i]
            payload = self._payloads[image_id]
            hits.append(
                SearchHit(
                    image_id=image_id,
                    product_id=payload.get("product_id"),
                    score=float(scores[i]),
                    payload=payload,
                )
            )
        return hits

    def delete(self, image_id: int) -> None:
        if image_id not in self._payloads:
            return
        idx = self._ids.index(image_id)
        self._ids.pop(idx)
        self._payloads.pop(image_id)
        self._matrix = np.delete(self._matrix, idx, axis=0)
        if self._matrix.shape[0] == 0:
            self._matrix = None

    def count(self) -> int:
        return len(self._ids)
