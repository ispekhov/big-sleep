#!/usr/bin/env bash
#
# SigLIP CPU proof-of-concept for the Encounter recognizer.
# ---------------------------------------------------------
# Runs the REAL vision model on any host with internet — no GPU required.
# It is slow (a few seconds per image on CPU), but it actually recognises
# real-world photos against the Roll & Hill catalogue, which the zero-dependency
# `fallback` embedder cannot.
#
# What it does:
#   1. creates an isolated venv and installs deps incl. CPU torch + transformers
#   2. configures the app to use SigLIP + a clean local SQLite/disk datastore
#   3. downloads the SigLIP weights once and verifies the embedder loads
#
# Then you import Roll & Hill, tune the threshold, and test in the browser —
# the script prints those final steps. Re-run is safe (idempotent).
#
# Usage:  bash scripts/siglip_poc.sh
#
set -euo pipefail
cd "$(dirname "$0")/.."   # repo's encounter/ directory

VENV=".venv-siglip"

echo "==> 1/3  Python env + dependencies (CPU torch, this can take a few minutes)"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q "torch>=2.2" "transformers>=4.40"

echo "==> 2/3  Configure the real model + a clean local datastore"
export ENCOUNTER_EMBEDDER_BACKEND=siglip
export ENCOUNTER_EMBEDDING_DIM=768          # siglip-base hidden size
export ENCOUNTER_VECTOR_BACKEND=memory
export ENCOUNTER_STORAGE_BACKEND=local
export ENCOUNTER_DATABASE_URL="sqlite:///$(pwd)/var/siglip_poc.db"
mkdir -p var

echo "==> 3/3  Download SigLIP weights (~0.4 GB, once) and verify"
python - <<'PY'
from encounter.embeddings import get_embedder
e = get_embedder()
print(f"    SigLIP ready: {e.name}, dim={e.dim}")
PY

cat <<EOF

Setup done. The real recognizer is configured. Finish in this same shell so the
env vars stay set:

  # A) start the app
  source $VENV/bin/activate
  export ENCOUNTER_EMBEDDER_BACKEND=siglip ENCOUNTER_EMBEDDING_DIM=768 \\
         ENCOUNTER_VECTOR_BACKEND=memory ENCOUNTER_STORAGE_BACKEND=local \\
         ENCOUNTER_DATABASE_URL="sqlite:///\$(pwd)/var/siglip_poc.db"
  uvicorn encounter.main:app --port 8000        # open http://localhost:8000

  # B) Brand Import tab -> paste the Roll & Hill URL -> wait for the import
  #    (images are SigLIP-fingerprinted as they import — slow on CPU, that's fine)
  #
  #    Already have Roll & Hill in another DB? Skip the import and instead run:
  #    python -m encounter.reindex --embed --brand "Roll & Hill"
  #    (re-fingerprints existing products by fetching their image URLs)

  # C) pick a threshold from real separation numbers
  python -m encounter.eval.threshold --brand "Roll & Hill"
  #    then restart uvicorn with e.g.  ENCOUNTER_MATCH_THRESHOLD=0.45

  # D) Visual Search tab -> upload a REAL photo of a Roll & Hill product
  #    -> it should identify it; a photo of anything else -> "no match".
EOF
