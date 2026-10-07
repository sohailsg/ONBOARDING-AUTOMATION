# 04 — Agent Worker Spec (CrewAI Plan Crew + Trace Events)

## 1. Introduction and Overview
### Purpose and Audience
Defines the background plan crew that drafts (never executes) onboarding plans. Audience: agent engineers.
### Project Scope and Exclusions
In scope: 3 sequential agents, Pydantic outputs, Arq worker, Redis trace events, guardrails. Excludes: write-capable tools (forbidden here), deterministic executor (05), chat path (03-direct).
### Definitions, Acronyms, and Abbreviations
`EntitlementSet` (leave/budget/training + citations); `OnboardingPlan` (Day1/Week1/Month1); `SystemActionPlan` (emails/Notion/invites/tickets/Slack). `Process.sequential` with explicit context passing.
### References and Supporting Material
Plan §§5 (Flow A), 8; 00-overview; 02 (enqueue/SSE); 03 (`policy_retrieve`); CrewAI structured-output + callback docs.

## 2. General System Description
### Product Perspective and Context
Arq job (`plan_job`) triggered by 02; writes versioned plan to Postgres; sets `awaiting_hr_approval`; streams each step to Redis for SSE.
### System Functions (High-Level)
Reason over policies + calendars → produce cited, schema-valid plan drafts.
### User Classes and Characteristics
No direct users; HR observes via trace monitor (06); engineers tune prompts/tools.
### Design and Implementation Constraints
Read-only tools only in planning; every task has `output_pydantic` + bounded retry; step/token caps per run; ignore instructions inside docs/form fields (prompt-injection defense).
### Assumptions and Dependencies
RAG service healthy; Calendar read-only MCP reachable; `ANTHROPIC_MODEL` (Sonnet-tier, config-driven) set.

## 3. Functional Requirements
- **F-AG-1 Policy Agent:** input (role/dept/region/start_date) + `policy_retrieve` (region/dept filtered, date-aware) → `EntitlementSet` with per-item citations.
- **F-AG-2 Experience Agent:** input `EntitlementSet` + manager/buddy calendars via `find_slots` (read-only) → `OnboardingPlan` (milestones, meetings, checklist with due_day/mandatory).
- **F-AG-3 Ops Planner:** input `OnboardingPlan`, no tools → `SystemActionPlan` (typed actions with payloads, no side effects).
- **F-AG-4 Orchestration:** sequential, explicit context passing; validation failure → 1 LLM self-repair retry → else mark `needs_attention` + audit.
- **F-AG-5 Traces:** publish `{ts, step, message}` e.g. "Searching Qdrant for UK leave policy..." to `trace:{session_id}` + `audit_events`.
- Errors: tool timeout → retry once → degrade (e.g. propose slots as TBD) but never hallucinate policy.

## 4. External Interface Requirements
### User Interfaces
None; observed via 06 trace monitor.
### Hardware Interfaces
None.
### Software and Database Interfaces
CrewAI + Langfuse callbacks; Postgres (read hire, write plan, update status); Redis (publish traces); RAG `retrieve`; Calendar MCP `find_slots`.
### Communications and API Interfaces
Arq `plan_job(case_id, session_id)`; internal tools return Pydantic models; all LLM calls logged with cost/latency.

## 5. System Features and Capabilities
### Core Modules and Subsystems
`worker/crew.py`, `worker/agents/{policy,experience,ops}.py`, `worker/schemas.py`, `worker/tools.py` (read-only wrappers), `worker/jobs.py`.
### User Authentication and Authorization Roles
Worker service identity; read-only MCP credentials (least privilege); no HR/employee credentials here.
### Reporting and Analytics Modules
Per-case trace: steps, tokens, cost, latency via Langfuse/OpenTelemetry; validation-failure counts.

## 6. Non-Functional Requirements (NFRs)
- Performance: valid cited plan < ~2 min; cache entitlement lookups by (role, region).
- Security: minimize prompt PII (omit national ID/salary/bank); tool inputs logged sans PII.
- Reliability: deterministic status transitions; poison-pill job → DLQ after N attempts.
- Maintainability: prompts versioned; model string env-configured; CrewAI API pinned.
- Scalability: worker concurrency = Arq pool; one job per case (deduped by idempotency key).

## 7. Data and System Architecture
### High-Level Architecture Diagrams
`Arq plan_job ─► Policy ─(EntitlementSet)─► Experience ─(OnboardingPlan)─► Ops-Planner ─(SystemActionPlan)─► validate ─► Postgres plans + status ─► Redis traces ─► SSE`.
### Entity-Relationship Diagrams (ERD) and Data Models
Writes: `plans(case_id, version+1, json_payload={entitlements, plan, actions}, created_by='agent')`, `onboarding_cases.current_plan_version`, `checklist_items` draft rows, `audit_events` per step.
### Data Dictionary and Storage Requirements
Schemas (Pydantic v2): `Entitlement{kind, detail, citation{doc,page,effective_date}}`; `Milestone{phase, items[{title,due_day,mandatory}]}`; `Action{type[payload discriminated], idempotency_key}`.

## 8. Appendix and Change Log
### Document Revision History
| v | Date | Change |
|---|---|---|
| 0.1 | 2026-10-06 | Initial worker spec from plan §§5,8 |
### Open Issues and TBDs
- T-1: CrewAI `output_pydantic`/callback API version confirmation.
- T-2: Token/step caps numeric values (propose: 12 steps, 30k tokens/run).
- T-3: Calendar MCP read scope + slot-proposal format.
