# 03 — RAG Service Spec (Ingestion, Hybrid Retrieval, Chat)

## 1. Introduction and Overview
### Purpose and Audience
Defines the shared retrieval service used by both the employee chatbot (Flow C) and the Policy Agent (04). Audience: ML/RAG engineers.
### Project Scope and Exclusions
In scope: ingestion, Qdrant hybrid index, filtered retrieval + rerank, `/chat` answer path with citations, golden eval + CI gate. Excludes agent orchestration (04) and frontend chat UI (06).
### Definitions, Acronyms, and Abbreviations
Parent-child chunks (~1024/256 tokens); RRF (reciprocal rank fusion of dense + BM25/BM42 sparse); RAGAS metrics (Context Recall, Faithfulness, Answer Relevance).
### References and Supporting Material
Plan §9; 00-overview; 01 (Qdrant); Unstructured/LlamaIndex, `text-embedding-3-small`, Cohere Rerank docs.

## 2. General System Description
### Product Perspective and Context
Standalone module (`rag-service/`) so chatbot (one retrieval + one LLM call) and Policy Agent use identical retrieval — faster/cheaper than routing chat through agents.
### System Functions (High-Level)
Ingest PDFs → chunk + embed → hybrid index → filtered retrieve → rerank → cite → abstain when uncertain.
### User Classes and Characteristics
Internal callers: chat API (02) and `policy_retrieve` tool (04). End beneficiaries: employees (answers) and HR (cited plans).
### Design and Implementation Constraints
Answer-only-from-retrieved-context; citations (doc, page, effective date) mandatory; region/dept/date pre-filters applied before ranking; model/embedding strings config-driven.
### Assumptions and Dependencies
PDFs have extractable pages; doc store fires change webhooks; Qdrant collections versioned.

## 3. Functional Requirements
- **F-RAG-1 Ingest:** `Unstructured`/LlamaIndex → parent-child chunks, preserve `page_number`; embed dense + sparse; upsert with metadata.
- **F-RAG-2 Filter:** `region==user.region AND (department==user.dept OR department==all) AND effective_date<=today AND superseded_by IS NULL`.
- **F-RAG-3 Retrieve:** hybrid top ~30 (dense + BM25 fused RRF) → Cohere rerank → top 5 → expand to parent chunks.
- **F-RAG-4 Answer:** LLM answers strictly from context; output `{answer, citations[{doc,page,effective_date}], confidence}`; confidence < threshold → "I couldn't find this" + HR escalation, still logged.
- **F-RAG-5 Lifecycle:** re-ingest on doc change webhook; old versions marked `superseded_by=<new_id>` (never deleted).
- **F-RAG-6 Eval:** golden set 100+ Q&A across regions; RAGAS gate (e.g. Faithfulness < 0.9 fails deploy).
- Validation/errors: empty retrieval → abstain (not 500); embedding/rerank timeout → retry once → fallback "try again" + audit.

## 4. External Interface Requirements
### User Interfaces
None (headless). Admin triggers via `POST /api/v1/admin/reindex` (02).
### Hardware Interfaces
None; embedding/rerank are external APIs.
### Software and Database Interfaces
`qdrant-client` (collections `policies_v1`), object store for PDFs, OpenAI embeddings + Cohere Rerank APIs, Postgres `chat_logs` (written by 02).
### Communications and API Interfaces
Internal Python API: `retrieve(query, region, dept, k) -> chunks`; `answer(query, chunks) -> (text, citations, confidence)`; webhook `POST /rag/reindex {doc_id}`.

## 5. System Features and Capabilities
### Core Modules and Subsystems
`ingest.py`, `index.py`, `retrieve.py`, `answer.py`, `eval/` (golden set + RAGAS), `reindex_worker.py`.
### User Authentication and Authorization Roles
Service-to-service token; no end-user direct access; region/dept filters enforced regardless of caller.
### Reporting and Analytics Modules
Per-query log: latency, k values, rerank scores, confidence, feedback; Langfuse traces with cost.

## 6. Non-Functional Requirements (NFRs)
- Performance: retrieval p95 < 1.5 s; chat end-to-end p95 < 5 s; entitlement lookup cached by (role, region).
- Security: PII never embedded in vectors beyond policy text; PDFs access-scoped.
- Reliability: idempotent upserts (`doc_id:page:chunk` IDs); stale reads bounded by reindex lag SLA.
- Maintainability: tokenizer/chunker version pinned in metadata for reproducibility.
- Scalability: Qdrant horizontal read replicas; rerank batching.

## 7. Data and System Architecture
### High-Level Architecture Diagrams
`PDFs ─► ingest ─► Qdrant (dense+sparse+payload) ◄── retrieve(filter→hybrid→rerank→expand) ──► answer LLM ─► citations`.
### Entity-Relationship Diagrams (ERD) and Data Models
Qdrant point payload: `{document_name, region, department, page_number, effective_date, superseded_by, version, chunker_v, parent_id}`; Postgres `chat_logs` links employee→Q&A.
### Data Dictionary and Storage Requirements
Chunk ~1024 parent / 256 child tokens; dense `text-embedding-3-small` (config), sparse BM25; retain superseded vectors for audit, excluded from queries by filter.

## 8. Appendix and Change Log
### Document Revision History
| v | Date | Change |
|---|---|---|
| 0.1 | 2026-10-06 | Initial RAG spec from plan §9 |
### Open Issues and TBDs
- T-1: Confirm Cohere Rerank model version + embedding model pin.
- T-2: Golden-set ownership (HR-provided Q&A?) and region coverage.
- T-3: Parent-expansion token budget vs citation precision tradeoff.
