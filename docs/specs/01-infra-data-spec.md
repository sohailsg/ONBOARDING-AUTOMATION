# 01 — Infra + Data Spec (Postgres / Redis / Qdrant / Compose)

## 1. Introduction and Overview
### Purpose and Audience
Defines local + pilot infrastructure and the system of record. Audience: platform/backend engineers.
### Project Scope and Exclusions
In scope: `docker-compose.yml`, Alembic migrations for 8 tables, seed data, backup basics. Excludes app logic (02–06) and prod hardening (07).
### Definitions, Acronyms, and Abbreviations
Compose services: `db` (Postgres 16), `redis` (Redis 7), `qdrant`, `n8n`. Arq queue + `trace:{session_id}` pub/sub live in Redis.
### References and Supporting Material
Plan §§2,6,11 (Phase 0); 00-overview-spec; Alembic + SQLAlchemy 2.0 docs.

## 2. General System Description
### Product Perspective and Context
Foundation layer; all parts depend on it. Runs via `docker compose up` for dev; pilot reuses same services (managed variants allowed).
### System Functions (High-Level)
Provide persistent state (Postgres), ephemeral queue/streams (Redis), vector index (Qdrant), versioned schema migrations.
### User Classes and Characteristics
Operator (engineer/HR-ops running compose); Service accounts (API, worker with least-privilege DB roles).
### Design and Implementation Constraints
Postgres is source of truth; Redis data is disposable; Qdrant metadata must include policy-lifecycle fields. `onboarding_cases.idempotency_key UNIQUE`.
### Assumptions and Dependencies
Docker available; ports 5432/6379/6333 free; n8n image pinned.

## 3. Functional Requirements
- **F-IN-1 Compose:** one command brings up db/redis/qdrant/n8n with healthchecks and named volumes.
- **F-IN-2 Migrations:** `alembic upgrade head` creates all tables + indexes; downgrade clean.
- **F-IN-3 Idempotency:** unique constraint on `onboarding_cases.idempotency_key` (`{hire_id}:{start_date}`); duplicate insert → 409 mapped to existing case by API.
- **F-IN-4 Seed:** idempotent seed script (1 region, 2 sample hires) for Phases 1–2 testing.
- Inputs: env (`DATABASE_URL, REDIS_URL, QDRANT_URL`); Processing: migrate → seed; Outputs: ready DSNs.
- Validation: migration CI check (`alembic check`); error: failed healthcheck blocks API/worker start (fail-fast with message).

## 4. External Interface Requirements
### User Interfaces
CLI only (`compose up/logs/down`, `alembic`).
### Hardware Interfaces
Dev: 4 CPU / 8 GB min. Qdrant memory sized for ~100k chunks pilot.
### Software and Database Interfaces
SQLAlchemy async (`asyncpg`), Arq (Redis), `qdrant-client`. Connection pooling (API pool 20, worker 10).
### Communications and API Interfaces
No public API. Internal: `postgres:5432`, `redis:6379`, `qdrant:6333`, `n8n:5678`.

## 5. System Features and Capabilities
### Core Modules and Subsystems
`db/migrations/`, `db/seeds/`, `docker-compose.yml`, `.env.example`.
### User Authentication and Authorization Roles
DB roles: `app_rw` (API/worker), `migrate` (DDL); no direct HR access to DB.
### Reporting and Analytics Modules
Migration version table; `audit_events` table created here (written by 02/04/05).

## 6. Non-Functional Requirements (NFRs)
- Performance: cold `compose up` < 3 min; migrations < 30 s.
- Security: secrets via env/Vault, never committed; Postgres encrypted at rest (pilot: volume encryption).
- Reliability: named volumes; `restart: unless-stopped`; Redis AOF on (queue durability best-effort; DB is truth).
- Maintainability: one migration per change; backward-compatible (expand→migrate→contract).
- Scalability: stateless consumers scale horizontally; queue depth is scale signal.

## 7. Data and System Architecture
### High-Level Architecture Diagrams
`API ─► Postgres; API/Worker ─► Redis (queue+pubsub); RAG ─► Qdrant; n8n ─► API`.
### Entity-Relationship Diagrams (ERD) and Data Models
`employees(id PK)` → `onboarding_cases(employee_id FK, status, current_plan_version, idempotency_key UNIQUE)` → `plans(case_id FK, version UNIQUE(case_id,version), json_payload, created_by, created_at)` → `approvals(plan_id FK, approver_id, decision, comment, decided_at)` + `actions(plan_id FK, type, payload JSONB, status, attempts, external_ref, last_error)`; `checklist_items(case_id FK, title, due_day, mandatory, completed_at)`; `audit_events(actor, event, entity, metadata JSONB, ts)`; `chat_logs(employee_id, question, answer, citations JSONB, confidence, feedback)`.
Indexes: cases(status), plans(case_id,version), actions(plan_id,status), audit(ts), chat(employee_id).
### Data Dictionary and Storage Requirements
Types: UUIDs PKs; `status` enums (`pending_ingestion, agent_processing, awaiting_hr_approval, executing, needs_attention, active`); `json_payload/payload` JSONB; retention: PII per 07 policy; Qdrant vectors separate from Postgres truth.

## 8. Appendix and Change Log
### Document Revision History
| v | Date | Change |
|---|---|---|
| 0.1 | 2026-10-06 | Initial infra/data spec from plan §§2,6,11 |
### Open Issues and TBDs
- T-1: Managed vs self-hosted Qdrant for pilot (Qdrant Cloud per plan §12?).
- T-2: Backup schedule + PITR for pilot Postgres.
