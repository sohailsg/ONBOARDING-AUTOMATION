# Pilot promotion checklist (07 hardening, task 7.7 / impl §6)

Manual promotion to pilot. ALL boxes required; freeze non-critical merges during pilot.

- [ ] `security.yml` green (secret scan + pip-audit + ZAP baseline)
- [ ] Eval gate green (Faithfulness ≥0.9 on golden set)
- [ ] Backup verified (Postgres base + WAL; Qdrant/Chroma snapshot; restore rehearsed, RTO <1h / RPO <15min)
- [ ] Runbooks linked (`oncall`, `reindex`, `kill-switch`, `secrets-rotation`) + game day signed
- [ ] `GET /api/v1/admin/readiness` → `{"ready": true}` (no prod blockers, DLQ 0)
- [ ] Retention jobs ran in dry-run week 11; live only after legal sign-off
- [ ] Approver roster + hire cohort (1 region/dept, ~10 hires) confirmed with HR pilot lead
- [ ] Pilot freeze communicated: only P0 fixes + approved runbook actions

## Rollback decision tree
1. 5xx spike or execute-failure burst → halt affected cases (kill-switch), then image rollback.
2. Data corruption → Postgres PITR (RTO <1h); vectors → snapshot restore; Redis → rebuild from DB.
3. RAG quality collapse → restore pre-reindex snapshot; keep abstain behavior (never lower threshold ad hoc).
4. Migration issue → forward-fix migration (never manual DDL on pilot DB).
