# Reindex runbook (07 hardening, task 7.6)

Rate limit: 2/hour, hr_admin only. Qdrant/Chroma snapshot BEFORE reindex.

## Standard reindex
1. Snapshot vectors: back up `CHROMA_DIR` (or Qdrant snapshot pre-reindex).
2. `POST /api/v1/admin/reindex` → expect 202 `{"status":"queued"}`.
3. Watch SSE / worker logs for `ingest_job` completion.
4. Spot-check: ask 3 known policy questions in chat, confirm citations + confidence ≥0.55.
5. If Faithfulness drops: restore snapshot, report in pilot weekly report.

## Rollback
- Vectors: restore `CHROMA_DIR` backup (or Qdrant snapshot restore).
- Postgres: PITR only if migration ran with reindex (forward-fix preferred).
- Redis: rebuild from DB (best-effort RDB, never authoritative).

## Post-reindex checks
- `GET /metrics` — ingest latency sane, DLQ depth 0.
- Eval gate still green (Faithfulness ≥0.9 on golden set).
