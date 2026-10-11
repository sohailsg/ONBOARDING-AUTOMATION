# Demo Guide — AI-Assisted Employee Onboarding

Copy-paste runbook: start the stack in the terminal, then click through the
product in the browser. All commands run from `onboarding/` unless noted.

> Ports on this box: API **8003**, RAG **8004**, web **3000**, n8n **5679**,
> Postgres **5442**, Redis **6380**. (8000–8002 belong to other projects —
> do not use them.)

## 0. Public link (already live)

**https://polymer-inform-patient-postcard.trycloudflare.com**

Open it in any browser — no login needed beyond picking a role.
Serve it to anyone; the whole flow (login → pipeline → plan → approve →
hub → cited chat) works through it, verified end to end.

- It stays alive while the `onboarding-tunnel` container runs:
  `docker logs onboarding-tunnel | grep -oE 'https://[a-z0-9.-]*trycloudflare.com'`
  If the container restarts, the URL **changes** — re-run that command.
- Demo-only safeguards (do NOT pilot on this link): sign-in is the stub
  (anyone can mint `hr_admin`), and the executor runs in sandbox mode
  (fake tools, no real side effects).
- For a truly permanent address (stable across restarts + your own domain),
  create a free Cloudflare account and convert this to a named tunnel —
  ask and I'll walk you through it.
- For Vercel-style hosting (frontend on Vercel + backend on
  Render/Railway/Fly/VPS), see **DEPLOY.md** — images build, no-GPU mode
  documented, env tables included.

## 1. Terminal — verify what's already running

```bash
cd /home/ashok/Downloads/crewai_pjt/onboarding

# Infra (postgres + redis + n8n — should all say "healthy")
docker compose ps

# RAG service (expect "points":30) and API (expect {"status":"ok"})
curl -s localhost:8001/health
curl -s localhost:8003/health
```

## 2. Terminal — restart anything that's down (one terminal per service)

```bash
# --- RAG service ---
CHROMA_DIR=./data/chroma \
  python3 -m uvicorn app:app --app-dir rag-service --port 8004

# --- Backend API ---
export DATABASE_URL="postgresql+asyncpg://app:app@localhost:5442/onboarding" \
  REDIS_URL="redis://localhost:6380/0" \
  RAG_BASE_URL="http://localhost:8004" \
  JWT_DEV_STUB=true \
  SERVICE_API_KEY=$(grep SERVICE_API_KEY_GENERATED .env | cut -d= -f2)
python3 -m uvicorn backend.app.main:app --port 8003

# --- Arq worker: runs plan + execute jobs (fixture mode = fast demo plans) ---
export DATABASE_URL="postgresql+asyncpg://app:app@localhost:5442/onboarding" \
  REDIS_URL="redis://localhost:6380/0" \
  RAG_BASE_URL="http://localhost:8004" \
  WORKER_FIXTURE_MODE=1
python3 -m arq backend.app.jobs.WorkerSettings
# For REAL LLM plans instead: restart without WORKER_FIXTURE_MODE=1
# (needs Ollama llama3.1:8b; ~2 min per plan).

# --- Frontend (API URL comes from gitignored frontend/.env.local) ---
cd frontend
npm run dev -- --port 3000
```

## 3. Terminal — create a fresh hire

```bash
export SERVICE_API_KEY=$(grep SERVICE_API_KEY_GENERATED .env | cut -d= -f2)
curl -X POST localhost:8003/api/v1/onboarding/trigger \
  -H "X-Service-Key: $SERVICE_API_KEY" \
  -H "Idempotency-Key: demo-001" \
  -H 'content-type: application/json' \
  -d '{"name":"Demo Priya","role":"Backend Engineer","dept":"Engineering", \
       "region":"UK","start_date":"2026-11-01"}'
# -> 201 Created. Re-send the same command -> 200 with the SAME case
# (idempotent; duplicate keys never create a second case).
```

## 4. Browser — HR flow (`http://localhost:3000/login`, pick `hr_admin`)

1. **`/admin` pipeline table** — your new hire appears; filter by status.
   Watch it move on its own:
   `pending_ingestion → agent_processing → awaiting_hr_approval`.
2. **Open the case → Plan tab** — cited entitlements (doc + page + date),
   Day1/Week1/Month1 milestones, proposed actions. Edit if you like (PUT
   creates a new plan version + diff), then **Approve & Execute**.
3. **Trace tab** — live feed:
   `policy_retrieve → experience_plan → ops_planner → plan_ready`.
4. **Execution tab** — each action flips to `succeeded` with an
   `external_ref`; try the **Halt** button on a second run to see the
   kill switch stop remaining actions.

## 5. Browser — employee flow (login again, pick `employee` → `/hub`)

1. **Roadmap** — 30-day timeline with progress.
2. **Checklist** — tick items (optimistic; un-tick to see rollback).
3. **Policy chat** — ask *"What is my home-office budget?"* → cited answer
   with doc/page/date. Then ask *"What is the stock price today?"* →
   abstain message + HR escalation (no hallucination, still logged).

## 6. Extras

- **n8n** (`http://localhost:5679`): `intake-workflow-a` is imported —
  webhook → HMAC check → validate → trigger → backoff → DLQ inbox.
- **Proof the gates hold** (terminal, from `onboarding/`):
  ```bash
  python -m pytest tests backend/tests worker/tests rag-service/tests -q
  CHROMA_DIR=/tmp/c1 python rag-service/scripts/seed_index.py && \
    CHROMA_DIR=/tmp/c1 python rag-service/eval/evaluate.py
  python scripts/worker_eval.py --n 3 --out report.md
  cd frontend && npm test && npx playwright test
  ```
