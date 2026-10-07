# 05 — n8n + MCP + Executor Spec (Intake Webhooks, Tool Hosting, Deterministic Execution)

## 1. Introduction and Overview
### Purpose and Audience
Defines n8n's two jobs only (inbound intake, outbound tool host) plus the deterministic post-approval executor. Audience: integration/backend engineers.
### Project Scope and Exclusions
In scope: Workflow A, n8n MCP Server Trigger tools, Notion/Calendar MCP wiring, executor with idempotency/retry/kill-switch. Excludes: agent reasoning (04), UI (06).
### Definitions, Acronyms, and Abbreviations
Workflow A = HRIS/Typeform → `POST /onboarding/trigger`. MCP Server Trigger = n8n exposes tools over MCP. Sandbox mode = tools pointed at test workspace.
### References and Supporting Material
Plan §§2,3,5 (Flow B), 12; 00-overview; 02 (trigger/approvals API); n8n MCP Trigger + Notion/Calendar MCP docs.

## 2. General System Description
### Product Perspective and Context
n8n is glue, not brain: receives hire webhooks and hosts side-effect tools; executor (Python, invoked by Arq `execute_job`) replays the approved plan deterministically — LLM never decides post-approval content.
### System Functions (High-Level)
Ingest hires; expose `send_email/post_slack/create_ticket/write_hris/create_notion_page/create_invite` tools; execute approved actions exactly once each.
### User Classes and Characteristics
HRIS (webhook sender); HR admin (approver, kill-switch operator); engineer (tool wrapper maintainer).
### Design and Implementation Constraints
Every tool behind own wrapper interface (swap to direct APIs if MCP immature); write credentials least-privilege, server-side only; sandbox mode for Phases 3–4.
### Assumptions and Dependencies
n8n self-hosted reachable from API and executor; sandbox Notion/Calendar/test mailbox exist.

## 3. Functional Requirements
- **F-MCP-1 Workflow A:** on HRIS webhook validate → `POST /api/v1/onboarding/trigger` with `Idempotency-Key`; retry 3x backoff; DLQ to HR inbox on failure.
- **F-MCP-2 Tools (via n8n MCP):** `send_email`, `post_slack`, `create_ticket` (Jira/helpdesk), `write_hris` (BambooHR), plus Notion (`create_workspace`) and Calendar (`create_invite`) MCPs — all idempotent (caller-supplied key: `{plan_id}:{action_index}`).
- **F-MCP-3 Executor:** for each action in approved `SystemActionPlan` in order: skip if `status==succeeded`; else call tool → store `external_ref` → `status=succeeded`; on error increment `attempts`, `last_error`, backoff; after N fails → `needs_attention` + HR notify; completed never re-run.
- **F-MCP-4 Kill switch:** HR `POST /execute/{case_id}/halt` stops remaining actions; in-flight action allowed to settle; audit logged.
- Validation/errors: payload schema per action type; unknown type → halt + `needs_attention` (no silent skip).

## 4. External Interface Requirements
### User Interfaces
n8n editor (engineers only); HR uses 06 execution view (status/retry/halt buttons call 02 → executor).
### Hardware Interfaces
None.
### Software and Database Interfaces
Executor: Postgres (`actions` rows), Redis (execute job queue), n8n MCP endpoint + Notion/Calendar MCP endpoints via wrapper clients.
### Communications and API Interfaces
Inbound: HRIS→n8n webhook (HMAC verified) → API trigger. Outbound: executor→MCP `tools/call` JSON-RPC with idempotency key header; callbacks store `external_ref` (message ID, ticket key, event ID).

## 5. System Features and Capabilities
### Core Modules and Subsystems
`n8n/workflows/intake.json`, `n8n/mcp_tools/*.json`, `backend/executor/{runner.py, tools/{email,slack,ticket,hris,notion,calendar}.py}`, sandbox config flag.
### User Authentication and Authorization Roles
n8n webhook HMAC + service key to API; MCP credentials in Vault, scoped per tool; HR halt requires `hr_admin`.
### Reporting and Analytics Modules
Per-action audit (`actor=system:executor`, metadata `{tool, attempts, external_ref, latency}`); execution dashboard data from `actions` table.

## 6. Non-Functional Requirements (NFRs)
- Performance: single-case execute p95 < 3 min (excl. external SLA); tool timeout 20 s default.
- Security: no LLM in execute path; secrets never in plan payload; sandbox enforced by config until pilot sign-off.
- Reliability: exactly-once effect via idempotency keys + `succeeded` guard; backoff (2s,10s,60s) then DLQ.
- Maintainability: wrapper interface per tool (`def send_email(key, to, subject, body) -> external_ref`).
- Scalability: executor concurrency bounded (e.g. 5 parallel cases); per-tool rate limits respected.

## 7. Data and System Architecture
### High-Level Architecture Diagrams
`HRIS ─► n8n A ─► API trigger ─► ... approve ─► Arq execute_job ─► executor ──MCP──► n8n tools / Notion / Calendar ─► external_ref ─► Postgres actions`.
### Entity-Relationship Diagrams (ERD) and Data Models
`actions(id, plan_id FK, type, payload JSONB, status[pending,running,succeeded,failed,halted], attempts, external_ref, last_error)`; one row per planned action, immutable payload post-approval.
### Data Dictionary and Storage Requirements
Action types: `send_email{to,subject,body}`, `create_notion_page{template,owner}`, `create_invite{attendees,start,end}`, `create_ticket{queue,title,body}`, `post_slack{channel,text}`; all carry `idempotency_key`.

## 8. Appendix and Change Log
### Document Revision History
| v | Date | Change |
|---|---|---|
| 0.1 | 2026-10-06 | Initial n8n/MCP/executor spec from plan §§3,5 |
### Open Issues and TBDs
- T-1: Verify exact Notion + Calendar MCP server package names (flagged wrong `server-google-maps/calendar`).
- T-2: Sandbox workspace IDs + test accounts.
- T-3: Ticket/HRIS field mappings (Jira project, BambooHR employee fields).
