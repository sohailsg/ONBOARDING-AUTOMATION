# 07 — Hardening & Rollout Spec (Security, Observability, Pilot)

## 1. Introduction and Overview
### Purpose and Audience
Defines Phase 5 exit: secure, observable, piloted system. Audience: security, SRE, HR pilot owners.
### Project Scope and Exclusions
In scope: security review, PII/retention, secrets, audit completeness, OTel/Sentry/Langfuse, load/failure tests, runbooks, single-region 10-hire pilot. Excludes: multi-region rollout, payroll integrations.
### Definitions, Acronyms, and Abbreviations
DPDP (India Digital Personal Data Protection); OTel (OpenTelemetry); DLQ (dead-letter queue); RTO/RPO for Postgres.
### References and Supporting Material
Plan §§10–11; 00-overview; 01–06 NFRs; legal guidance on GDPR (UK) + DPDP.

## 2. General System Description
### Product Perspective and Context
Final gate before production: proves zero unapproved side effects, cited answers, recoverable failures.
### System Functions (High-Level)
Enforce least-privilege + audit; trace cost/latency per case; survive dependency failures; operate via runbooks.
### User Classes and Characteristics
SRE on-call; security auditor; HR pilot cohort (1 region/dept, ~10 hires).
### Design and Implementation Constraints
Append-only audit (no updates/deletes); PII minimization in prompts/logs/vectors; kill switch always available to HR.
### Assumptions and Dependencies
Vault (or cloud secrets manager) provisioned; Sentry/OTel collector/Langfuse tenants ready; sandbox→pilot promotion checklist signed.

## 3. Functional Requirements
- **F-HD-1 Access:** SSO enforced, RBAC tests (employee cannot read others' cases; service cannot approve), secrets rotation runbook.
- **F-HD-2 PII:** field allowlist for prompts (exclude national ID/salary/bank); retention + deletion job (e.g. chat logs 12 mo, traces 6 mo — confirm with legal).
- **F-HD-3 Audit:** every agent step/edit/approval/external action in `audit_events`; immutability test (UPDATE/DELETE rejected).
- **F-HD-4 Observability:** OTel traces API→queue→worker→MCP; Sentry errors; Langfuse LLM cost/latency per case dashboard.
- **F-HD-5 Resilience:** idempotency chaos test (duplicate trigger + duplicate tool calls → single effect); retry/DLQ test; kill-switch drill; Qdrant/Rerank outage → graceful abstain/degrade.
- **F-HD-6 Pilot:** 10 hires, one region/dept; success = cited plans, all sends approved, Faithfulness ≥ 0.9, no `needs_attention` left unresolved > 24 h.

## 4. External Interface Requirements
### User Interfaces
Runbook docs + Grafana/Langfuse dashboards + HR execution view (06) showing audit trail.
### Hardware Interfaces
Pilot infra: single Postgres primary + Redis + Qdrant (backups enabled).
### Software and Database Interfaces
Vault agent injection; OTel exporter; Sentry SDK (backend/worker/frontend); PG `pg_cron` or equivalent for retention deletes.
### Communications and API Interfaces
No new public APIs; alert webhooks (PagerDuty/Slack) for DLQ depth, Faithfulness drop, 5xx spike.

## 5. System Features and Capabilities
### Core Modules and Subsystems
`onboarding/runbooks/{oncall, reindex, kill-switch, secrets-rotation}.md`, `observability/` dashboards, `tests/{load,chaos,security}.py`, retention jobs.
### User Authentication and Authorization Roles
On-call SRE (read traces/logs, halt executions); auditor (read-only audit export); HR pilot lead (halt + escalate).
### Reporting and Analytics Modules
Weekly pilot report: hires onboarded, plan latency, chat Faithfulness/answer rate, action success/retry, cost per hire.

## 6. Non-Functional Requirements (NFRs)
- Performance: load test 2x pilot (20 concurrent cases) without SLO breach (API p95 < 300 ms, plan < 2 min).
- Security: pen-test-lite (OWASP ZAP), dependency scan, secret scan in CI; encryption at rest + TLS everywhere.
- Reliability: RTO < 1 h / RPO < 15 min for Postgres (PITR); DLQ drained < 4 h.
- Maintainability: runbooks tested via game day before pilot.
- Scalability: scale signals documented (queue depth, Qdrant latency) with runbook thresholds.

## 7. Data and System Architecture
### High-Level Architecture Diagrams
Same as 00 + observability sidecar: `API/Worker/RAG/MCP ──OTel──► collector ─► traces/metrics; ──Sentry──► errors; LLM calls ─► Langfuse`.
### Entity-Relationship Diagrams (ERD) and Data Models
No new tables; retention policies annotate 01 tables (`audit_events` immutable/retained longest; `chat_logs` PII-redacted after N months).
### Data Dictionary and Storage Requirements
Backup: daily Postgres base + WAL; Qdrant snapshot pre-reindex; Redis RDB best-effort (rebuildable from DB).

## 8. Appendix and Change Log
### Document Revision History
| v | Date | Change |
|---|---|---|
| 0.1 | 2026-10-06 | Initial hardening spec from plan §§10–11 |
### Open Issues and TBDs
- T-1: Legal sign-off on GDPR/DPDP retention periods.
- T-2: Pilot region/dept selection + HR approver roster.
- T-3: Cost-per-hire budget threshold for Langfuse alerts.
