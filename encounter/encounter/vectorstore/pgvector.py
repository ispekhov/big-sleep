"""pgvector-backed vector store (durable, lives in the same Postgres).

This makes the platform fully stateless — ideal for serverless — because the
similarity index is in the database rather than process memory. Requires the
``vector`` extension and a table created by the migration:

    create extension if not exists vector;
    create table image_vectors (
        image_id   bigint primary key,
        product_id bigint,
        image_type text,
        embedding  vector(<dim>)
    );
    create index on image_vectors using hnsw (embedding vector_cosine_ops);

Uses raw SQL via the shared SQLAlchemy engine; no extra driver needed beyond
psycopg.
"""

from __future__ import annotations

import json

import numpy as np
from sqlalchemy import text

from ..config import get_settings
from .base import SearchHit, VectorStore


def _vec_literal(vector: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.7f}" for x in np.asarray(vector).ravel()) + "]"


class PgVectorStore(VectorStore):
    def __init__(self) -> None:
        from ..db import engine

        self._engine = engine
        self._table = get_settings().pgvector_table

    def upsert(self, image_id: int, vector: np.ndarray, payload: dict) -> None:
        stmt = text(
            f"""
            insert into {self._table} (image_id, product_id, image_type, embedding)
            values (:id, :pid, :itype, (:emb)::vector)
            on conflict (image_id) do update set
                product_id = excluded.product_id,
                image_type = excluded.image_type,
                embedding  = excluded.embedding
            """
        )
        with self._engine.begin() as conn:
            conn.execute(
                stmt,
                {
                    "id": image_id,
                    "pid": payload.get("product_id"),
                    "itype": payload.get("image_type"),
                    "emb": _vec_literal(vector),
                },
            )

    def search(self, vector: np.ndarray, top_k: int = 10) -> list[SearchHit]:
        stmt = text(
            f"""
            select image_id, product_id, image_type,
                   1 - (embedding <=> (:emb)::vector) as similarity
            from {self._table}
            order by embedding <=> (:emb)::vector
            limit :k
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(
                stmt, {"emb": _vec_literal(vector), "k": top_k}
            ).all()
        return [
            SearchHit(
                image_id=r.image_id,
                product_id=r.product_id,
                score=float(r.similarity),
                payload={"image_type": r.image_type, "product_id": r.product_id},
            )
            for r in rows
        ]

    def delete(self, image_id: int) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(f"delete from {self._table} where image_id = :id"),
                {"id": image_id},
            )

    def count(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(text(f"select count(*) from {self._table}")).scalar())
