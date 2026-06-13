"""End-to-end visual search service."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..embeddings import Embedder, get_embedder
from ..enums import ImageType, SourceType, VerificationStatus
from ..models import Image, Product, Source
from ..schemas import SearchCandidate, SearchResponse
from ..storage import ObjectStorage, get_storage
from ..vectorstore import VectorStore, get_vector_store
from .detector import ObjectDetector, get_detector
from .reranker import Candidate, Reranker, get_reranker


class SearchService:
    def __init__(
        self,
        session: Session,
        *,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        detector: ObjectDetector | None = None,
        reranker: Reranker | None = None,
        storage: ObjectStorage | None = None,
    ) -> None:
        self.session = session
        self.embedder = embedder or get_embedder()
        self.vector_store = vector_store or get_vector_store()
        self.detector = detector or get_detector()
        self.reranker = reranker or get_reranker()
        self.storage = storage or get_storage()
        self.settings = get_settings()

    def search(
        self, image_bytes: bytes, *, store_query: bool = True
    ) -> SearchResponse:
        settings = self.settings

        # 1) Detect the object (whole-image fallback) and use the top region.
        detections = self.detector.detect(image_bytes)
        target = detections[0].image_bytes if detections else image_bytes

        # 2) Embed + 3) vector search.
        query_vec = self.embedder.embed(target)
        hits = self.vector_store.search(query_vec, top_k=settings.search_top_k)

        # 4) Persist the query image (provenance for future training).
        query_image_id = (
            self._store_query_image(image_bytes, query_vec)
            if store_query
            else -1
        )

        if not hits:
            return SearchResponse(query_image_id=query_image_id)

        # 5) Group hits per product, keep best score + scores per product.
        by_product: dict[int, Candidate] = {}
        for hit in hits:
            pid = hit.product_id
            if pid is None:
                continue
            cand = by_product.get(pid)
            if cand is None:
                cand = Candidate(product_id=pid, best_score=hit.score)
                by_product[pid] = cand
            cand.scores.append(hit.score)
            if hit.score >= cand.best_score:
                cand.best_score = hit.score
                cand.best_image_id = hit.image_id

        # 6) Rerank (VLM in prod) + calibrate confidence.
        ranked = self.reranker.rerank(image_bytes, list(by_product.values()))
        ranked = ranked[: settings.search_rerank_k]

        candidates = [self._to_candidate(c) for c in ranked]
        candidates = [c for c in candidates if c is not None]
        if not candidates:
            return SearchResponse(query_image_id=query_image_id)

        top = candidates[0]
        similar = self._similar_products(top.product_id, exclude=top.product_id)
        return SearchResponse(
            query_image_id=query_image_id,
            top_candidate=top,
            candidates=candidates,
            similar_products=similar,
        )

    # --- helpers ----------------------------------------------------------
    def _to_candidate(self, cand: Candidate) -> SearchCandidate | None:
        product = self.session.scalar(
            select(Product)
            .where(Product.id == cand.product_id, Product.deleted_at.is_(None))
            .options(selectinload(Product.brand), selectinload(Product.images))
        )
        if product is None:
            return None
        image_urls = [img.image_url for img in product.images]
        matched_url = None
        if cand.best_image_id is not None:
            matched = self.session.get(Image, cand.best_image_id)
            matched_url = matched.image_url if matched else None
        return SearchCandidate(
            product_id=product.id,
            brand=product.brand.name if product.brand else "",
            product_name=product.name,
            category=product.category,
            price=product.price,
            currency=product.currency,
            description=product.description,
            confidence=cand.confidence,
            matched_image_url=matched_url or (image_urls[0] if image_urls else None),
            images=image_urls,
        )

    def _similar_products(
        self, product_id: int, exclude: int, limit: int = 4
    ) -> list[SearchCandidate]:
        """Products sharing brand/category — a simple V1 'similar' heuristic."""
        product = self.session.get(Product, product_id)
        if product is None:
            return []
        stmt = (
            select(Product)
            .where(
                Product.id != exclude,
                Product.brand_id == product.brand_id,
                Product.deleted_at.is_(None),
            )
            .options(selectinload(Product.brand), selectinload(Product.images))
            .limit(limit)
        )
        if product.category:
            stmt = stmt.where(Product.category == product.category)
        rows = self.session.scalars(stmt).all()
        out = []
        for p in rows:
            urls = [img.image_url for img in p.images]
            out.append(
                SearchCandidate(
                    product_id=p.id,
                    brand=p.brand.name if p.brand else "",
                    product_name=p.name,
                    category=p.category,
                    price=p.price,
                    currency=p.currency,
                    description=p.description,
                    confidence=0.0,
                    matched_image_url=urls[0] if urls else None,
                    images=urls,
                )
            )
        return out

    def _store_query_image(self, image_bytes: bytes, vector) -> int:
        import hashlib

        source = self.session.scalar(
            select(Source).where(
                Source.type == SourceType.user_upload, Source.name == "user_upload"
            )
        )
        if source is None:
            source = Source(type=SourceType.user_upload, name="user_upload")
            self.session.add(source)
            self.session.flush()

        digest = hashlib.sha256(image_bytes).hexdigest()[:24]
        key = f"queries/{digest}.jpg"
        url = self.storage.put(key, image_bytes, "image/jpeg")
        image = Image(
            product_id=None,
            source_id=source.id,
            image_url=url,
            storage_key=key,
            image_type=ImageType.user_query_image,
            embedding=[float(x) for x in vector.tolist()],
            embedding_model=self.embedder.name,
            verification_status=VerificationStatus.submitted,
        )
        self.session.add(image)
        self.session.commit()
        return image.id
