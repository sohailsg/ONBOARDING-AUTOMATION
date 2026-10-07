# 04 — Agent Worker Implementation Plan

## 1. Document Overview and Scope
### Purpose and Objectives
Build the background plan crew that drafts (never executes) versioned, cited onboarding plans. Done when a sample hire yields a schema-valid cited plan in <~2 min with live SSE traces.
### Project Reference Documents (SRS/Spec Links)
Spec: `04-agent-worker-spec.md`; Master: `00-overview-impl.md`; consumes 03 (`policy_retrieve`) + Calendar read-only; enqueued by 02; observed in 06.
### Key Stakeholders and Project Roles
E2 agent engineer (owner); HR (plan-schema + citation-quality sign-off); E1 (Arq/Redis wiring support).

## 2. Technical Architecture and Design Strategy
### Technology Stack Selection
CrewAI (`Process.sequential`), Pydantic v2 `output_pydantic`, Arq worker pool, `redis.asyncio` trace publisher, Langfuse/OTel callbacks, Sonnet-tier model via `ANTHROPIC_MODEL` env (config-driven).
### System High-Level Architecture
`Arq plan_job(case_id, session_id): set agent_processing → Policy(policy_retrieve) → Experience(find_slots) → Ops-Planner(no tools) → validate → INSERT plans(version+1, created_by='agent') + draft checklist_items → set awaiting_hr_approval → publish traces per step to trace:{session_id} + audit_events`.
### Database Schema and Data Models
Writes: `plans.json_payload = {entitlements: EntitlementSet, plan: OnboardingPlan, actions: SystemActionPlan}`; `onboarding_cases.current_plan_version`; draft `checklist_items`; per-step `audit_events`. Schemas: `Entitlement{kind, detail, citation{doc,page,effective_date}}`; `Milestone{phase: Day1|Week1|Month1, items[{title,due_day,mandatory}]}`; `Action{type, payload (discriminated), idempotency_key}`.
### API Contracts and Integration Specifications
Job signature `plan_job(case_id: UUID, session_id: str)`; tools: `policy_retrieve(query, region, dept) → cited chunks` (03 wrapper, read-only), `find_slots(attendees, window) → slots[]` (Calendar MCP read-only). Trace event `{ts, step, message, case_id, session_id}`. Validation failure → 1 self-repair retry → else `needs_attention` + audit.

## 3. Work Breakdown Structure (WBS) and Backlog
### Feature-to-Task Decomposition
| ID | Task | Done when |
|---|---|---|
| 4.1 | Schemas (`schemas.py`) + fixture plans + validator tests | Invalid plan rejected in unit test |
| 4.2 | Read-only tool wrappers (`policy_retrieve`, `find_slots`) + prompt-injection guard tests | Tool with write attempt blocked; injection fixture ignored |
| 4.3 | Three agents + sequential crew + `output_pydantic` + retry | Sample hire → valid plan locally |
| 4.4 | Arq `plan_job` (status transitions, version insert, trace publish, audit) | `agent_processing → awaiting_hr_approval` + SSE visible |
| 4.5 | Caps (≤12 steps, ≤30k tokens/run), entitlement cache `(role,region)`, Langfuse cost logging | Cost/latency per case dashboarded |
| 4.6 | HR citation-quality pass (20 plans graded) | Citation precision ≥ target agreed with HR |

### Task Dependencies and Critical Path
4.1 → 4.2 → 4.3 → 4.4 → 4.5/4.6. Needs W3 retrieve + W2 enqueue. S1 spike first: verify CrewAI structured-output/callback API version (plan §12 TBD).
### Definition of Done (DoD)
Valid cited plan <2 min on seed hire; traces stream to 06 monitor; no write-tool import in worker image (CI grep); guardrail tests green; cost per plan recorded.

## 4. Resource Allocation and Scheduling
### Team Structure and Core Responsibilities
E2 full-time weeks 4–5; E1 half-day Arq/Redis help; HR 2-hour grading session week 5.
### Milestones and Key Delivery Dates
W4: 4.1–4.3 local plan generation; W5: 4.4–4.6 + <2 min benchmark + HR sign-off on schema.
### Sprint Schedule / Gantt Chart Phase Planning
S3: schemas→agents→job→SSE; buffer 2 days for CrewAI API surprises (pin version, wrap client).

## 5. Testing and Quality Assurance Strategy
### Test Environment Setup
CrewAI with recorded tool fixtures (no live LLM in unit); live-model nightly for e2e timing; fakeredis for trace assertions.
### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Unit: schema validation, retry-on-invalid, injection-ignored, no-write-tool import test.
- Integration: `plan_job` full run on seed hire (status + version + traces + audit); duplicate job dedupe; cap-enforcement (long-hire still terminates).
- UAT: HR reviews 3 generated plans (citations click through, milestones sensible) before W5 exit.
### Requirements Traceability Matrix (RTM)
| Spec req | Task | Test |
|---|---|---|
| F-AG-1 Policy+citations | 4.2/4.3 | Citation-presence test |
| F-AG-2 slots read-only | 4.2 | Write-tool grep + scope test |
| F-AG-3 no-tool Ops planner | 4.3 | Tool-call count = 0 assertion |
| F-AG-4 sequential+retry | 4.3/4.4 | Invalid-output repair test |
| F-AG-5 traces+audit | 4.4 | Redis publish + audit row test |
| Caps + injection guard | 4.2/4.5 | Injection fixture + cap test |

## 6. Deployment and DevOps Pipeline
### CI/CD Configuration and Environments (Dev, Staging, Prod)
PR: fixture-based tests (fast, no LLM). Nightly/staging: live-model e2e + timing + cost capture; image ships worker + read-only MCP creds only. Model string via env per env.
### Data Migration and Seeding Strategies
No DDL; prompt/schema changes versioned (`prompts/vN`) with plan-version linkage for reproducibility.
### Rollback and Disaster Recovery Procedures
Worker image rollback safe (jobs dedupe by idempotency); poison job → DLQ after N attempts with `needs_attention`; in-flight job on deploy drains before shutdown.
### Post-Launch Monitoring and Alerting
Langfuse: tokens/cost/latency per case, validation-retry rate; OTel: job duration, step counts; alerts on e2e >2 min trend, retry-rate spike, cap-hit rate.

## 7. Risk Management and Contingencies
### Technical Risks and Mitigation Actions
| Risk | Mitigation |
|---|---|
| CrewAI API drift (`output_pydantic`/callbacks) | S1 spike + pin; wrapper isolates upgrade |
| Slow/expensive runs | Caps + entitlement cache; nightly cost review vs budget |
| Prompt injection via docs/forms | Ignore-embedded-instructions system prompt + fixture tests |
| Calendar MCP unreadable scope | Degrade to TBD slots (never invent); surface in plan for HR edit |
### Resource and Timeline Constraints
E2 shared with W3; W3 gate must be green before 4.3 live runs — use fixtures meanwhile to protect schedule.
### Change Management Process
Prompt/model/tool change → prompt-version bump + fixture refresh + nightly e2e + spec §8 note; HR re-grades citations on planner-affecting changes.
