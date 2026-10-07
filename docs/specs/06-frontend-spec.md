# 06 — Frontend Spec (Employee Hub + HR Admin Center)

## 1. Introduction and Overview
### Purpose and Audience
Defines the two role-gated Next.js apps in one codebase. Audience: frontend engineers, UX/HR stakeholders.
### Project Scope and Exclusions
In scope: Employee Hub (roadmap/chat/buddy), HR Center (pipeline/HITL editor/trace/execution), auth gating, SSE client. Excludes: backend/RAG/agent logic (02–04); builds against mocked plans in parallel with Phase 3.
### Definitions, Acronyms, and Abbreviations
TanStack Query (server state), Zustand (UI state), EventSource (SSE), shadcn/ui components.
### References and Supporting Material
Plan §§2–4,7; 00-overview; 02 (API/SSE contracts); 04 (trace event shape).

## 2. General System Description
### Product Perspective and Context
Single Next.js + Tailwind + shadcn/ui deployment, route-gated by JWT role (`/hub` employee, `/admin` HR). All data via 02 REST + SSE.
### System Functions (High-Level)
Render 30-day timeline + checklist; embedded policy chat with citations; buddy/manager card; pipeline table; HITL plan editor + Approve & Execute; live trace; per-action execution status + halt.
### User Classes and Characteristics
Employee (low training, mobile-friendly); HR admin (power user, desktop, needs diff/citation review + speed).
### Design and Implementation Constraints
No secrets in client; region/dept never sent from client for chat scoping (server resolves); SSE only (no sockets); accessible (WCAG AA) + responsive.
### Assumptions and Dependencies
02 API + SSE available (or MSW mocks with identical shapes during parallel build).

## 3. Functional Requirements
- **F-UI-1 Timeline:** Day 1 / Week 1 / Month 1 milestones + progress bar; mandatory vs optional badges; `PATCH checklist` on tick with optimistic update + rollback.
- **F-UI-2 Chat:** embedded panel; messages with inline blockquote citations (click → doc page anchor); abstain state ("couldn't find") + "Ask HR" escalation button.
- **F-UI-3 Buddy card:** photo, role, timezone, calendar link (`find_slots` output rendered).
- **F-UI-4 Pipeline:** table filterable by status (`pending_ingestion…active`); row → case detail.
- **F-UI-5 HITL editor:** sections (schedule, welcome email, Notion spec, invites, tickets) each with policy citations; inline edit → diff view; **Approve & Execute** confirm modal → `POST approvals`.
- **F-UI-6 Trace monitor:** SSE-driven step feed (`Searching Qdrant for UK leave policy...`); auto-scroll, reconnect with backoff.
- **F-UI-7 Execution view:** per-action status/attempts/error + retry + kill switch button.
- Validation/errors: form validation inline; 403 → "contact HR"; SSE disconnect → banner + retry; optimistic checklist revert on 4xx/5xx.

## 4. External Interface Requirements
### User Interfaces (UI/UX Mockups)
Routes: `/hub` (timeline, chat drawer, buddy card), `/admin` (pipeline, `/admin/cases/[id]` with Plan/Trace/Execution tabs). shadcn: Table, Tabs, Sheet (HITL), Chat bubble, Timeline, Badge, Alert. Mockups to be added as Figma links in Appendix.
### Hardware Interfaces
Responsive 360px–1440px; no native requirements.
### Software and Database Interfaces
No direct DB; only 02 REST/SSE via `fetch` + `EventSource` wrapped in TanStack Query hooks.
### Communications and API Interfaces
Consumes §7 endpoints; SSE `GET /cases/{id}/stream` with JWT (or signed-URL fallback per 02 T-3); payloads typed from OpenAPI codegen.

## 5. System Features and Capabilities
### Core Modules and Subsystems
`frontend/app/(hub)/`, `app/(admin)/`, `components/{timeline,chat,buddy,pipeline,plan-editor,trace,execution}.tsx`, `lib/{api.ts, sse.ts, store.ts}`.
### User Authentication and Authorization Roles
SSO login → JWT in httpOnly cookie; middleware gates `/hub` (employee) vs `/admin` (hr_admin); row scoping enforced server-side (client only hides).
### Reporting and Analytics Modules
Client logs checklist completion + chat feedback (thumbs) → `chat_logs.feedback`; trace latency displayed from event timestamps.

## 6. Non-Functional Requirements (NFRs)
- Performance: LCP < 2.5 s; route transitions < 200 ms (cached query); SSE render < 100 ms/event.
- Security: httpOnly auth, no PII in localStorage, CSP headers.
- Reliability: offline checklist retry queue; SSE exponential reconnect.
- Maintainability: generated API types from OpenAPI; storybook for shadcn composites.
- Scalability: static export/CDN (Vercel/CloudFront); no client-side fan-out.

## 7. Data and System Architecture
### High-Level Architecture Diagrams
`Browser ──REST/SSE──► FastAPI ─► Postgres/Redis; Next.js SSR for first paint, CSR + Query for mutations, EventSource for traces`.
### Entity-Relationship Diagrams (ERD) and Data Models
Client models mirror 01 tables (read-only projections): `Case, PlanVersion, ActionStatus, ChecklistItem, ChatMessage{citations[]}`; Zustand holds `selectedCaseId, editorDraft, traceEvents[]`.
### Data Dictionary and Storage Requirements
No persistent client storage except auth cookie + query cache; drafts held in memory until PUT plan.

## 8. Appendix and Change Log
### Document Revision History
| v | Date | Change |
|---|---|---|
| 0.1 | 2026-10-06 | Initial frontend spec from plan §4 |
### Open Issues and TBDs
- T-1: Figma mockups for timeline + HITL editor (link here).
- T-2: SSE auth approach pending 02 T-3 decision.
- T-3: MSW mock dataset for parallel Phase 3/4 build.
