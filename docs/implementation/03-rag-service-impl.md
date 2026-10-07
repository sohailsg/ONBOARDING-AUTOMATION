# 03 — RAG Service Implementation Plan

## 1. Document Overview and Scope
### Purpose and Objectives
Build the shared retrieval service (chatbot + Policy Agent) with hybrid search, rerank, citations, and an eval CI gate. Done when golden-set Faithfulness ≥0.9 and `/chat` path returns cited answers with abstain behavior.
### Project Reference Documents (SRS/Spec Links)
Spec: `03-rag-service-spec.md`; Master: `00-overview-impl.md`; Plan §9; feeds 02-chat and 04-`policy_retrieve`.
### Key Stakeholders and Project Roles
E2 RAG/agent engineer (owner); HR (golden Q&A contributors across regions); tech lead (eval-gate approver).

## 2. Technical Architecture and Design Strategy
### Technology Stack Selection
LlamaIndex (or Unstructured) chunking, `text-embedding-3-small` dense + BM25 sparse, Qdrant hybrid + RRF, Cohere Rerank, config-driven model strings, RAGAS for eval, Langfuse tracing.
### System High-Level Architecture
`PDFs → ingest (1024/256 parent-child, page nos) → embed → Qdrant upsert (payload: doc/region/dept/page/effective_date/superseded_by/version/chunker_v/parent_id) → retrieve: pre-filter → hybrid top30 RRF → rerank → top5 → parent-expand → answer LLM (context-only) → {answer, citations, confidence} → abstain if < threshold`.
### Database Schema and Data Models
Qdrant collection `policies_v1` (dense + sparse vectors + payload); Postgres `chat_logs` written by 02 (not here). Chunk IDs deterministic (`doc:page:child`) for idempotent upserts.
### API Contracts and Integration Specifications
Internal: `retrieve(query, region, dept, k=30) → chunks[{text, doc, page, effective_date, score}]`; `answer(query, chunks) → (text, citations[], confidence)`; webhook `POST /rag/reindex {doc_id, version}` sets old `superseded_by`. Filters: `region==user.region AND (dept==all OR ==user.dept) AND effective_date<=today AND superseded_by IS NULL`.

## 3. Work Breakdown Structure (WBS) and Backlog
### Feature-to-Task Decomposition
| ID | Task | Done when |
|---|---|---|
| 3.1 | Ingest pipeline (PDF→chunks→embed→upsert + page preservation) | 3 sample policies queryable with page cites |
| 3.2 | Hybrid retrieve + filters + rerank + parent-expand | top-5 precision spot-checked by HR on 20 queries |
| 3.3 | Answer path (context-only prompt, citations, confidence, abstain) | Abstain triggers on out-of-scope; no uncited claims |
| 3.4 | Lifecycle webhook (version bump, `superseded_by`, never delete) | Old answers reproducible from superseded vectors |
| 3.5 | Golden set (100+ Q&A multi-region) + RAGAS eval + CI gate (<0.9 fails) | Gate green on main |
| 3.6 | Cache `(role,region)` entitlement lookups + Langfuse cost logging | p95 retrieval <1.5 s |

### Task Dependencies and Critical Path
3.1 → 3.2 → 3.3 → 3.5 (gate); 3.4 + 3.6 parallel. Unblocks 04-policy tool and 02-chat integration. Start immediately after W1.
### Definition of Done (DoD)
Ingest idempotent; filters enforced in code (not prompt); citations include doc+page+date; eval gate in CI; latency targets met on seed corpus.

## 4. Resource Allocation and Scheduling
### Team Structure and Core Responsibilities
E2 full-time weeks 2–3; HR provides 30 seed Q&A week 2, 70+ week 3; tech lead reviews prompt + abstain threshold.
### Milestones and Key Delivery Dates
W2: 3.1–3.3 demo (cited answers on UK + 1 more region); W3: 3.4–3.6 + gate green.
### Sprint Schedule / Gantt Chart Phase Planning
S2: ingest→retrieve→answer vertical slice; S3: lifecycle + eval hardening + cache. Buffer: chunk-size tuning (1024/256 → adjust on recall).

## 5. Testing and Quality Assurance Strategy
### Test Environment Setup
Ephemeral Qdrant collection per CI run (`policies_test`); pinned embedding/rerank mocks for unit, live APIs for nightly eval.
### Unit, Integration, and User Acceptance Testing (UAT) Plans
- Unit: chunker page preservation; filter SQL/payload correctness; idempotent upsert.
- Integration: reindex supersede flow; rerank ordering on adversarial queries; abstain on empty retrieval.
- UAT: HR grades 20 answers (citation correctness); sign-off on "I couldn't find this" wording + escalation.
### Requirements Traceability Matrix (RTM)
| Spec req | Task | Test |
|---|---|---|
| F-RAG-1 ingest+pages | 3.1 | Page-citation test |
| F-RAG-2 filters | 3.2 | Region/dept/date isolation test |
| F-RAG-3 hybrid→rerank→expand | 3.2 | Recall@5 on golden set |
| F-RAG-4 cite/abstain | 3.3 | Uncited-claim grep = 0; abstain test |
| F-RAG-5 lifecycle | 3.4 | Supersede integration |
| F-RAG-6 eval gate | 3.5 | CI fails when Faithfulness <0.9 (mutation test) |

## 6. Deployment and DevOps Pipeline
### CI/CD Configuration and Environments (Dev, Staging, Prod)
PR: unit + mocked-retrieval tests. Nightly/main: full RAGAS eval on live APIs; gate blocks deploy. Reindex workflow separate (doc webhook → staging eval → promote collection alias `policies_v1`).
### Data Migration and Seeding Strategies
Collection versioning (`policies_v1 → v2` alias swap); chunker version in payload for reproducibility; seed policies (anonymized) in dev only.
### Rollback and Disaster Recovery Procedures
Alias rollback to prior collection snapshot; Qdrant snapshot before every reindex; answer path degrades to abstain if index unavailable (never hallucinate).
### Post-Launch Monitoring and Alerting
Retrieval latency, rerank score distribution, confidence histogram, abstain rate, Faithfulness trend (Langfuse); alerts on abstain spike (stale index?) or Faithfulness drop.

## 7. Risk Management and Contingencies
### Technical Risks and Mitigation Actions
| Risk | Mitigation |
|---|---|
| Poor recall on region-specific perks | Golden-set per region; chunk-size + filter tuning; parent-expand budget ↑ |
| Embedding/rerank cost/latency | Cache entitlements; batch rerank; nightly (not per-PR) full eval |
| Version-string drift (Cohere/model) | Env-pinned + S1 verification spike; wrapper client isolates change |
| PDF extraction quality | Unstructured↔LlamaIndex A/B on sample; page-anchor QA by HR |
### Resource and Timeline Constraints
E2 also owns W4; protect eval-gate week by timeboxing chunk tuning (2 days) then moving on with documented tradeoff.
### Change Management Process
Chunker/embedding/rerank change = new collection version + full eval + spec §7 update; no in-place index mutation on shared envs.
