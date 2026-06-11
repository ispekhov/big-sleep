"""Deterministic perceptual embedder — no GPU, no network, no model weights.

This produces a *real* visual descriptor (not a random hash) so photo search
works end-to-end out of the box: visually similar images map to nearby
vectors. It combines a downscaled grayscale "structure" grid with per-region
RGB colour statistics, then projects to the configured dimension with a fixed
seeded random projection so the output size matches the production embedder.

Swap ``ENCOUNTER_EMBEDDER_BACKEND=siglip`` for production-quality recognition.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageOps

_GRID = 16  # 16x16 structure grid
_REGIONS = 4  # 4x4 colour regions


class PerceptualEmbedder:
    name = "perceptual-fallback-v1"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        raw_dim = _GRID * _GRID + _REGIONS * _REGIONS * 3
        # Fixed random projection -> stable across processes/runs.
        rng = np.random.default_rng(seed=1729)
        self._proj = rng.standard_normal((raw_dim, dim)).astype(np.float32)

    def _raw_features(self, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")

        gray = np.asarray(
            img.resize((_GRID, _GRID), Image.BILINEAR).convert("L"),
            dtype=np.float32,
        ).reshape(-1)
        gray = gray / 255.0
        gray = gray - gray.mean()  # illumination invariance

        regions = np.asarray(
            img.resize((_REGIONS, _REGIONS), Image.BILINEAR), dtype=np.float32
        ).reshape(-1)
        regions = regions / 255.0

        return np.concatenate([gray, regions]).astype(np.float32)

    def embed(self, image_bytes: bytes) -> np.ndarray:
        raw = self._raw_features(image_bytes)
        vec = raw @ self._proj
        norm = float(np.linalg.norm(vec))
        return (vec / norm).astype(np.float32) if norm > 0 else vec
