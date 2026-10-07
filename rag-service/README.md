# RAG service (W3, impl 03) — free/local stack

Ollama embeddings + Chroma-local vectors + local rerank. No paid keys.
Spec: `docs/specs/03-rag-service-spec.md` · Plan: `docs/implementation/03-rag-service-impl.md`
· Free-stack substitutions: `docs/STACK_DECISION_FREE.md`.

## Layout

```
rag-service/
  app.py            FastAPI: /health /retrieve /answer /chat /rag/reindex (+ /api/v1/admin/reindex alias)
  config.py         env-driven settings (model strings, chunk sizes, thresholds)
  models.py         pydantic schemas (mirrors backend/openapi Chat*)
  chunking.py       parent (~1024 tok) / child (~256 tok) chunker, page-preserving (3.1)
  embeddings.py     Ollama embeddings + deterministic hash fallback (EMBEDDING_BACKEND=auto|ollama|hash)
  bm25.py           pure-python Okapi BM25 + RRF fusion (sparse side of hybrid)
  vector_store.py   Chroma persistent-local `policies_v1` + code-enforced filters (F-RAG-2)
  ingest.py         PDF/TXT/MD → chunks → embed → idempotent upsert (3.1)
  retrieve.py       pre-filter → dense+BM25 → RRF → rerank → top-5 → parent-expand (3.2)
  rerank.py         cross-encoder when installed, else BM25+cosine blend fallback
  answer.py         context-only answer, citations, confidence, abstain (3.3)
  lifecycle.py      version bump via superseded_by, never delete (3.4)
  cache.py          (role,region) entitlement TTL cache: Redis if REDIS_URL else local (3.6)
  observability.py  per-query log (latency/scores/confidence/cost=0) + Langfuse stub, off by default (3.6)
  seeds/            4 sample policies (PDF+TXT+manifest) across UK/US/DE/IN
  eval/             golden_set.json (106 Q&A) + evaluate.py gate (Faithfulness ≥ 0.9) (3.5)
  scripts/          seed_index.py (load seeds into Chroma)
  tests/            unit + integration (hash backend, isolated collections per test)
```

## Quick start

```bash
pip install -r rag-service/requirements.txt
python rag-service/seeds/seed_policies.py                 # (re)generate seed PDFs
CHROMA_DIR=./data/chroma python rag-service/scripts/seed_index.py
CHROMA_DIR=./data/chroma uvicorn app:app --app-dir rag-service --port 8001
curl -X POST localhost:8001/chat \
  -H 'content-type: application/json' \
  -d '{"question":"What is my remote home-office budget in the UK?","region":"UK","dept":"all"}'
```

Without Ollama running, `EMBEDDING_BACKEND=hash` (or default `auto` fallback)
keeps ingest/retrieve/answer fully working offline; answer LLM falls back to
extractive mode when the chat model is unreachable.

## Chunk IDs and versions

IDs are deterministic per version — `{doc}:v{n}:{page}:{child}`
(parents `{doc}:v{n}:{page}:p{i}`). Re-ingesting the same version is an
idempotent upsert; a new version coexists under new IDs while the old points
are marked `superseded_by` (never deleted, excluded from queries in code).

## Filters (enforced in code, never in the prompt)

`region == user.region AND (dept == all OR == user.dept)
AND effective_date <= today AND superseded_by IS NULL`

## Eval gate

```bash
python rag-service/eval/evaluate.py --llm extractive   # exit 1 if Faithfulness < 0.9
```

CI: PRs run unit tests (hash backend); main + nightly seed a fresh index and
run the full 106-item gate — deploy is blocked on failure.
