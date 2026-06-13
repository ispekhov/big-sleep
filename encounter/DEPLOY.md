# Deploying the Encounter Object ID web interface

A standalone prototype of the broader Encounter platform: enter a brand URL,
it crawls/extracts products, then you upload a photo and it identifies the
product. Runs as a Python (FastAPI) app on **Vercel**, backed by **Supabase
Postgres + pgvector**.

> The database is already provisioned (see "What's already set up"). The only
> remaining step is connecting Vercel and setting one secret env var.

## Architecture (hosted prototype)

| Concern        | Hosted choice                                              |
| -------------- | ---------------------------------------------------------- |
| API + UI       | FastAPI on Vercel Python serverless (`api/index.py`)       |
| Database       | Supabase Postgres, isolated `object_id` schema             |
| Vector search  | `pgvector` (durable; stateless across invocations)         |
| Images         | Referenced by original brand/CDN URL (not re-hosted)       |
| Embeddings     | Deterministic **perceptual** embedder (no GPU/model)       |
| Object detect  | Whole-image (Grounding DINO/Florence-2 are prod upgrades)  |
| Reranker       | Heuristic confidence calibration (VLM is a prod upgrade)   |

The perceptual embedder is a real visual descriptor (similar images → nearby
vectors) so search works end-to-end, but it is a **baseline** — production
recognition accuracy needs SigLIP/DINOv2 on a GPU host plus a VLM reranker.

## Recognition accuracy & the match threshold

The recogniser does **open-set recognition**: it only declares a match when the
top candidate's calibrated confidence clears `ENCOUNTER_MATCH_THRESHOLD`
(default `0.6`). Below it, search returns *no confident match* and the UI asks
the user to label the photo — instead of snapping every photo to the nearest
catalogue item. This is what makes a single-brand index behave correctly:

- Photograph an **indexed** product → it matches.
- Photograph **anything else** → "no match", not a false positive.

A nearest-neighbour search always returns *something*, so this threshold — not
the index — is what rejects out-of-catalogue photos. Two levers set how well it
works:

1. **Embedder.** The deterministic `fallback` embedder needs a very high
   threshold to reject foreign images and still generalises poorly to new
   photos of the same object. For production accuracy, run **SigLIP** on a GPU
   host: `pip install "torch>=2.2" "transformers>=4.40"`, set
   `ENCOUNTER_EMBEDDER_BACKEND=siglip`, and **re-index** (embeddings from a
   different model are not comparable). SigLIP runs on CPU too, just slowly —
   fine for a pilot, too slow for serverless request latency at scale.
2. **Threshold.** Tune it per embedder with the eval harness:

   ```bash
   # Roll & Hill pilot: import just Roll & Hill first, then
   python -m encounter.eval.threshold --brand "Roll & Hill"
   # harden the reject side with real out-of-catalogue photos:
   python -m encounter.eval.threshold --brand "Roll & Hill" --negatives ./foreign
   ```

   It sweeps thresholds over **positives** (catalogue images retrieving their
   own product — leave-one-out for multi-image products, self-match otherwise)
   and **negatives** (foreign photos via `--negatives`, else synthetic noise),
   prints recall / precision / false-accept per threshold, and recommends the
   lowest threshold with zero false accepts. Set that as
   `ENCOUNTER_MATCH_THRESHOLD`.

Acceptance test for the pilot: index only Roll & Hill, then a real Roll & Hill
photo should be identified and any non-Roll & Hill photo should return "no
match".

## What's already set up (Supabase project `encounter`, eu-north-1)

Co-located in the existing `encounter` project under an **isolated schema** so
nothing else is touched:

- schema `object_id`
- `vector` extension enabled
- table `object_id.image_vectors` + HNSW cosine index (dim 512)
- dedicated login role `objectid_app` scoped to `object_id` only
  (no access to any other tables in the database)

The app creates its remaining tables (`brands`, `products`, `images`, …) in
`object_id` automatically on first boot.

## Step 1 — set the database URL (secret)

In the Vercel project, add an Environment Variable:

- **Name:** `ENCOUNTER_DATABASE_URL`
- **Value:** the Supabase **Transaction pooler** connection string for the
  `objectid_app` role, in SQLAlchemy form:

  ```
  postgresql+psycopg://objectid_app.<PROJECT_REF>:<PASSWORD>@<POOLER_HOST>:6543/postgres
  ```

  Grab the exact `<POOLER_HOST>` from **Supabase → Project → Connect →
  Transaction pooler** (it already shows the `…pooler.supabase.com` host and
  the `:6543` port), then swap the username to `objectid_app.<PROJECT_REF>`
  and use the `objectid_app` password. The password was generated during
  setup and shared separately — never commit it.

All non-secret config (pgvector backend, null storage, remote images,
serverless DB mode, crawl caps) is baked into `api/index.py`.

## Step 2 — deploy

**Option A — Vercel dashboard (git integration, recommended):**

1. Vercel → Add New → Project → Import `ispekhov/big-sleep`.
2. Project name: `encounter-object-id`. Framework Preset: **Other**.
   Root Directory: repo root (leave default).
3. Production Branch: `claude/encounter-product-recognition-mr71pu`
   (or merge this branch to `main` first).
4. Add the env var from Step 1, then Deploy.

**Option B — Vercel CLI:**

```bash
git checkout claude/encounter-product-recognition-mr71pu
npm i -g vercel
vercel link            # create project "encounter-object-id"
vercel env add ENCOUNTER_DATABASE_URL production   # paste the URL from Step 1
vercel deploy --prod
```

## Step 3 — try it

- Open the deployment URL → the **Encounter** console loads.
- `GET /health` → `database_connected: true` once the env var is set.
- **Brand Import** tab → paste a real brand URL (e.g. `https://www.tomdixon.net`).
  The crawler uses the sitemap first and is bounded by `maxDuration` (60s);
  raise `ENCOUNTER_CRAWL_MAX_PAGES` / Vercel plan limits for larger catalogues.
- **Visual Search** tab → upload a photo → ranked matches + confidence.
- **Review Queue** tab → fix importer-flagged products.

## Notes / tuning

- **Function timeout:** crawling is bounded by Vercel's `maxDuration`
  (`vercel.json` sets 60s). Large brands import partially within the budget —
  call import again or raise the cap on a paid plan / a long-running host.
- **Custom role over the pooler:** if `objectid_app` fails to authenticate via
  the transaction pooler, use the Session pooler URI from the dashboard (same
  swap of username/password), which also speaks IPv4.
- **Local dev** still runs with zero external services — see `README` /
  `make dev` (SQLite + in-memory vectors + local disk + perceptual embedder).
