# 07 — Hardening & Rollout Implementation Plan

## 1. Document Overview and Scope
### Purpose and Objectives
Prove the system is secure, observable, and operable, then run a fixed-scope pilot (1 region/dept, ~10 hires) with zero unapproved side effects. Go/no-go gate for production.
### Project Reference Documents (SRS/Spec Links)
Spec: `07-hardening-spec.md`; Master: `00-overview-impl.md` (NFRs, RTM); consumes exits of 01–06; legal guidance (GDPR UK + India DPDP).
### Key Stakeholders and Project Roles
Tech lead + SRE (owner); security reviewer; HR pilot lead (approver roster, hire cohort); legal (retention sign-off); on-call engineer.

## 2. Technical Architecture and Design Strategy
### Technology Stack Selection
Vault (or cloud secrets manager) agent injection; OTel collector + Grafana; Sentry (backend/worker/frontend); Langfuse (LLM cost/latency/quality); `pg_cron` retention jobs; ZAP + dependency/secret scans in CI; PagerDuty/Slack alerts.
### System High-Level Architecture
Same as 00 + sidecars: `API/Worker/RAG/MCP ─OTel─► collector ─► metrics/traces; ─Sentry─► errors; LLM ─► Langfuse`. Audit stays append-only; retention jobs redact/delete per policy; kill switch + DLQ drain paths tested in game day.
### Database Schema and Data Models
No new tables. Policies annotate 01 tables: `audit_events` retained longest + immutable; `chat_logs` PII-redacted after N months (legal confirms N); trace payloads PII-scrubbed before `audit_events` insert.
### API Contracts and Integration Specifications
No new public APIs. Alert webhooks: DLQ depth, Faithfulness <0.9, 5xx spike, execute-failure rate. Auditor export: read-only `audit_events` CSV with redaction.

## 3. Work Breakdown Structure (WBS) and Backlog
### Feature-to-Task Decomposition
| ID | Task | Done when |
|---|---|---|
| 7.1 | Secrets: Vault paths, rotation runbook, least-privilege MCP creds, secret-scan CI | No secret in git; rotation rehearsed |
| 7.2 | PII: prompt/log/vector allowlist, retention + redaction jobs (chat 12 mo / traces 6 mo proposed) | Legal sign-off; job dry-run clean |
| 7.3 | Audit: immutability test, export, per-action completeness check | Auditor verifies full hire trail |
| 7.4 | Observability: OTel dashboards, Sentry wiring, Langfuse per-case cost/latency + Faithfulness trend | Dashboards linked in runbook |
| 7.5 | Resilience: load (20 concurrent cases), chaos (duplicate trigger/execute, Qdrant outage → abstain), kill-switch + DLQ drills | SLOs held; drill log signed |
| 7.6 | Runbooks (`oncall, reindex, kill-switch, secrets-rotation`) + game day | On-call resolves simulated page unaided |
| 7.7 | Pilot: 10 hires, weekly report (latency, Faithfulness/answer rate, action success, cost/hire) + go/no-go | Zero unapproved actions; no unresolved `needs_attention` >24 h |

### Task Dependencies and Critical Path
7.1 → 7.2 → 7.3/7.4 (parallel) → 7.5 → 7.6 → 7.7. Needs all prior W-exits; longest lead: legal retention decision — request week 8.
### Definition of Done (DoD)
Scans green, drills logged, dashboards live, pilot report complete, go/no-go signed by tech lead + HR + security.

## 4. Resource Allocation and Scheduling
### Team Structure and Core Responsibilities
SRE + tech lead weeks 10–12; E1/E2 on-call for fixes; HR pilot lead owns cohort + approver roster; legal consulted week 8–9.
### Milestones and Key Delivery Dates
W10: 7.1–7.4; W11: 7.5–7.6 + game day; W12: 7.7 pilot + report + decision.
### Sprint Schedule / Gantt Chart Phase Planning
S6 split: hardening sprint (1.5 weeks) → pilot (1.5 weeks). 50% of S6 held as buffer for findings from 7.5.

## 5. Testing and Quality Assurance Strategy
### Test Environment Setup
Staging mirrors pilot (backups on, sandbox tools) for 7.5 chaos; pilot env is prod-like with real tools behind approval gate.
### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Security: RBAC matrix re-run, ZAP baseline, `UPDATE/DELETE audit_events` must fail, log PII grep = 0.
- Load: 20 concurrent cases (2x pilot); API p95 <300 ms, plan <2 min sustained.
- Chaos: duplicate trigger + duplicate execute → single effects; kill mid-run; RAG outage → abstain (no hallucination); DLQ drain <4 h.
- UAT (pilot): HR approves real hires; employees use hub + chat; weekly HR satisfaction check.
### Requirements Traceability Matrix (RTM)
| Spec req | Task | Test |
|---|---|---|
| F-HD-1 least-privilege | 7.1 | RBAC + cred-scope tests |
| F-HD-2 PII/retention | 7.2 | Redaction dry-run + legal sign |
| F-HD-3 audit complete | 7.3 | Full-trail export test |
| F-HD-4 observability | 7.4 | Dashboard presence check |
| F-HD-5 resilience | 7.5 | Chaos + drill logs |
| F-HD-6 pilot success | 7.7 | Pilot report metrics |

## 6. Deployment and DevOps Pipeline
### CI/CD Configuration and Environments (Dev, Staging, Prod)
Staging auto-deploys; pilot promotion manual + checklist (scans green, eval gate green, backup verified, runbooks linked). Freeze non-critical merges during pilot.
### Data Migration and Seeding Strategies
Pilot uses real HRIS data only; pre-pilot backup snapshot; retention jobs run in `dry-run` week 11, live after sign-off.
### Rollback and Disaster Recovery Procedures
Image rollback + migration forward-fix; Postgres PITR (RTO <1 h, RPO <15 min) rehearsed; Qdrant snapshot restore; Redis rebuild from DB. Rollback decision tree in on-call runbook.
### Post-Launch Monitoring and Alerting
Grafana: request/job latency, queue depth, Qdrant latency, action success; Langfuse: cost/hire, Faithfulness; Sentry: error rate. Page on: DLQ >0 15 min, Faithfulness <0.9, 5xx spike, execute-failure burst. Weekly pilot report auto-generated.

## 7. Risk Management and Contingencies
### Technical Risks and Mitigation Actions
| Risk | Mitigation |
|---|---|
| Legal delays retention decision | Proceed with strictest proposed default; adjust after sign-off |
| Pilot HR overload (`needs_attention`) | 24 h SLA + on-call pairing; pause intake via Workflow A toggle |
| Cost overrun (LLM/rerank) | Langfuse budget alert; entitlement cache; nightly cost review |
| Alert fatigue | Page only on pilot-blocking signals; rest to Slack digest |
### Resource and Timeline Constraints
Pilot scope frozen (1 region, ~10 hires) — expansion requests go to post-pilot backlog regardless of pressure.
### Change Management Process
Pilot freeze: only P0 fixes + approved runbook actions; all else queued. Post-pilot retro updates specs 00–07 + impl docs before wider rollout.
