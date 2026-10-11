# Deploy Plan — Vercel (frontend) + Google backend, executed with Claude Code

**Goal:** production-like public deployment of this monorepo with **zero replatforming**:
the Python backend/RAG/worker ship as containers, Postgres stays Postgres,
and only auth changes shape (Firebase Auth replaces the JWT dev stub).

> Why not Firestore/Functions? The backend is built on SQLAlchemy + Alembic +
> Arq/Redis pub-sub + local Chroma vectors. Rewriting that onto Firestore +
> Cloud Functions is a 4–6 week replatform with no product benefit. The plan
> below keeps every line of backend logic and swaps only hosting + auth.

## Architecture

```
browser ──https──► Vercel (Next.js, root: onboarding/frontend)
                       │  same-origin /api/* ──https──► Cloud Run: api
                       │                                    ├── Cloud SQL (Postgres 16)
                       │                                    ├── Upstash Redis (Arq + SSE)
                       │                                    ├── Cloud Run: rag (stateless, self-seeding)
                       │                                    └── Cloud Run Job: worker (arq plan/execute)
Firebase Auth ──ID tokens──► browser ──Bearer──► api (firebase-admin verify)
n8n (stays on current box until pilot) ──webhook──► api
```

## What you do vs what Claude Code does

| You (accounts, ~30 min) | Claude Code (code + deploy, ~2–3 h) |
|---|---|
| Google account → Firebase project + billing-free Spark/Blaze choice | All phases below, verified per gate |
| Vercel account (GitHub login) | Writes every file change, runs every command |
| Upstash account (free Redis) | Proves each service healthy before moving on |
| `gcloud`, `firebase-tools` login on the deploy machine | Never invents credentials; reads them from you |

## Prerequisites (Claude Code: verify first, stop if missing)

```bash
gcloud --version && firebase --version && docker --version
gcloud auth list                       # must show YOUR google account
gcloud config get-value project        # must be the Firebase project id
```

Copy-paste prompt:

> **P0 — preflight.** In `onboarding/`, verify deploy prerequisites and stop
> with a precise missing-item list if anything is absent: `gcloud`,
> `firebase-tools`, `docker`, an authenticated Google account, a Firebase
> project id, `FIREBASE_WEB_API_KEY`, `FIREBASE_AUTH_DOMAIN`,
> `FIREBASE_PROJECT_ID` (web app config), a Firebase **service account JSON**
> (Admin SDK, kept out of git), `UPSTASH_REDIS_URL`, and a Vercel project
> linked to `onboarding/frontend`. Do not create accounts. Do not proceed
> past preflight until I confirm the values.

## Phase 1 — Cloud SQL + Redis (no code changes)

Prompt:

> **P1 — data plane.** Provision (or verify existing): Cloud SQL Postgres 16
> database `onboarding` reachable from Cloud Run via private IP/connector,
> and an Upstash Redis URL. Then from `onboarding/`: run
> `DATABASE_URL=<cloud-sql-psycopg2-url> alembic -c db/alembic.ini upgrade head`,
> then `alembic check`, then `SEED_DEMO=1` seed **only if this is a demo
> project** (never for pilot). Gate: `test_schema_has_8_tables`,
> `test_idempotency_key_unique`, `test_seed_idempotent` green against the
> cloud DB. Record both DSNs in `.env.deploy` (gitignored, never committed).

Why Cloud SQL, not Firestore: `db/models.py` (8 tables, UNIQUEs, JSONB,
CHECK constraints) and `db/migrations/` (0001→0004) keep working untouched;
Alembic remains the migration story.

## Phase 2 — backend API to Cloud Run (config-only change)

Prompt:

> **P2 — api container.** Using `onboarding/Dockerfile.backend`, build and
> push the image to Artifact Registry, then deploy service `api` to Cloud Run
> (min-instances 0, max 2, `--port 8000`, concurrency 20). Env:
> `DATABASE_URL` (Cloud SQL), `REDIS_URL` (Upstash, `rediss://` tolerated),
> `RAG_BASE_URL` (Phase 4 URL, temporary `http://127.0.0.1:9` until then),
> `JWT_DEV_STUB=true` (demo) with `SERVICE_API_KEY` + `JWT_SECRET_GENERATED`
> from local `openssl rand -hex 32`, `MCP_MODE=sandbox`. Gate: public
> `GET /health` → `{"status":"ok"}` and `GET /openapi.json` contains
> `/api/v1/auth/dev-login`. Do not enable public unauthenticated writes
> beyond what the app already exposes; note the Cloud Run URL as
> `API_URL` for Phase 5.

## Phase 3 — Firebase Auth swap (the one real code change)

Current state: `backend/app/auth.py` accepts `dev:<role>:<sub>` bearers when
`JWT_DEV_STUB=true`; `frontend/app/login/page.tsx` mints them via
`POST /api/v1/auth/dev-login`; `frontend/lib/api.ts` already attaches
`Authorization: Bearer <token>` from its token holder. Only the mint/verify
ends change — no route logic changes (RBAC decorators untouched).

Prompt:

> **P3 — Firebase Auth.** 1) Add `firebase-admin` to
> `backend/requirements.txt`; in `backend/app/auth.py` add a
> `verify_firebase_id_token()` used by `get_current_user()` when
> `FIREBASE_PROJECT_ID` is set (before the dev-stub branch; dev stub stays
> for local tests). Map Firebase `uid` → `TokenData.sub` and a custom claim
> `role` (`employee|hr_admin|service`) → `TokenData.role`; reject missing
> role with 403. Keep `JWT_DEV_STUB=false` disabling `/auth/dev-login`
> (already implemented — add a test asserting 404 when stub is off).
> 2) Frontend: add `firebase` (client SDK) dependency; rewrite
> `app/login/page.tsx` sign-in to Firebase email-link/Google-provider
> sign-in (your choice, default: Google provider, allowlist by email domain
> if HR provides one), then `getIdToken()` → existing `setApiToken()`.
> Delete the `api.devLogin` call but keep the MSW `dev-login` handler for
> offline UI work. 3) Regenerate contract
> (`export_openapi.py` + `gen_types.py`) and run: backend gateway suite,
> `tsc --noEmit`, vitest, Playwright (MSW), ruff-F, mypy backend. Gate: all
> green + live `POST /api/v1/chat` with a Firebase ID token returns cited
> answers and `dev-login` 404s with the stub off.

## Phase 4 — RAG + worker to Cloud Run

Prompt:

> **P4 — rag + worker.** Build/push `Dockerfile.rag` → Cloud Run service
> `rag` (needs no disk: entrypoint self-seeds 30 points into ephemeral
> Chroma on cold start; `EMBEDDING_BACKEND=hash`, `WORKER_FIXTURE_MODE`
> irrelevant here). Point the `api` service `RAG_BASE_URL` at it and
> re-run the RAG eval gate against the public URL
> (`evaluate.py --llm extractive`, expect PASS 1.0/1.0/1.0). Then build/push
> `Dockerfile.worker` → Cloud Run **Job** (or min-instances-1 service)
> running `arq worker.jobs.WorkerSettings` with the same Postgres/Redis env
> plus `RAG_BASE_URL`; trigger one hire end to end (trigger → plan →
> approve → execute → `active`) and attach the trace. Keep
> `WORKER_FIXTURE_MODE=1` (no GPU on Cloud Run CPU); document the Ollama
> flip (Option B in DEPLOY.md) without implementing it.

## Phase 5 — frontend to Vercel

Prompt:

> **P5 — Vercel.** Push the repo, import in Vercel with Root Directory
> `onboarding/frontend` (framework auto-detected). Set env (Production +
> Preview): `INTERNAL_API_URL=<Phase-2 API_URL>`,
> `NEXT_PUBLIC_API_URL=` (empty = same-origin rewrites),
> `NEXT_PUBLIC_FIREBASE_API_KEY/AUTH_DOMAIN/PROJECT_ID` (Phase 0 values),
> `NEXT_PUBLIC_USE_MSW` unset. Deploy, then verify from a fresh browser:
> Firebase sign-in → HR pipeline lists cases → plan approve → execution
> succeeds → employee chat cited. Also confirm the version-drift banner is
> absent (codegen hash matches the deployed API).

## Phase 6 — cutover checklist (Claude Code: execute, report each line)

- [ ] n8n `intake.json` trigger URL → public api URL; re-import; send one
      test HRIS webhook (HMAC) → exactly one case (DLQ empty).
- [ ] `JWT_DEV_STUB=false` on Cloud Run api; `dev-login` 404s; Firebase
      login still works.
- [ ] Secrets live only in Cloud Run/Vercel env (never in git;
      `scripts/check_secrets.py` green).
- [ ] `MCP_MODE` stays `sandbox` (fake tools) until mapping sign-off.
- [ ] Old tunnel/demo containers stopped to avoid double-processing Arq jobs.
- [ ] `DEPLOY.md` proof-log section appended with image digests + URLs.

## Cost (honest, free-tier-first)

| Piece | Free option | When it stops being free |
|---|---|---|
| Vercel frontend | Hobby (100 GB bandwidth) | High demo traffic |
| Cloud Run api/rag | 2M reqs + 360k GB-s /mo | Sustained pilot load |
| Cloud SQL | **No free tier** — smallest ~$10–15/mo | Day one (use $300 new-account trial) |
| Upstash Redis | 10k cmds/day free | Busy pilot |
| Firebase Auth | 50k MAU free | Never at this scale |
| GPU/Ollama | None — fixture mode | Live crew needs a GPU box (~$1–2/hr spot) |

Cheapest honest demo: Vercel + Cloud Run + **Neon/Supabase free Postgres**
instead of Cloud SQL (same SQLAlchemy/Alembic path, Phase 1 unchanged apart
from the DSN). Claude Code: prefer Neon if the user confirms; Cloud SQL if
they insist on all-Google.

## Rollback

Every phase is additive: local compose stack + tunnel link keep running
throughout. If any gate fails, stop, keep serving locally, and report the
failing gate output — do not roll forward. Vercel keeps instant rollback to
the previous deployment; Cloud Run keeps prior revisions one click away.
