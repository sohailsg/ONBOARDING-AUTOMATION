# 00 — Master Implementation Plan: AI-Assisted Employee Onboarding

## 1. Document Overview and Scope

### Purpose and Objectives
Master build plan that turns all specs (00–07) into an executable 10–12 week program. Objective: intake → cited AI plan → HR approval → deterministic execution → employee hub + chatbot, with zero unapproved side effects in pilot.

### Project Reference Documents (SRS/Spec Links)
| Doc | Path |
|---|---|
| Architecture + plan (normative) | `onboarding_architecture_and_plan.md` §§1–12 |
| Overview spec | `onboarding/docs/specs/00-overview-spec.md` |
| Part specs | `onboarding/docs/specs/01-infra-data-spec.md` … `07-hardening-spec.md` |
| Part implementation docs | `00-overview-impl.md` (this file) … `07-hardening-impl.md` |

### Key Stakeholders and Project Roles
| Role | Responsibility |
|---|---|
| Tech lead | WBS, critical path, spec↔impl traceability, go/no-go |
| Backend engineer | 01 + 02 + executor core (05) |
| RAG/Agent engineer | 03 + 04 |
| Frontend engineer | 06 (builds against mocks from week 5) |
| HR pilot owner | Golden Q&A, plan-schema sign-off, 10-hire pilot |
| Security/SRE | 07 review, secrets, runbooks, on-call |

## 2. Technical Architecture and Design Strategy

### Technology Stack Selection (FREE-ONLY — see `onboarding/docs/STACK_DECISION_FREE.md`; no paid keys)
| Layer | Choice (locked) | Why |
|---|---|---|
| Backend | FastAPI + Pydantic v2 + SQLAlchemy 2 async + Alembic + Arq | Async-native, typed, SSE-friendly; Arq lighter than Celery for asyncio jobs |
| Data | Postgres 16, Redis 7, **Chroma (persistent, local)** | Source of truth / queue+pubsub / free local vectors (no Qdrant) |
| Agents | CrewAI `Process.sequential`, **Ollama chat via `OLLAMA_CHAT_MODEL` (default `llama3.1:8b`)** | Local, $0; model swappable |
| RAG | LlamaIndex/Unstructured, **Ollama embeddings (`nomic-embed-text`)**, BM25 sparse + RRF in-app, **local cross-encoder rerank** | Free hybrid recipe (no OpenAI/Cohere) |
| Frontend | Next.js + Tailwind + shadcn/ui + TanStack Query + Zustand + EventSource | Plan §12; SSE only |
| Orchestration | n8n self-hosted (Workflow A + MCP Server Trigger) | Webhooks + tool hosting only, no brain |
| Ops | Docker Compose (dev), OTel + Sentry + Langfuse (empty until W7; free tiers) | Traces, errors, LLM cost per case |

### System High-Level Architecture
```
[Next.js Hub + HR Center] ──REST+SSE/JWT──► [FastAPI] ──┬── Postgres
                                                         ├── Redis (Arq queue + trace:{session_id} pubsub) ──► SSE
                                                         ├── RAG service ──► Chroma (local) + Ollama
                                                         ├── Arq plan_job ─► CrewAI worker (Ollama) ─► Postgres + traces
                                                         └── Arq execute_job ─► deterministic executor ──MCP──► n8n/Notion/Calendar
[HRIS/Typeform] ──webhook──► [n8n Workflow A] ─► POST /onboarding/trigger
```

### Database Schema and Data Models
Per 01: `employees → onboarding_cases(idempotency_key UNIQUE) → plans(versioned) → approvals + actions(status/attempts/external_ref)`; `checklist_items`; `audit_events` append-only; `chat_logs`. Status enum: `pending_ingestion, agent_processing, awaiting_hr_approval, executing, needs_attention, active`. Pydantic: `EntitlementSet / OnboardingPlan / SystemActionPlan`.

### API Contracts and Integration Specifications
§7 surface implemented in 02: trigger (Idempotency-Key, service role), cases list, SSE stream, plan GET/PUT (new version + diff), approvals POST (enqueue execute), me/roadmap, checklist PATCH, chat POST, admin reindex. Internal: Arq `plan_job(case_id, session_id)` / `execute_job(plan_id)`; RAG `retrieve() + answer()`; MCP `tools/call` with `{plan_id}:{action_index}` idempotency keys; Chroma metadata includes `region, department, page_number, effective_date, superseded_by, version`.

## 3. Work Breakdown Structure (WBS) and Backlog

### Feature-to-Task Decomposition
| ID | Work package (impl doc) | Key tasks |
|---|---|---|
| W0 | Program setup (this doc) | Repo scaffold, CI, env, OpenAPI codegen, mock fixtures |
| W1 | Infra+data (01-impl) | Compose, migrations ×8 tables, seeds, healthchecks |
| W2 | Backend gateway (02-impl) | Auth/RBAC, 8 routers, SSE fan-out, Arq enqueue, audit |
| W3 | RAG (03-impl) | Ingest, hybrid index, retrieve→rerank→answer, eval gate |
| W4 | Worker (04-impl) | Schemas, 3 agents, read-only tools, traces, caps |
| W5 | n8n/MCP/executor (05-impl) | Workflow A, tool wrappers, executor, kill switch, sandbox |
| W6 | Frontend (06-impl) | Hub + HR Center, HITL editor, trace/execution views, MSW mocks |
| W7 | Hardening (07-impl) | Security review, load/chaos, runbooks, 10-hire pilot |

### Task Dependencies and Critical Path
`W1 → W2 → W4 → W5 → W7` is critical. `W3` required by W4 (Policy Agent) and W2-chat — start W3 immediately after W1. `W6` runs parallel from week 5 against MSW mocks + 02 stubs. `W7` needs all prior exits.

### Definition of Done (DoD)
- Code merged with tests + OpenAPI/spec updated; `ruff + mypy + pytest` green.
- Each package exit met: W1 compose up <3 min; W2 API p95 <300 ms; W3 Faithfulness ≥0.9; W4 plan <2 min cited; W5 sandbox end-to-end; W6 HR intake→approve→track unaided; W7 pilot 10 hires, zero unapproved actions.

## 4. Resource Allocation and Scheduling

### Team Structure and Core Responsibilities
3–4 engineers: E1 backend/infra (W1+W2+W5-executor), E2 RAG/agents (W3+W4), E3 frontend (W6) + assists W2 mocks, E4 (or shared) n8n/integrations + hardening (W5-n8n, W7). Tech lead covers W0 + cross-cutting reviews.

### Milestones and Key Delivery Dates (12-week frame)
| Week | Milestone |
|---|---|
| 1 | W1 done; schemas signed with HR |
| 2–3 | W3 done (eval gate green); W2 skeleton + mocks for frontend |
| 4–5 | W4 done (valid cited plan <2 min); W6 MSW build started |
| 5–7 | W5 sandbox execute end-to-end |
| 6–9 | W6 HR usable without dev help |
| 10–12 | W7 pilot (1 region, ~10 hires) + sign-off |

### Sprint Schedule / Gantt Chart Phase Planning
2-week sprints: S1 foundations (W0+W1); S2 RAG+API skeleton (W3+W2); S3 worker (W4) + frontend mocks (W6); S4 integrations (W5) + HITL UI; S5 frontend completion; S6 hardening + pilot. Overlap W5/W6 deliberately (frontend on mocks).

## 5. Testing and Quality Assurance Strategy

### Test Environment Setup
`dev` (docker compose, sandbox MCP), `staging` (managed Postgres/Redis/Qdrant mirrors + sandbox tools), `pilot/prod` (backups, Vault, no sandbox). Seed fixtures shared across envs.

### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Unit: schemas, status transitions, idempotency guards, chunk/filter logic, executor skip-succeeded.
- Integration: trigger→plan→approve→execute happy path; duplicate-trigger dedupe; SSE reconnect; chat abstain path; kill-switch drill.
- UAT: HR runs intake→review→edit→approve→track on 3 sample hires; employees complete checklist + 10 chat questions; sign-off checklist in 07-impl.

### Requirements Traceability Matrix (RTM)
| Plan req | Spec | Impl | Test |
|---|---|---|---|
| Idempotent intake | 00 F-OV-1, 01 | 01-impl W1, 02-impl | Duplicate-trigger test |
| Cited plan <2 min | 04 F-AG-1–4 | 04-impl | Worker e2e timer |
| Approval gate, no LLM post-approval | 00 §2, 05 | 05-impl executor | Unapproved-send negative test |
| Cited chat + abstain | 03 F-RAG-4 | 03-impl | Golden-set + low-confidence test |
| SSE traces | 02 F-API-3 | 02-impl + 04-impl | Stream/reconnect test |
| Per-action retry/halt | 05 F-MCP-3/4 | 05-impl | Chaos + kill-switch test |
| Faithfulness ≥0.9 | 03 F-RAG-6 | 03-impl + CI gate | RAGAS eval |

## 6. Deployment and DevOps Pipeline

### CI/CD Configuration and Environments (Dev, Staging, Prod)
GitHub Actions: `lint (ruff) → typecheck (mypy) → pytest → alembic check → RAGAS eval gate → build images → deploy staging → promote pilot`. Qdrant reindex as separate workflow (`admin/reindex`).

### Data Migration and Seeding Strategies
Alembic expand→migrate→contract; backward-compatible only. Seeds: `seed_demo.py` (idempotent, 1 region + 2 hires + sample policies) for dev/staging; pilot uses real HRIS data via Workflow A, never seeds.

### Rollback and Disaster Recovery Procedures
API/worker: blue-green image rollback (previous tag); migrations: forward-fix preferred, tested `downgrade` for additive changes; Postgres PITR (RPO <15 min, RTO <1 h); Qdrant snapshot before reindex; Redis rebuildable from DB. Kill switch halts in-flight executions during rollback.

### Post-Launch Monitoring and Alerting
OTel dashboards (request/job latency, queue depth, Qdrant latency), Sentry (5xx, worker exceptions), Langfuse (cost/latency per case, Faithfulness trend). Alerts: DLQ depth, Faithfulness <0.9, 5xx spike, execute failure rate → PagerDuty/Slack.

## 7. Risk Management and Contingencies

### Technical Risks and Mitigation Actions
| Risk | Mitigation (owner) |
|---|---|
| Hallucinated policy | Answer-only-from-context + citations + abstain + RAGAS gate (E2) |
| Duplicate/wrong sends | Approval gate + idempotency + sandbox + per-action audit (E1) |
| Stale policies | `effective_date/superseded_by` filter + re-ingest webhook (E2) |
| MCP immaturity (wrong package names flagged) | Wrapper interfaces; verify names before W5; fallback direct APIs (E4) |
| Agent latency/cost | Background jobs, step/token caps, (role,region) entitlement cache (E2) |
| CrewAI API drift | Pin version; verify `output_pydantic`/callbacks in S1 spike (E2) |

### Resource and Timeline Constraints
3–4 engineers × 12 weeks. Buffer: S6 is 50% buffer; frontend decoupled via mocks so W5 slippage doesn't block W6. Pilot scope fixed (1 region) — no expansion under pressure.

### Change Management Process
Spec change → update spec + impl doc + RTM row + migration/test impact note; tech-lead approval; minor (prompt copy, UI text) via PR only. Model/rerank/MCP swaps go through wrapper-interface PR + eval re-run.
