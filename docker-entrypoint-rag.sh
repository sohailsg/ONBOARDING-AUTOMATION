#!/bin/sh
# RAG entrypoint: seed the index when empty (idempotent upserts make this
# safe on every start, including ephemeral disks), then serve.
set -eu

SEED_MANIFEST="/srv/rag/seeds/manifest.json"
if [ -f "$SEED_MANIFEST" ]; then
  echo "entrypoint: ensuring seed index in $CHROMA_DIR ..."
  python3 /srv/rag/scripts/seed_index.py || echo "entrypoint: seed skipped (index may already exist)"
else
  echo "entrypoint: no seeds bundled, serving existing index"
fi

exec python3 -m uvicorn app:app --app-dir /srv/rag --host 0.0.0.0 --port "${RAG_PORT:-8001}"
