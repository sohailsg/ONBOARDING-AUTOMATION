# 06 — Frontend Implementation Plan

## 1. Document Overview and Scope
### Purpose and Objectives
Build the role-gated Next.js apps: Employee Hub + HR Admin Center. Done when HR can intake→review→edit→approve→track without dev help (against real API), and employees complete roadmap + cited chat.
### Project Reference Documents (SRS/Spec Links)
Spec: `06-frontend-spec.md`; Master: `00-overview-impl.md`; consumes 02 REST/SSE (+ OpenAPI codegen); displays 04 traces and 05 execution states.
### Key Stakeholders and Project Roles
E3 frontend (owner); HR (UX sign-off on pipeline/HITL); E1 (API shape support); accessibility reviewer.

## 2. Technical Architecture and Design Strategy
### Technology Stack Selection
Next.js (App Router) + Tailwind + shadcn/ui + TanStack Query + Zustand + native EventSource; MSW for mocks; OpenAPI→TypeScript codegen; httpOnly-cookie JWT, middleware route gates (`/hub` employee, `/admin` hr_admin).
### System High-Level Architecture
SSR first paint → CSR Query mutations (optimistic checklist) → EventSource to `GET /cases/{id}/stream` (reconnect backoff, last-N replay) → Zustand `selectedCaseId/editorDraft/traceEvents[]`. No direct DB; region/dept never sent for chat (server resolves).
### Database Schema and Data Models
Client projections: `Case, PlanVersion, ActionStatus, ChecklistItem, ChatMessage{citations[{doc,page,effective_date}]}` generated from OpenAPI; drafts in memory until PUT plan.
### API Contracts and Integration Specifications
Uses §7 endpoints via generated hooks: trigger/list/stream/plan GET-PUT/approvals/me-roadmap/checklist-PATCH/chat/reindex. SSE event type `{ts, step, message, case_id, session_id}`; signed-URL fallback if header-auth blocked (pending 02 T-3).

## 3. Work Breakdown Structure (WBS) and Backlog
### Feature-to-Task Decomposition
| ID | Task | Done when |
|---|---|---|
| 6.1 | Scaffold (routes, auth gates, theme, Query+Zustand, OpenAPI codegen, MSW fixtures mirroring API) | Mocked pipeline renders from fixtures |
| 6.2 | Employee Hub: timeline + progress, checklist optimistic tick, buddy card | Tick works offline-queue + rollback on error |
| 6.3 | Policy chat: bubbles, blockquote citations (click→page anchor), abstain + Ask-HR | Feedback thumbs logged |
| 6.4 | HR pipeline table (status filter) + case detail tabs | Filter parity with `?status=` |
| 6.5 | HITL editor: sectioned plan + citations, inline edit, diff, Approve & Execute modal | PUT creates version; approve enqueues |
| 6.6 | Trace monitor (SSE feed, auto-scroll, reconnect banner) + Execution view (per-action status/retry/halt) | Kill-switch drill from UI passes |
| 6.7 | A11y + responsive pass (360–1440px, WCAG AA) + UAT fixes | Lighthouse + keyboard walkthrough green |

### Task Dependencies and Critical Path
6.1 → 6.2/6.4 (parallel) → 6.3/6.5 → 6.6 → 6.7. Starts week 5 on MSW mocks; swaps to real API incrementally (list first, then plan/approve, then SSE). Needs 02 OpenAPI stability by week 3.
### Definition of Done (DoD)
All routes against real API in staging; optimistic paths tested; SSE reconnect covered; HR UAT (3 hires, unaided) signed; a11y + perf budgets (LCP <2.5 s) met.

## 4. Resource Allocation and Scheduling
### Team Structure and Core Responsibilities
E3 full-time weeks 6–9; E1 on-call for API shape questions; HR 2 UAT sessions (weeks 7, 9).
### Milestones and Key Delivery Dates
W6: 6.1–6.2 mocked; W7: 6.4–6.5 vs real API; W8: 6.3+6.6; W9: 6.7 + unaided-HR demo.
### Sprint Schedule / Gantt Chart Phase Planning
S4–S5 overlapping W5 integrations; mock-first protects frontend from backend slippage; weekly API-diff check with E1.

## 5. Testing and Quality Assurance Strategy
### Test Environment Setup
Vitest + Testing Library + Playwright; MSW handlers versioned with API fixtures; a11y (axe) + Lighthouse CI.
### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Unit: progress calc, diff render, citation links, optimistic rollback.
- Integration (Playwright vs staging): login→pipeline→edit→approve→trace→execution-halt; employee tick + chat abstain path.
- UAT: HR runs full flow on 3 hires unaided; employees test chat wording + escalation.
### Requirements Traceability Matrix (RTM)
| Spec req | Task | Test |
|---|---|---|
| F-UI-1 timeline/checklist | 6.2 | Optimistic-rollback test |
| F-UI-2 cited chat | 6.3 | Citation-click + abstain tests |
| F-UI-5 HITL+diff+approve | 6.5 | Version+approve e2e |
| F-UI-6 trace SSE | 6.6 | Reconnect-banner test |
| F-UI-7 execution+halt | 6.6 | Halt-button e2e |

## 6. Deployment and DevOps Pipeline
### CI/CD Configuration and Environments (Dev, Staging, Prod)
Vercel (or CloudFront) preview per PR (MSW) → staging (real API) → pilot (gated). Env: API base, auth cookie domain, SSE URL. OpenAPI codegen runs in CI; type drift fails build.
### Data Migration and Seeding Strategies
No client data; MSW fixture version pinned to API commit; cache invalidation via Query keys on version bump.
### Rollback and Disaster Recovery Procedures
Instant static rollback (prior deployment); API-version mismatch banner (client detects OpenAPI hash drift); no data loss (server is truth).
### Post-Launch Monitoring and Alerting
Web Vitals, route error rate, SSE disconnect rate, chat feedback score; alerts on LCP regression, 403 spike (role misconfig), approve-button error rate.

## 7. Risk Management and Contingencies
### Technical Risks and Mitigation Actions
| Risk | Mitigation |
|---|---|
| API shape drift | Codegen in CI; weekly E1/E3 sync; MSW fixtures regenerated, not hand-edited |
| SSE auth via EventSource headers | Signed-URL fallback decided S2; banner+retry for disconnects |
| HITL editor complexity | Ship sectioned read-only + per-section edit first; full rich-diff second |
| Scope creep (HR asks) | Freeze to §4 scope for pilot; extras to backlog with HR-owner priority |
### Resource and Timeline Constraints
Single frontend owner; protect 6.5/6.6 (HITL + execution) — defer chat polish (6.3 extras) if needed.
### Change Management Process
UI copy/layout tweaks via PR + screenshot; flow changes (tabs, approval steps) need HR sign-off + spec §4 update.
