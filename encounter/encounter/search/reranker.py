"""Re-ranking stage + confidence calibration.

Vector search is high-recall but noisy. Production re-ranks the top candidates
with a VLM (GPT-4.1 / Gemini / Qwen-VL) that compares the query photo against
each candidate's official images and returns a calibrated match probability.

The default ``HeuristicReranker`` needs no API: it calibrates the raw cosine
similarity into a confidence and rewards agreement among a product's images
(several of a product's photos matching the query is a stronger signal than a
single lucky match).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from functools import lru_cache

from ..config import get_settings


@dataclass
class Candidate:
    product_id: int
    best_score: float  # max cosine similarity across the product's images
    scores: list[float] = field(default_factory=list)
    best_image_id: int | None = None
    confidence: float = 0.0


class Reranker(abc.ABC):
    @abc.abstractmethod
    def rerank(
        self, query_bytes: bytes, candidates: list[Candidate]
    ) -> list[Candidate]:
        """Return candidates sorted best-first with ``confidence`` set (0..1)."""


def _calibrate(cosine: float) -> float:
    """Map cosine similarity (~[-1,1]) to a 0..1 confidence.

    Cosine below ~0.5 is treated as no real signal; the band 0.5..0.95 is
    stretched across the usable confidence range.
    """
    lo, hi = 0.5, 0.95
    if cosine <= lo:
        return max(0.0, cosine) * 0.2  # small floor, clearly low
    if cosine >= hi:
        return 0.99
    return 0.2 + (cosine - lo) / (hi - lo) * 0.79


class HeuristicReranker(Reranker):
    def rerank(
        self, query_bytes: bytes, candidates: list[Candidate]
    ) -> list[Candidate]:
        for cand in candidates:
            base = _calibrate(cand.best_score)
            # Multi-image agreement bonus: extra matching images raise trust.
            strong = sum(1 for s in cand.scores if s >= 0.6)
            bonus = min(0.05 * max(0, strong - 1), 0.1)
            cand.confidence = round(min(base + bonus, 0.99), 3)
        return sorted(candidates, key=lambda c: c.confidence, reverse=True)


class VLMReranker(Reranker):
    """Placeholder for a VLM-backed reranker (GPT-4.1 / Gemini / Qwen-VL).

    Wire an actual provider call in ``_score_pair``; until then it defers to
    the heuristic so the system stays runnable.
    """

    def __init__(self) -> None:
        self._fallback = HeuristicReranker()

    def rerank(
        self, query_bytes: bytes, candidates: list[Candidate]
    ) -> list[Candidate]:
        return self._fallback.rerank(query_bytes, candidates)


@lru_cache
def get_reranker() -> Reranker:
    settings = get_settings()
    if settings.reranker_backend == "vlm":
        return VLMReranker()
    return HeuristicReranker()
