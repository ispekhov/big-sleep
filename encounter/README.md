# Encounter — Product Recognition Platform (V1)

Point a camera at furniture, lighting, decor, and design objects and identify
the exact product. This package is the **V1 milestone**: brand importer,
product database, image storage, image embeddings, photo search, and a
correction/verification UI.

It runs **end-to-end with zero external services** (SQLite + local disk +
in-memory vector store + a deterministic perceptual embedder) and swaps in
production backends (Postgres, Cloudflare R2, Qdrant/pgvector, SigLIP, a VLM
reranker) purely via configuration.

## Quick start (local, no services)

```bash
cd encounter
pip install -r requirements.txt
make seed        # optional: synthetic catalogue so search has data
make dev         # http://localhost:8000  (console) + /docs (API)
```

Then: **Brand Import** a URL, **Visual Search** a photo, work the **Review
Queue**. Run `make test` for the suite (23 tests).

## Pipeline

```
Brand import:  crawl (sitemap-first) → detect product pages → extract
               (JSON-LD → OpenGraph → heuristics) → download images →
               embed → store product + images + vectors

Visual search: detect object → embed → vector search → group by product →
               VLM/heuristic rerank → calibrated confidence + similar products

Verification:  submitted → ai_validated → human_review → verified
               (only verified records are training-eligible)
```

## Layout

| Path                         | What                                             |
| ---------------------------- | ------------------------------------------------ |
| `encounter/models.py`        | Brand / Product / Variant / Image / Source ORM   |
| `encounter/importer/`        | crawler, extractor, import pipeline              |
| `encounter/embeddings/`      | perceptual fallback + SigLIP backend             |
| `encounter/vectorstore/`     | in-memory / Qdrant / pgvector backends           |
| `encounter/storage/`         | local / Cloudflare R2 / null backends            |
| `encounter/search/`          | detector, reranker, search service               |
| `encounter/api/`             | FastAPI routers                                  |
| `encounter/webui.py`         | embedded single-page console                     |

## Configuration

All via `ENCOUNTER_*` env vars (see `.env.example`): `DATABASE_URL`,
`STORAGE_BACKEND` (`local`/`r2`/`null`), `EMBEDDER_BACKEND`
(`fallback`/`siglip`), `VECTOR_BACKEND` (`memory`/`qdrant`/`pgvector`),
`RERANKER_BACKEND` (`heuristic`/`vlm`), and crawl caps.

## Deployment

See [`DEPLOY.md`](./DEPLOY.md) — the hosted "Encounter Object ID" prototype
runs on Vercel + Supabase Postgres/pgvector.

## Roadmap (per the product spec)

- **V2:** human verification queue, contributor program, dataset management,
  quality scoring, real-world capture collection.
- **V3:** training loop over official images + verified field captures +
  human corrections (better recognition / reranking / extraction).
