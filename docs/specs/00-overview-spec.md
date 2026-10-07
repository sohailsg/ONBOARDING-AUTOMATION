# 00 — System Overview Spec: AI-Assisted Employee Onboarding

## 1. Introduction and Overview

### Purpose and Audience
Defines the end-to-end system so all part specs (01–07) share one baseline. Audience: tech lead, backend/frontend/RAG/agent engineers, HR stakeholders, security reviewer.

### Project Scope and Exclusions
**In scope:** New-hire intake → AI plan crew → HR approval → deterministic execution → employee hub + policy chatbot, per `onboarding_architecture_and_plan.md` §§2–12.
**Exclusions:** Payroll/HRIS as source of truth (HRIS is upstream webhook only); native mobile apps; full SSO provider implementation in MVP (stub acceptable, see 02); direct LLM side effects (forbidden by design).

### Definitions, Acronyms, and Abbreviations
| Term | Meaning |
|---|---|
| HITL | Human-in-the-loop (HR approval gate) |
| RAG | Retrieval-Augmented Generation (Qdrant hybrid + rerank) |
| SSE | Server-Sent Events (one-way server→client trace stream) |
| Plan crew | 3 sequential CrewAI agents: Policy, Experience, Ops-Planner |
| Execute step | Deterministic replay of approved `SystemActionPlan` |
| MCP | Model Context Protocol (tool hosting, incl. n8n MCP Server Trigger) |

### References and Supporting Material
- `onboarding_architecture_and_plan.md` §§1–12 (normative)
- Part specs 01–07 in this folder
- Verify-before-build list (§12 of plan): Notion/Calendar MCP package names, Cohere Rerank version, Claude Sonnet-tier model string, CrewAI structured-output API

## 2. General System Description

### Product Perspective and Context
Greenfield system inside `onboarding/` monorepo. Replaces manual onboarding checklists and ad-hoc policy questions. Current repo (`src/`, `python_approach/`, `mcp_servers/`) contains only trading/starter demos — nothing is reused.

### System Functions (High-Level)
1. Flow A: intake → plan (`pending_ingestion` → `agent_processing` → `awaiting_hr_approval`)
2. Flow B: HITL edit/approve → execute (`executing` → `active` / `needs_attention`)
3. Flow C: policy Q&A (direct RAG, cited answers)

### User Classes and Characteristics
| Class | Role | Access |
|---|---|---|
| `employee` | New hire: roadmap, checklist, chat | Own case only (row-level scoping) |
| `hr_admin` | Pipeline, HITL review, trace, kill switch | All cases |
| `service` | n8n intake webhook | `POST /onboarding/trigger` only |

### Design and Implementation Constraints
- Key principle (§1): LLMs reason and draft; deterministic code executes side effects, only after approval.
- Agents never hold write-capable MCP tools during planning (read-only only).
- SSE only (no WebSockets); model name config-driven (`ANTHROPIC_MODEL`).
- Stack locked: FastAPI + Pydantic v2 + SQLAlchemy/Alembic + Arq, Postgres + Redis + Qdrant, Next.js + Tailwind + shadcn/ui + TanStack Query + Zustand, CrewAI, n8n self-hosted.

### Assumptions and Dependencies
- HRIS/Typeform can POST webhooks with hire ID + start date.
- Policy docs available as PDFs with page numbers; doc store can fire change webhooks.
- Anthropic + OpenAI embeddings + Cohere Rerank credentials available; Vault/secrets manager exists.

## 3. Functional Requirements

### System Features and Workflows
- **F-OV-1 Intake (idempotent):** `POST /api/v1/onboarding/trigger` with `Idempotency-Key: {hire_id}:{start_date}`; duplicate → return existing case.
- **F-OV-2 Plan:** Arq job runs plan crew; per-step trace events on Redis `trace:{session_id}` → SSE; Pydantic-validated versioned plan persisted.
- **F-OV-3 HITL:** HR views plan + citations, edits inline (new version + diff), Approve & Execute records approver/timestamp.
- **F-OV-4 Execute:** Iterate approved actions with per-action idempotency keys; retry with backoff; `needs_attention` on persistent failure; never re-run completed.
- **F-OV-5 Chat:** `POST /api/v1/chat`, server-side region/dept resolution, answer-only-from-context with citations; low confidence → "I couldn't find this" + HR escalation.

### Inputs, Processing Logic, and Outputs
| Input | Processing | Output |
|---|---|---|
| Hire record (name, role, dept, region, timezone, manager, buddy, start_date) | Validate → create case → enqueue | `onboarding_case` + job ID |
| Plan crew context | Policy → Experience → Ops-Planner, sequential, `output_pydantic` + retry | `EntitlementSet`, `OnboardingPlan`, `SystemActionPlan` (versioned) |
| Approval decision | Record + enqueue execute | `approvals` row + execution status |

### Use Case Diagrams and Scenarios
- UC-1 HRIS fires hire → HR sees `agent_processing` + live trace → reviews cited plan → approves → tracks per-action status.
- UC-2 Employee opens Hub → ticks checklist → asks "What is my remote home-office budget in the UK?" → cited answer.
- UC-3 Policy doc updated → re-ingest → old version `superseded_by` set → future answers use new version.

### Data Validation and Error Handling
- Pydantic validation on all API inputs and agent outputs; agent validation failure → bounded retry then `needs_attention`.
- Idempotency-Key required on trigger and every external action.
- Chat: retrieval confidence threshold; below → abstain path (no hallucination).

## 4. External Interface Requirements

### User Interfaces (UI/UX Mockups)
See 06-frontend-spec. Two role-gated apps: Employee Hub (timeline, chat, buddy card) and HR Admin Center (pipeline, HITL editor, trace monitor, execution view).

### Hardware Interfaces
None beyond standard cloud hosting (Docker; UI on Vercel or CloudFront).

### Software and Database Interfaces
- Postgres (state/audit/approvals), Redis (Arq queue + SSE pub/sub), Qdrant (hybrid vectors), n8n (webhooks + MCP tools), Notion/Calendar MCPs. Details in 01/03/05.

### Communications and API Interfaces
Full surface (§7 of plan): trigger, `GET /cases?status=`, SSE stream, plan GET/PUT, approvals POST, `me/roadmap`, checklist PATCH, chat POST, admin reindex POST. REST + SSE, JWT bearer.

## 5. System Features and Capabilities

### Core Modules and Subsystems
Parts 01–07 map 1:1 to modules: infra/data, backend gateway, RAG, agent worker, n8n/MCP/executor, frontend, hardening.

### User Authentication and Authorization Roles
SSO/OIDC → JWT; RBAC enforced in FastAPI; employees row-scoped to own `employee_id`. Service key scoped to trigger endpoint. See 02.

### Reporting and Analytics Modules
- `audit_events` (append-only) for every agent step, edit, approval, external action.
- `chat_logs` with citations, confidence, feedback.
- Langfuse/LangSmith for cost/latency per case; OpenTelemetry + Sentry. See 07.

## 6. Non-Functional Requirements (NFRs)

| Category | Target |
|---|---|
| Performance | Sample hire → valid cited plan < ~2 min; chatbot p95 < 5 s (cached entitlements by role+region) |
| Security/Compliance | SSO, RBAC, PII minimization (no national ID/salary/bank in prompts), encryption at rest, GDPR (UK) + India DPDP review with legal |
| Reliability | Idempotency keys, backoff retry, DLQ, kill switch; no unapproved external action in pilot |
| Maintainability | MCP tools behind wrapper interfaces (swap to direct APIs); model string + rerank version config-driven |
| Scalability | Stateless API/worker, Redis queue depth + Qdrant replica as load signals; pilot 10 hires single region |

## 7. Data and System Architecture

### High-Level Architecture Diagrams
```
Next.js (Hub + HR Center) ──REST+SSE/JWT──► FastAPI ──┬── Postgres / Redis / Qdrant-RAG-service
                                                       ├── Arq → CrewAI worker (plan crew) ──► Postgres + Redis traces
                                                       └── n8n (intake webhooks + MCP tool host) ◄── deterministic executor
```

### Entity-Relationship Diagrams (ERD) and Data Models
`employees(1)—(n)onboarding_cases(1)—(n)plans(1)—(n)approvals|actions`; `cases(1)—(n)checklist_items`; `audit_events` and `chat_logs` standalone append-only. Full DDL in 01.

### Data Dictionary and Storage Requirements
Minimum fields per §6 table in plan; retention/deletion policy for PII defined in 07. Postgres is source of truth; Qdrant stores vectors + metadata (`document_name, region, department, page_number, effective_date, superseded_by, version`); Redis is ephemeral (queue + pub/sub).

## 8. Appendix and Change Log

### Document Revision History
| v | Date | Change |
|---|---|---|
| 0.1 | 2026-10-06 | Initial overview derived from plan §§1–12 |

### Open Issues and TBDs
- O-1: Exact Notion + Calendar MCP package names (plan §12 flag; `server-google-maps/calendar` looks wrong).
- O-2: Current Cohere Rerank model + Claude Sonnet-tier string.
- O-3: CrewAI structured-output/callback API version.
- O-4: SSO provider choice vs JWT stub for MVP (see 02).
- O-5: Arq vs Celery final pick (recommend Arq; confirm in 02).
