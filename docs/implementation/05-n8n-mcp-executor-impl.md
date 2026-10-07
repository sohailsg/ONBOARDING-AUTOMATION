# 05 — n8n + MCP + Executor Implementation Plan

## 1. Document Overview and Scope
### Purpose and Objectives
Wire hire intake and host side-effect tools in n8n, then implement the deterministic post-approval executor (no LLM). Done when an approved plan executes end-to-end in a sandbox workspace with per-action audit and exactly-once effects.
### Project Reference Documents (SRS/Spec Links)
Spec: `05-n8n-mcp-executor-spec.md`; Master: `00-overview-impl.md`; Plan §§3,5; triggered via 02 approvals; statuses visible in 06.
### Key Stakeholders and Project Roles
E1 backend (executor owner); E4/integrations (n8n workflows + MCP wiring); HR (sandbox approver, kill-switch operator); IT (Jira/BambooHR field mapping).

## 2. Technical Architecture and Design Strategy
### Technology Stack Selection
n8n self-hosted (webhook node → HTTP to API; MCP Server Trigger for tools), Python executor (`backend/executor/runner.py` + per-tool wrappers), Vault-held credentials, Arq `execute_job`, sandbox Notion/Calendar/test mailbox + test Jira project.
### System High-Level Architecture
`HRIS ─HMAC─► n8n Workflow A ─► POST /onboarding/trigger ─► … approve ─► Arq execute_job(plan_id) ─► runner iterates actions in order: skip succeeded → tools/call {idempotency_key={plan_id}:{idx}} → store external_ref → succeeded; fail → attempts++, backoff 2s/10s/60s → needs_attention + notify; halt → stop remaining`. Tools: `send_email, post_slack, create_ticket, write_hris, create_notion_page, create_invite` — each behind `tools/<name>.py` wrapper (`def run(key, **payload) -> external_ref`) so MCP→direct-API swap is contained.
### Database Schema and Data Models
`actions(id, plan_id FK, type, payload JSONB immutable post-approval, status[pending|running|succeeded|failed|halted], attempts, external_ref, last_error)`; executor transitions only `pending→running→succeeded|failed`, case `executing→active|needs_attention`.
### API Contracts and Integration Specifications
Inbound: HRIS webhook (HMAC) → n8n → API trigger with Idempotency-Key; 3x backoff, DLQ mailbox. Outbound: MCP JSON-RPC `tools/call` with idempotency header; responses mapped to `external_ref` (message-id, ticket key, event id). Halt: `POST /execute/{case_id}/halt` (hr_admin) → runner stops before next action; in-flight settles.

## 3. Work Breakdown Structure (WBS) and Backlog
### Feature-to-Task Decomposition
| ID | Task | Done when |
|---|---|---|
| 5.1 | Verify MCP package names (Notion official, Calendar — not `server-google-maps/calendar`) + spike calls | Decision log in spec §8; sandbox creds working |
| 5.2 | Workflow A (`n8n/workflows/intake.json`): validate → trigger → retry/DLQ | Duplicate HRIS event → single case |
| 5.3 | MCP tool defs (`n8n/mcp_tools/*.json`) + wrapper clients per tool | Each tool callable with idempotency key in sandbox |
| 5.4 | Executor runner (order, skip-succeeded, backoff, halt, audit per action) | Kill-switch drill passes; re-run never duplicates |
| 5.5 | Field mappings (Jira project/issue-type, BambooHR employee fields, email templates, Slack channels) | IT/HR sign-off sheet |
| 5.6 | Sandbox end-to-end (hire → approve → all actions succeeded with external_refs) | Demo recorded; audit complete |

### Task Dependencies and Critical Path
5.1 → 5.2/5.3 → 5.4 → 5.5 → 5.6. Needs 02 trigger/approvals + 04 action shapes. Critical for W7 pilot.
### Definition of Done (DoD)
Sandbox e2e green; duplicate-execute test shows single effects; halt test stops remainder; every action has audit row with attempts + external_ref; sandbox flag enforced by config.

## 4. Resource Allocation and Scheduling
### Team Structure and Core Responsibilities
E4 (or E1) weeks 5–7 on n8n/MCP; E1 on runner 5.4; IT provides mappings week 6; HR approves templates week 6.
### Milestones and Key Delivery Dates
W5: 5.1–5.3 tools callable; W6: 5.4 + mappings; W7: 5.6 sandbox e2e demo.
### Sprint Schedule / Gantt Chart Phase Planning
S4: intake + tools + runner skeleton; S5-start: mappings + e2e. Parallel with W6 frontend (execution view consumes `actions` reads).

## 5. Testing and Quality Assurance Strategy
### Test Environment Setup
Sandbox workspace isolated by config flag (`MCP_MODE=sandbox`); n8n test instance; fake tool server for unit (assert idempotency-key echo).
### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Unit: skip-succeeded, backoff schedule, unknown-type halts, halt-flag check between actions.
- Integration: duplicate `execute_job` → single effects (fake + sandbox); tool timeout → retry → `needs_attention`; halt mid-run.
- UAT: HR approves sample plan in sandbox, verifies email/ticket/page/invite received, then halts a second run mid-way.
### Requirements Traceability Matrix (RTM)
| Spec req | Task | Test |
|---|---|---|
| F-MCP-1 intake+retry | 5.2 | Duplicate-webhook test |
| F-MCP-2 idempotent tools | 5.3 | Double-call single-effect test |
| F-MCP-3 replay+backoff | 5.4 | Retry/DLQ + skip-succeeded tests |
| F-MCP-4 kill switch | 5.4 | Halt-drill test |
| Sandbox enforcement | 5.6 | Prod-cred absence test in sandbox |

## 6. Deployment and DevOps Pipeline
### CI/CD Configuration and Environments (Dev, Staging, Prod)
n8n workflows versioned as JSON in git, imported via API on deploy; executor ships in backend image; `MCP_MODE` + tool URLs per env (dev/staging=sandbox, pilot=real-behind-approval). Promotion requires sandbox e2e green.
### Data Migration and Seeding Strategies
No DDL; action-type registry versioned (`executor/actions_v1`); new types additive with mapping docs.
### Rollback and Disaster Recovery Procedures
Executor rollback safe (succeeded-guard); n8n workflow rollback = re-import prior JSON tag; in-flight halt during rollback; external side effects reconciled via `external_ref` listing (email/ticket search runbook).
### Post-Launch Monitoring and Alerting
Per-tool latency/success, attempts histogram, DLQ depth, halt events; alerts on execute-failure rate, DLQ >0 >15 min, unknown-action-type (halt) event.

## 7. Risk Management and Contingencies
### Technical Risks and Mitigation Actions
| Risk | Mitigation |
|---|---|
| Wrong MCP server names/immaturity | 5.1 verification spike first; wrapper interface allows direct-API fallback |
| Wrong recipient/template (email to wrong hire) | HR template sign-off; sandbox-only until pilot; payload preview in HITL editor |
| Duplicate tickets/charges | Idempotency keys + succeeded-guard + duplicate-execute chaos test |
| Long external outages | Backoff + `needs_attention` + HR notify; resume without re-running succeeded |
### Resource and Timeline Constraints
IT mapping turnaround is the bottleneck — request week 5, escalate week 6; proceed with fake mappings for runner tests meanwhile.
### Change Management Process
New/changed tool or template → wrapper PR + sandbox e2e + mapping sign-off + spec §8 update; no direct n8n edits on shared instances (git-import only).
