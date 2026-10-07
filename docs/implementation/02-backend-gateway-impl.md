# 02 — Backend Gateway Implementation Plan

## 1. Document Overview and Scope
### Purpose and Objectives
Build the stateless FastAPI gateway: auth/RBAC, §7 REST + SSE, Arq enqueue, audit. Explicitly no LLM/agent logic. Done when frontend can intake→list→stream→edit→approve against real API with mocked worker payloads.
### Project Reference Documents (SRS/Spec Links)
Spec: `02-backend-gateway-spec.md`; Master: `00-overview-impl.md`; consumes 01 DSNs; serves 06; enqueues 04/05 jobs.
### Key Stakeholders and Project Roles
E1 backend (owner); E3 frontend (API consumer, mock-shape reviewer); security reviewer (RBAC sign-off).

## 2. Technical Architecture and Design Strategy
### Technology Stack Selection
FastAPI + Pydantic v2 + SQLAlchemy async + Arq + `redis.asyncio` + `httpx` (RAG) + `python-jose` (JWT) + slowapi (rate limits) + OTel + Sentry SDKs.
### System High-Level Architecture
Thin routers → service layer (state transitions) → Postgres; `jobs.py` enqueues `plan_job/execute_job`; `sse.py` subscribes `trace:{session_id}` and fans out `text/event-stream` with 15 s heartbeats + last-N replay from `audit_events` on reconnect.
### Database Schema and Data Models
Owns status machine: `pending_ingestion→agent_processing→awaiting_hr_approval→executing→active|needs_attention`; PUT plan bumps `current_plan_version` + stores diff in `approvals.comment`/audit metadata; Pydantic request/response models mirror 01 tables + `Action` discriminated payloads.
### API Contracts and Integration Specifications
Implement exactly (OpenAPI-generated): trigger (service, Idempotency-Key 128ch), `GET /cases?status=&page=`, SSE stream, plan GET/PUT, approvals POST, me/roadmap + checklist PATCH (force `employee_id=token.sub`), chat POST (server-side profile → RAG), admin reindex (2/hr). Error map: 400/401/403/404/409→existing/429/5xx+Sentry. Rate limits: chat 30/min/user, trigger 60/min/key.

## 3. Work Breakdown Structure (WBS) and Backlog
### Feature-to-Task Decomposition
| ID | Task | Done when |
|---|---|---|
| 2.1 | Scaffold (`main.py`, config, logging, OTel/Sentry, OpenAPI) + JWT/RBAC deps (+ stub behind interface) | `/health` + 403 matrix test green |
| 2.2 | Onboarding + cases routers (trigger idempotent, list, SSE stream + replay) | Duplicate-key returns existing; SSE reconnect test passes |
| 2.3 | Plan + approvals routers (version bump, diff, approve→enqueue execute) | Version/diff persisted; approve enqueues job |
| 2.4 | Me + checklist + chat + admin routers (row scoping, RAG call, reindex limit) | Employee cannot touch others' cases; chat logs row written |
| 2.5 | `jobs.py` + `audit.py` + rate limits + OpenAPI client codegen for frontend | `npm run gen:api` types consumed by 06 |

### Task Dependencies and Critical Path
2.1 → 2.2 → 2.3 → 2.4 → 2.5. Needs W1 DSNs. Unblocks 06 (mocks→real) and 04/05 enqueue integration.
### Definition of Done (DoD)
All routers tested (unit+integration), SSE reconnect covered, OpenAPI diff reviewed by E3, API p95 <300 ms on seed data, audit rows verified per mutation.

## 4. Resource Allocation and Scheduling
### Team Structure and Core Responsibilities
E1 full-time weeks 2–4; E3 reviews API shapes mid-week-2; security review end of week 4.
### Milestones and Key Delivery Dates
W2: 2.1+2.2 + mock payloads for frontend; W3: 2.3+2.4; W4: 2.5 + RBAC pen-test-lite + perf check.
### Sprint Schedule / Gantt Chart Phase Planning
S2: skeleton + trigger/stream; S3: plan/approvals/chat; overlap with W3 RAG (chat needs RAG stub → real).

## 5. Testing and Quality Assurance Strategy
### Test Environment Setup
`pytest` with asyncpg test DB (migrated), fakeredis, RAG stub server, Arq test queue; SSE tests via streaming client.
### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Unit: RBAC matrix (3 roles × endpoints), idempotency-key validation, status-transition guards.
- Integration: trigger→enqueue→SSE replay; PUT→version bump; approve→execute enqueue; checklist optimistic-conflict path; chat abstain logging.
- UAT: HR clicks pipeline→plan→approve in staging; employee checklist tick.
### Requirements Traceability Matrix (RTM)
| Spec req | Task | Test |
|---|---|---|
| F-API-1 trigger idempotent | 2.2 | Duplicate-key integration |
| F-API-3 SSE + replay | 2.2 | Disconnect/reconnect test |
| F-API-4 version + diff | 2.3 | Version-bump test |
| F-API-5 approve→enqueue | 2.3 | Job-enqueued assertion |
| F-API-6 row scoping | 2.4 | Cross-employee 403 test |
| F-API-7 chat + logs | 2.4 | RAG-stub + abstain test |

## 6. Deployment and DevOps Pipeline
### CI/CD Configuration and Environments (Dev, Staging, Prod)
Actions: ruff+mypy+pytest → Docker build → push → deploy dev (auto) → staging (manual) → pilot (gated). Env vars per env (issuer, JWKS, rate limits, RAG URL).
### Data Migration and Seeding Strategies
No DDL here (01 owns); seed hires used for API perf tests; no production seeding.
### Rollback and Disaster Recovery Procedures
Stateless → previous image rollback instant; in-flight SSE reconnects; queued Arq jobs survive (Redis) and dedupe via idempotency keys on new version.
### Post-Launch Monitoring and Alerting
OTel RED metrics per route; Sentry 5xx; alerts on 5xx spike, SSE error rate, queue-lag growth; dashboard: request p95, enqueue latency, approval throughput.

## 7. Risk Management and Contingencies
### Technical Risks and Mitigation Actions
| Risk | Mitigation |
|---|---|
| SSO delay | JWT stub behind `AuthProvider` interface; swap without route changes |
| EventSource auth limits | Fallback: short-lived signed stream URL (T-3 decision in S2) |
| Arq vs Celery regret | Queue abstraction (`enqueue(plan_job…)`) so backend swap is contained |
| Chat PII leak in logs | Allowlist serializer; log-review checklist in PR template |
### Resource and Timeline Constraints
E1 split with W5-executor in weeks 5–7; protect 2.1–2.4 dates by deferring 2.5 codegen polish (hand-written types interim).
### Change Management Process
Route/spec change → OpenAPI regen + frontend type bump + RTM update in same PR; breaking changes need tech-lead + E3 sign-off.
