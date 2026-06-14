"""Tests for the threshold-tuning harness core (encounter.eval.threshold)."""

from __future__ import annotations

import numpy as np

from encounter.eval.threshold import IndexedImage, _rank
from encounter.search.reranker import HeuristicReranker


def _unit(*xs: float) -> np.ndarray:
    v = np.asarray(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def _index() -> list[IndexedImage]:
    # Two products, two images each, in well-separated directions.
    return [
        IndexedImage(image_id=1, product_id=10, vector=_unit(1, 0, 0)),
        IndexedImage(image_id=2, product_id=10, vector=_unit(0.96, 0.1, 0.0)),
        IndexedImage(image_id=3, product_id=20, vector=_unit(0, 1, 0)),
        IndexedImage(image_id=4, product_id=20, vector=_unit(0.1, 0.96, 0.0)),
    ]


def test_rank_leave_one_out_retrieves_same_product():
    index = _index()
    rr = HeuristicReranker()
    # Query with image 1 (product 10), excluding itself -> image 2 (product 10).
    pid, conf = _rank(index[0].vector, index, exclude_image_id=1, top_k=10, reranker=rr)
    assert pid == 10
    assert conf > 0.5


def test_rank_self_match_is_top_at_full_confidence():
    index = _index()
    rr = HeuristicReranker()
    pid, conf = _rank(index[0].vector, index, exclude_image_id=-1, top_k=10, reranker=rr)
    assert pid == 10
    assert conf >= 0.99  # exact self-match calibrates to the ceiling


def test_rank_foreign_query_has_low_confidence():
    index = _index()
    rr = HeuristicReranker()
    # Orthogonal to everything indexed -> nearest cosine ~0 -> rejected.
    pid, conf = _rank(_unit(0, 0, 1), index, exclude_image_id=-1, top_k=10, reranker=rr)
    assert conf < 0.2  # below any sane acceptance threshold


def test_rank_empty_index():
    rr = HeuristicReranker()
    pid, conf = _rank(_unit(1, 0, 0), [], exclude_image_id=-1, top_k=10, reranker=rr)
    assert pid is None and conf == 0.0
