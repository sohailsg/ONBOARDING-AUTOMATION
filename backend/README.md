# Backend gateway (W2, spec 02) — implemented

Stateless FastAPI gateway: auth/RBAC, §7 REST + SSE, Arq enqueue, audit. No LLM/agent logic.

## Layout

```
app/
  main.py            # create_app(), /health, /metrics (07), lifespan (OTel/Sentry, create_all)
  config.py          # pydantic-settings (DATABASE_URL, REDIS_URL, RAG_BASE_URL, JWT_*, SERVICE_API_KEY)
  db.py              # async engine/session (asyncpg Postgres; aiosqlite for dev/tests)
  models.py          # mirrors 01 tables; owns status machine + can_transition()
  schemas.py         # Pydantic v2 request/response models
  auth.py            # AuthProvider-compatible JWT/dev-stub + require_roles()
  audit.py           # append-only audit_events writer (+ SSE fan-out)
  jobs.py            # Arq enqueue w/ inline fallback; DLQ helpers (07); worker entrypoints
  sse.py             # trace:{session_id} in-memory bus + redis pub/sub bridge
  ratelimit.py       # slowapi limiter (chat 30/min, trigger 60/min, reindex 2/hr)
  metrics.py         # RED latency series + Prometheus render (07)
  routers/
    onboarding.py    # POST /api/v1/onboarding/trigger (service, Idempotency-Key)
    cases.py         # GET /cases?status=&page= ; GET /cases/{id}/stream (SSE + replay)
    plans.py         # GET/PUT /cases/{id}/plan (version bump + diff in audit)
    approvals.py     # POST /approvals/{plan_id} (approve→enqueue execute)
    me.py            # GET /me/roadmap ; PATCH /me/checklist/{id} (row scoping)
    chat.py          # POST /chat (server-side profile → RAG → chat_logs, abstain)
    admin.py         # POST /admin/reindex + audit/readiness/DLQ (07)
    execute.py       # POST /execute/{case_id}/halt (05 kill switch)
tools/gen_types.py   # OpenAPI -> TS codegen for frontend (`make gen-api`)
tests/test_gateway.py# 18 tests: RBAC matrix, idempotency, SSE reconnect (live server),
                     # plan/approval, row scoping, chat abstain, OpenAPI surface
requirements.txt
openapi.yaml         # §7 contract (frontend codegen input)
```

## Run / test

```bash
uvicorn onboarding.backend.app.main:app --port 8000
python -m pytest onboarding/backend/tests -q   # sqlite memory/file, no external services
python onboarding/backend/tools/gen_types.py --spec onboarding/backend/openapi.yaml \
  --out onboarding/frontend/lib/api.types.ts
```

SSE notes: `GET /cases/{id}/stream` replays last-N `audit_events` for the case
session (`?last_n=`, `?last_event_id=`) then fans out live `trace:{session_id}`
events with 15 s heartbeats. `?token=` query fallback exists for EventSource
clients that can't set headers.
