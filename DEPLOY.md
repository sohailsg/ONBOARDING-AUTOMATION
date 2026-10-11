# Deploy Guide — onboarding (Vercel-style hosting)

Split by design: **frontend → Vercel**, **everything else → one backend host**
(Render / Railway / Fly / any VPS with Docker). All images are proven to
build and boot (see bottom). No paid LLM keys anywhere.

## Architecture on the internet

```
browser ──https──► Vercel (Next.js)
                       │  same-origin /api/* ──https──► backend host
                       │                              ├── api (FastAPI :8000)
                       │                              ├── worker (Arq plan/execute)
                       │                              ├── rag (Chroma + retrieve)
                       │                              ├── Postgres 16 + Redis 7
                       │                              └── (Ollama — GPU box only, optional)
```

The UI calls only **relative** `/api/*` URLs; Vercel rewrites them to
`INTERNAL_API_URL` (see `frontend/next.config.mjs`), so the browser never
needs backend ports or CORS entries.

## Option A — free tiers, no GPU (recommended first deploy)

Runs 100% of the product **except live-LLM generation**: retrieval +
citations + executor are real; plans come from the deterministic assembler
(same schemas, same traces, same audit). Zero cost, zero keys.

| Service | Host | Notes |
|---|---|---|
| `frontend/` | Vercel (Hobby, free) | Import repo, root dir `onboarding/frontend` |
| api + worker + rag + db + redis | Railway/Render/Fly free tier **or** `docker-compose.prod.yml` on any VPS | Postgres/Redis via host plugins or compose services |

### A1. Backend host via compose (any Docker VPS)

```bash
cd onboarding
export API_IMAGE=onboarding-backend:local RAG_IMAGE=onboarding-rag:local \
  WORKER_IMAGE=onboarding-worker:local
docker build -f Dockerfile.backend -t $API_IMAGE .
docker build -f Dockerfile.rag      -t $RAG_IMAGE .
docker build -f Dockerfile.worker   -t $WORKER_IMAGE .
export POSTGRES_PASSWORD=$(openssl rand -hex 32) \
  JWT_SECRET_GENERATED=$(openssl rand -hex 32) \
  SERVICE_API_KEY=$(openssl rand -hex 32)
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm migrate   # alembic upgrade
SEED_DEMO=1 docker compose -f docker-compose.prod.yml run --rm migrate  # demo hires only
```

Health: `GET http(s)://<api-host>/health` → `{"status":"ok"}`.

### A2. Frontend on Vercel

1. Push this repo to GitHub, import in Vercel, set **Root Directory** to
   `onboarding/frontend` (framework auto-detected: Next.js).
2. Environment variables (Production + Preview):
   - `INTERNAL_API_URL=https://<your-api-host>` ← backend public URL
   - `NEXT_PUBLIC_API_URL=` (empty = same-origin via rewrites)
   - leave `NEXT_PUBLIC_USE_MSW` **unset** (mocks off)
3. Deploy. Open `https://<your-app>.vercel.app/login`, pick a role, demo.

> Rewrites are evaluated at **build** time: set `INTERNAL_API_URL` in
> Vercel *before* the first deploy, and redeploy after changing it.

### A3. Managed Postgres/Redis instead of compose (Render/Railway)

Point the api/worker services at the managed DSNs instead of `db`/`redis`:

```bash
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>/<db>
REDIS_URL=redis://<host>:6379/0
```

Then `migrate` runs against the managed DB the same way.

## Option B — live LLM (GPU box required)

Nothing free runs an 8B crew in the 2-min DoD. On any host with a GPU
(or Apple-silicon/64GB-CPU box), add Ollama and flip two variables:

```bash
# api + worker + rag services:
OLLAMA_HOST=http://<ollama-host>:11434
OLLAMA_CHAT_MODEL=llama3.1:8b
OLLAMA_EMBED_MODEL=nomic-embed-text
# worker + rag only:
WORKER_FIXTURE_MODE=          # empty = live CrewAI crew (plan_job)
EMBEDDING_BACKEND=auto        # live embeddings w/ hash fallback
```

Verify with the strict gates (must be LLM-served, not fallback):

```bash
python scripts/worker_eval.py --n 1 --live        # expect Verdict: PASS, 1/1 LLM-served
CHROMA_DIR=./data/chroma python rag-service/scripts/seed_index.py
CHROMA_DIR=./data/chroma python rag-service/eval/evaluate.py
```

## Env reference (backend host)

| Var | Example | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` | required by prod compose |
| `JWT_SECRET_GENERATED` | `openssl rand -hex 32` | sign/verify JWTs |
| `SERVICE_API_KEY` | `openssl rand -hex 32` | n8n → trigger; HRIS HMAC peer is `WEBHOOK_HMAC_SECRET_GENERATED` |
| `JWT_DEV_STUB` | `true` (demo) / `false` (pilot+) | `false` disables `/auth/dev-login` |
| `MCP_MODE` | `sandbox` | `live` only after mapping sign-off + pilot approval |
| `SEED_DEMO` | `0` | `1` = demo hires (dev/demo only, never pilot) |

## Proof log (built + booted 2026-10-10)

- `onboarding-backend:local` — builds; `/health` ok in container.
- `onboarding-rag:local` — builds; entrypoint self-seeds 30 points on first boot.
- `onboarding-worker:local` — builds; imports ok; `arq --check` connects to Redis.
- `docker-compose.prod.yml` — `config --quiet` valid.
