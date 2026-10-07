# Stack Decision (FREE-ONLY) — binding for implementations 0–7

User constraint: **no Anthropic or paid API keys; everything free; Ollama;
no Qdrant (perceived paid).**

## Substitutions (spec → implementation)

| Spec / plan says | Implementation uses | Why free |
|---|---|---|
| Claude Sonnet-tier (`ANTHROPIC_MODEL`) | **Ollama chat** `OLLAMA_CHAT_MODEL=llama3.1:8b` (overridable) | Local, $0 |
| OpenAI `text-embedding-3-small` | **Ollama embeddings** `OLLAMA_EMBED_MODEL=nomic-embed-text` | Local, $0 |
| Qdrant hybrid (dense + BM25/BM42, RRF) | **Chroma persistent local** (`CHROMA_DIR`, collection `policies_v1`) + app-level BM25 fuse + RRF in `rag-service` | Embedded/file, $0, no server or cloud |
| Cohere Rerank | **Local cross-encoder** `RERANK_MODEL=sentence-transformers/ms-marco-MiniLM-L-6-v2` | HuggingFace weights, $0 |
| Qdrant Cloud / managed options | Not used | — |
| SSO provider | **JWT dev stub** (`JWT_DEV_STUB=true`) behind `AuthProvider` interface; real OIDC later without route changes | $0 |
| Sentry / Langfuse / OTel vendor | Wired but **empty by default**; all have free/self-host tiers, enabled in W7 only | $0 until then |

## What stays identical

Flows A/B/C, HITL approval gate, deterministic executor, idempotency keys,
status enum, 8-table data model, §7 API surface, SSE-only traces,
read-only-tools-in-planning rule, citations + abstain path, RAGAS ≥ 0.9 gate
(RAGAS runs against local Ollama — slower but free).

## Consequences (accepted)

- Answer/plan quality below Sonnet-tier; eval thresholds stay, prompts get
  simpler instructions + stricter context-only decoding.
- Local rerank + Ollama embeddings: recall tuning happens on chunk sizes
  (1024/256) and `HYBRID_TOP_K/RERANK_TOP_K`, not on vendor upgrades.
- Hardware: Ollama needs local RAM/GPU; CI uses fixtures + tiny local models,
  full RAGAS nightly only.
- Chroma replaces Qdrant payload filters 1:1 (`region, department,
  page_number, effective_date, superseded_by, version` stored as metadata).

## Placeholders

`.env.example` files contain **zero paid keys**. `*_GENERATED` values
(service key, webhook HMAC, JWT secret) are created locally with
`openssl rand -hex 32` at deploy time — user provides nothing purchased.
