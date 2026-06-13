"""Tune (and prove) the open-set acceptance threshold.

The recogniser only declares a match when the top candidate's calibrated
confidence clears ``ENCOUNTER_MATCH_THRESHOLD`` (see ``config.Settings`` and
``search.service``). This script measures, for the *currently configured
embedder*, how well that threshold separates:

  * **positives** — a catalogue image, queried against the rest of the index,
    should retrieve its *own* product (leave-one-out nearest neighbour); and
  * **negatives** — an image of something we do NOT index (a foreign-brand
    photo, or, lacking those, synthetic noise) should be *rejected*, not
    snapped to the nearest catalogue item.

It reuses the exact production calibration path (``HeuristicReranker`` over
hits grouped by product), sweeps thresholds, and recommends the lowest one
that accepts correct matches while keeping false accepts at zero.

Workflow for the Roll & Hill pilot::

    # 1. import just Roll & Hill, then:
    python -m encounter.eval.threshold --brand "Roll & Hill"
    # with real foreign photos to harden the negative side:
    python -m encounter.eval.threshold --brand "Roll & Hill" --negatives ./foreign

The methodology is embedder-agnostic: it characterises whatever
``ENCOUNTER_EMBEDDER_BACKEND`` is set (deterministic ``fallback`` out of the
box, ``siglip`` on a GPU host).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import session_scope
from ..embeddings import get_embedder
from ..enums import ImageType
from ..models import Brand, Image, Product
from ..search.reranker import Candidate, HeuristicReranker


@dataclass
class IndexedImage:
    image_id: int
    product_id: int
    vector: np.ndarray


def _load_catalogue(session, brand: str | None) -> list[IndexedImage]:
    """All non-query catalogue images (with embeddings) for live products."""
    stmt = (
        select(Image)
        .join(Product, Image.product_id == Product.id)
        .where(
            Image.product_id.is_not(None),
            Image.embedding.is_not(None),
            Image.image_type != ImageType.user_query_image,
            Product.deleted_at.is_(None),
        )
        .options(selectinload(Image.product))
    )
    if brand:
        stmt = stmt.join(Brand, Product.brand_id == Brand.id).where(
            Brand.name == brand
        )
    out: list[IndexedImage] = []
    for img in session.scalars(stmt):
        out.append(
            IndexedImage(
                image_id=img.id,
                product_id=img.product_id,
                vector=np.asarray(img.embedding, dtype=np.float32),
            )
        )
    return out


def _rank(query: np.ndarray, index: list[IndexedImage], *, exclude_image_id: int,
          top_k: int, reranker: HeuristicReranker) -> tuple[int | None, float]:
    """Replicate the service: vector search -> group by product -> calibrate.

    Returns ``(predicted_product_id, confidence)`` for the best candidate, or
    ``(None, 0.0)`` when nothing is retrievable.
    """
    scored = [
        (it, float(np.dot(query, it.vector)))
        for it in index
        if it.image_id != exclude_image_id
    ]
    if not scored:
        return None, 0.0
    scored.sort(key=lambda t: t[1], reverse=True)
    hits = scored[:top_k]

    by_product: dict[int, Candidate] = {}
    for it, score in hits:
        cand = by_product.get(it.product_id)
        if cand is None:
            cand = Candidate(product_id=it.product_id, best_score=score)
            by_product[it.product_id] = cand
        cand.scores.append(score)
        cand.best_score = max(cand.best_score, score)
    ranked = reranker.rerank(b"", list(by_product.values()))
    top = ranked[0]
    return top.product_id, top.confidence


def _load_negatives(neg_dir: Path | None, embedder, count: int) -> list[np.ndarray]:
    """Foreign-image query vectors. Real photos if given, else synthetic."""
    vecs: list[np.ndarray] = []
    if neg_dir is not None:
        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        files = sorted(p for p in neg_dir.rglob("*") if p.suffix.lower() in exts)
        for p in files:
            try:
                vecs.append(embedder.embed(p.read_bytes()))
            except Exception as exc:  # skip unreadable files
                print(f"  ! skipped {p.name}: {exc}", file=sys.stderr)
        return vecs

    # Synthetic fallback: random-noise JPEGs. A weak proxy for true negatives
    # (real foreign photos via --negatives are strongly preferred), but enough
    # to expose a threshold that accepts everything.
    import io

    from PIL import Image as PILImage

    rng = np.random.default_rng(20240613)
    for _ in range(count):
        arr = rng.integers(0, 256, size=(128, 128, 3), dtype=np.uint8)
        buf = io.BytesIO()
        PILImage.fromarray(arr, "RGB").save(buf, format="JPEG", quality=88)
        vecs.append(embedder.embed(buf.getvalue()))
    return vecs


def evaluate(brand: str | None, neg_dir: Path | None, top_k: int) -> int:
    embedder = get_embedder()
    reranker = HeuristicReranker()

    with session_scope() as session:
        index = _load_catalogue(session, brand)

    scope = f'brand "{brand}"' if brand else "full catalogue"
    if len(index) < 2:
        print(
            f"Not enough indexed images for {scope} "
            f"({len(index)} found). Import a catalogue first.",
            file=sys.stderr,
        )
        return 1

    n_products = len({it.product_id for it in index})
    print(f"Embedder      : {embedder.name} (dim={embedder.dim})")
    print(f"Scope         : {scope}")
    print(f"Indexed images: {len(index)}  across {n_products} products\n")

    # Warn on embedder mismatch: positives use stored embeddings, negatives are
    # embedded now — they must come from the same model to be comparable.
    with session_scope() as session:
        models = {
            m for (m,) in session.execute(
                select(Image.embedding_model).where(
                    Image.product_id.is_not(None),
                    Image.embedding_model.is_not(None),
                )
            ).all()
        }
    if models and embedder.name not in models:
        print(
            f"WARNING: stored embeddings were made by {sorted(models)} but the "
            f"configured embedder is '{embedder.name}'. Re-index before tuning "
            f"(set ENCOUNTER_EMBEDDER_BACKEND to match), or the numbers below "
            f"are meaningless.\n",
            file=sys.stderr,
        )

    # --- Positives --------------------------------------------------------
    # Leave-one-out only makes sense for products with >= 2 images (you need
    # one to query and one to retrieve). When every product has a single image
    # leave-one-out is structurally impossible, so we fall back to self-match
    # (the indexed image queries itself): that measures the accept ceiling and
    # the true-match confidence distribution, but not generalisation to a new
    # photo. Real field photos via --negatives harden the reject side; multi-
    # image products are what exercise the accept side properly.
    from collections import Counter

    per_product = Counter(it.product_id for it in index)
    multi = [it for it in index if per_product[it.product_id] >= 2]
    if multi:
        eval_set, exclude_self = multi, True
        pos_mode = "leave-one-out (generalises to a different photo)"
        skipped = len(index) - len(multi)
    else:
        eval_set, exclude_self = index, False
        pos_mode = "self-match (accept ceiling; every product has one image)"
        skipped = 0

    pos_conf: list[float] = []
    pos_correct: list[bool] = []
    for q in eval_set:
        pid, conf = _rank(
            q.vector, index,
            exclude_image_id=q.image_id if exclude_self else -1,
            top_k=top_k, reranker=reranker,
        )
        pos_conf.append(conf)
        pos_correct.append(pid == q.product_id)
    print(f"Positives     : {len(eval_set)} queries, {pos_mode}")
    if skipped:
        print(f"                ({skipped} single-image products skipped)")

    # --- Negatives: foreign images should be rejected ---------------------
    neg_vecs = _load_negatives(neg_dir, embedder, count=max(20, n_products))
    neg_conf: list[float] = []
    for v in neg_vecs:
        _, conf = _rank(
            v, index, exclude_image_id=-1, top_k=top_k, reranker=reranker,
        )
        neg_conf.append(conf)

    pos_conf_a = np.asarray(pos_conf)
    pos_correct_a = np.asarray(pos_correct, dtype=bool)
    neg_conf_a = np.asarray(neg_conf)
    neg_kind = "real" if neg_dir is not None else "synthetic"

    top1 = float(pos_correct_a.mean()) if len(pos_correct_a) else 0.0
    print(f"Top-1 product accuracy (ignoring threshold): {top1*100:.1f}%")
    print(f"Negatives                                  : {len(neg_conf_a)} ({neg_kind})\n")

    # --- Threshold sweep --------------------------------------------------
    print(f"{'thresh':>7} {'recall':>8} {'precision':>10} {'false-accept':>13}")
    print("-" * 42)
    best_t, best_recall = None, -1.0
    for t in np.round(np.arange(0.30, 0.96, 0.05), 2):
        accepted = pos_conf_a >= t
        correct_accept = accepted & pos_correct_a
        recall = float(correct_accept.sum()) / len(pos_conf_a)
        precision = (
            float(correct_accept.sum()) / float(accepted.sum())
            if accepted.any() else 1.0
        )
        false_accept = (
            float((neg_conf_a >= t).mean()) if len(neg_conf_a) else 0.0
        )
        flag = ""
        # Recommend the lowest threshold with zero false accepts that still
        # keeps the best recall among such thresholds.
        if false_accept == 0.0 and recall > best_recall:
            best_recall, best_t = recall, float(t)
            flag = "  <-"
        print(
            f"{t:>7.2f} {recall*100:>7.1f}% {precision*100:>9.1f}% "
            f"{false_accept*100:>12.1f}%{flag}"
        )

    print()
    if best_t is None:
        print(
            "No threshold fully separates positives from negatives with this "
            "embedder. The deterministic 'fallback' embedder is not expected "
            "to — switch ENCOUNTER_EMBEDDER_BACKEND=siglip on a GPU host and "
            "re-run. (Recommend a high threshold meanwhile.)"
        )
    else:
        print(
            f"Recommended ENCOUNTER_MATCH_THRESHOLD={best_t:.2f}  "
            f"(recall {best_recall*100:.1f}%, zero false accepts on "
            f"{len(neg_conf_a)} {neg_kind} negatives)"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m encounter.eval.threshold",
        description="Tune the open-set acceptance threshold for the "
                    "configured embedder.",
    )
    parser.add_argument(
        "--brand", default=None,
        help='Scope to one brand (e.g. "Roll & Hill"). Default: full catalogue.',
    )
    parser.add_argument(
        "--negatives", type=Path, default=None,
        help="Directory of foreign images (not in the catalogue) used as "
             "negatives. Strongly recommended; falls back to synthetic noise.",
    )
    parser.add_argument(
        "--top-k", type=int, default=10,
        help="Hits to retrieve before grouping/reranking (default: 10).",
    )
    args = parser.parse_args(argv)
    return evaluate(args.brand, args.negatives, args.top_k)


if __name__ == "__main__":
    raise SystemExit(main())
