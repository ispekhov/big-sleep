"""Vector store interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass

import numpy as np


@dataclass
class SearchHit:
    image_id: int
    product_id: int | None
    score: float  # cosine similarity in [-1, 1]
    payload: dict


class VectorStore(abc.ABC):
    @abc.abstractmethod
    def upsert(
        self, image_id: int, vector: np.ndarray, payload: dict
    ) -> None: ...

    @abc.abstractmethod
    def search(self, vector: np.ndarray, top_k: int = 10) -> list[SearchHit]: ...

    @abc.abstractmethod
    def delete(self, image_id: int) -> None: ...

    @abc.abstractmethod
    def count(self) -> int: ...
