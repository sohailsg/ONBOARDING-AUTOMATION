# AI-Assisted Employee Onboarding (`onboarding/`)

Monorepo for the system defined in `onboarding_architecture_and_plan.md` and
`docs/specs/00-overview-spec.md` … `07-hardening-spec.md`.

**Stack: 100% free / local.** No Anthropic, OpenAI, Cohere, Qdrant Cloud, or any
paid API key. LLM + embeddings run on **Ollama** (local); vectors in
**Chroma (persistent, local)**; rerank is a local cross-encoder. See
`docs/STACK_DECISION_FREE.md`.

## Layout

```
onboarding/
  backend/          # W2 FastAPI gateway (02-impl)
  worker/           # W4 CrewAI plan crew (04-impl)
  rag-service/      # W3 ingestion + hybrid retrieve + rerank + answer (03-impl)
  frontend/         # W6 Next.js Hub + HR Center (06-impl)
  n8n/              # W5 Workflow A + MCP tool defs + executor config (05-impl)
  db/               # W1 Alembic migrations + seeds (01-impl)
  tests/fixtures/   # W0 mock fixtures (used by frontend MSW + backend tests)
  docs/specs/       # Part specs 00–07
  docs/implementation/  # Part implementation docs 00–07
  backend/openapi.yaml  # W0 API contract stub (§7 surface)
```

## Quick start (W1 completes the runnable stack)

```bash
cp .env.example .env            # all free/local defaults; no keys needed
make up                         # (W1) docker compose: postgres, redis, chroma, n8n, ollama
make migrate && make seed       # (W1) schema + demo data
make test                       # fixture + unit tests
```

If default ports are busy (e.g. another Postgres on 5432), override in
`.env`: `POSTGRES_PORT=5442 REDIS_PORT=6380 N8N_PORT=5679`, and point
`DATABASE_URL` / `REDIS_URL` at the same ports.

## Free-stack prerequisites

- Docker (Postgres 16, Redis 7, n8n). Chroma runs embedded/persistent — no server needed.
- [Ollama](https://ollama.com) installed + models pulled:
  ```bash
  ollama pull llama3.1:8b            # chat / agent / answer model
  ollama pull nomic-embed-text       # embeddings
  ```
  Override via `OLLAMA_CHAT_MODEL` / `OLLAMA_EMBED_MODEL` in `.env`.
- Rerank model (`sentence-transformers/ms-marco-MiniLM-L-6-v2`) downloads
  automatically on first use (HuggingFace, free). No key.
- Python 3.13 + `uv` (matches repo `pyproject.toml` / `.python-version`).

## Env files (placeholders only — you fill values last)

| File | Contains |
|---|---|
| `.env.example` | Master list, free/local defaults, empty secrets to generate |
| `backend/.env.example` | DSNs, JWT stub flag, service key ref, RAG/queue URLs |
| `worker/.env.example` | Ollama chat model, caps, Langfuse off by default |
| `rag-service/.env.example` | Ollama embed model, Chroma dir, chunk/rerank params |
| `n8n/.env.example` | Webhook HMAC ref, trigger URL, sandbox mode |
| `frontend/.env.example` | `NEXT_PUBLIC_API_URL` only — never secrets |

No `*_API_KEY` for any paid provider exists anywhere in this scaffold.
