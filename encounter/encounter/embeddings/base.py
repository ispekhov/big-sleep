"""Embedder interface."""

from __future__ import annotations

import abc

import numpy as np


class Embedder(abc.ABC):
    """Maps image bytes to an L2-normalized vector."""

    name: str
    dim: int

    @abc.abstractmethod
    def embed(self, image_bytes: bytes) -> np.ndarray:
        """Return a 1-D float32 vector of length ``dim`` (L2-normalized)."""

    def embed_batch(self, images: list[bytes]) -> np.ndarray:
        return np.stack([self.embed(b) for b in images]) if images else np.empty(
            (0, self.dim), dtype=np.float32
        )

    @staticmethod
    def normalize(vec: np.ndarray) -> np.ndarray:
        vec = vec.astype(np.float32)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec
