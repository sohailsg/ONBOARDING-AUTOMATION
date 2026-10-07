# 01 — Infra + Data Implementation Plan

## 1. Document Overview and Scope
### Purpose and Objectives
Build the runnable foundation: one-command local stack + versioned Postgres schema + seeds. Done when `docker compose up && alembic upgrade head` yields a healthy dev backend dependency set.
### Project Reference Documents (SRS/Spec Links)
Spec: `onboarding/docs/specs/01-infra-data-spec.md`; Master: `00-overview-impl.md`; Plan §§2,6,11 (Phase 0).
### Key Stakeholders and Project Roles
E1 backend/infra (owner); tech lead (schema review); HR (seed-data sanity on sample hire fields).

## 2. Technical Architecture and Design Strategy
### Technology Stack Selection
Postgres 16 (`pgvector` not needed — Qdrant holds vectors), Redis 7 (AOF on), Qdrant latest, n8n self-hosted image pinned, SQLAlchemy 2 async + `asyncpg`, Alembic, Arq.
### System High-Level Architecture
`docker-compose.yml` services: `db (5432), redis (6379), qdrant (6333+6334), n8n (5678)` on one network with named volumes `pgdata, redisdata, qdrantdata, n8ndata`; healthchecks gate API/worker startup.
### Database Schema and Data Models
8 tables per spec: `employees; onboarding_cases(idempotency_key UNIQUE, status enum, current_plan_version); plans(case_id, version, UNIQUE(case_id,version), json_payload JSONB, created_by); approvals(plan_id, approver_id, decision, comment, decided_at); actions(plan_id, type, payload JSONB, status, attempts DEFAULT 0, external_ref, last_error); checklist_items(case_id, title, due_day, mandatory, completed_at); audit_events(actor, event, entity, metadata JSONB, ts DEFAULT now(), immutable via REVOKE UPDATE/DELETE); chat_logs(...)`. Indexes on `cases(status), plans(case_id,version), actions(plan_id,status), audit(ts)`.
### API Contracts and Integration Specifications
No public API. Internal DSNs: `DATABASE_URL=postgresql+asyncpg://app:…@db:5432/onboarding`, `REDIS_URL=redis://redis:6379/0`, `QDRANT_URL=http://qdrant:6333`. `.env.example` documents all; fail-fast if unset.

## 3. Work Breakdown Structure (WBS) and Backlog
### Feature-to-Task Decomposition
| ID | Task | Done when |
|---|---|---|
| 1.1 | `docker-compose.yml` + volumes + healthchecks | `compose up` all healthy <3 min |
| 1.2 | Alembic scaffolding + initial migration (8 tables + enums + indexes) | `upgrade/downgrade` clean, `alembic check` green |
| 1.3 | DB roles (`app_rw`, `migrate`) + least-privilege grants | App cannot DDL; migrate-only image documented |
| 1.4 | `audit_events` immutability (REVOKE + test) | UPDATE/DELETE raises |
| 1.5 | Seed script (`seed_demo.py`, idempotent: 1 region, 2 hires, sample checklist) | Re-runnable, no dupes |
| 1.6 | `make up/down/logs/migrate/seed` targets + README | New engineer onboard <30 min |

### Task Dependencies and Critical Path
1.1 → 1.2 → 1.3/1.4 → 1.5 → 1.6. Critical: 1.1+1.2 unblock all downstream (W2–W4).
### Definition of Done (DoD)
Compose healthy; migrations reversible; seed idempotent; CI runs `alembic check`; README verified by second engineer.

## 4. Resource Allocation and Scheduling
### Team Structure and Core Responsibilities
E1 owns all; tech lead reviews migration SQL; 0.5 week.
### Milestones and Key Delivery Dates
Week 1 day 3: compose up; day 5: migrations + seeds merged, HR confirms sample-hire fields.
### Sprint Schedule / Gantt Chart Phase Planning
S1a (days 1–2): 1.1; S1b (days 3–4): 1.2–1.4; S1c (day 5): 1.5–1.6. Float: none (critical path head).

## 5. Testing and Quality Assurance Strategy
### Test Environment Setup
CI service containers (postgres/redis/qdrant) mirror compose pins; `pytest -m infra` exercises migrations + seed idempotency.
### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Unit: enum defaults, unique constraints (duplicate idempotency key → IntegrityError).
- Integration: full `up → migrate → seed → API health` smoke; downgrade→upgrade cycle.
- UAT: HR confirms seed hire fields render in pipeline mock.
### Requirements Traceability Matrix (RTM)
| Spec req | Task | Test |
|---|---|---|
| F-IN-1 compose | 1.1 | Healthcheck CI |
| F-IN-2 migrations | 1.2 | `alembic check` + downgrade test |
| F-IN-3 idempotency UNIQUE | 1.2 | Duplicate-key test |
| F-IN-4 seed | 1.5 | Re-run seed, row counts stable |
| audit append-only | 1.4 | UPDATE/DELETE must fail |

## 6. Deployment and DevOps Pipeline
### CI/CD Configuration and Environments (Dev, Staging, Prod)
CI: `alembic check` + migration-up-on-ephemeral-DB + seed test. Staging: managed Postgres + `migrate` job before deploy. Prod/pilot: PITR-enabled instance; migrations run as gated job with backup snapshot first.
### Data Migration and Seeding Strategies
Forward-only in pilot; expand→backfill→contract for column changes. Seeds only in dev/staging; pilot data enters via Workflow A (never seed scripts).
### Rollback and Disaster Recovery Procedures
Additive migrations roll forward; destructive changes require tested `downgrade` + snapshot restore drill. Nightly `pg_dump` + WAL (pilot); Qdrant snapshot pre-reindex; Redis RDB best-effort.
### Post-Launch Monitoring and Alerting
Compose healthchecks → container restart; staging/pilot: DB connections, disk, replication lag alerts; migration failure pages E1.

## 7. Risk Management and Contingencies
### Technical Risks and Mitigation Actions
| Risk | Mitigation |
|---|---|
| Port conflicts / Docker Desktop limits | Documented port overrides; min-spec 4CPU/8GB note |
| Enum migration pain later | Use check-constraint-friendly enums; new statuses additive |
| Qdrant version drift | Pin image digest; collection `policies_v1` versioned |
### Resource and Timeline Constraints
Single owner + 1-week window; if blocked, defer n8n service (stub) — never defer Postgres/Redis.
### Change Management Process
Schema change = new migration + spec §7 update + RTM row; tech-lead approval; no direct DDL on shared envs.
