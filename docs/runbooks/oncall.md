# On-call runbook (07 hardening, task 7.6)

Owner: SRE + tech lead. Pilot scope: 1 region/dept, ~10 hires. Freeze: only P0 fixes.

## Paging (page = PagerDuty; rest = Slack digest)

| Alert | Meaning | First action |
|---|---|---|
| `DLQNonEmpty` (DLQ >0 for 15m) | poison job stuck | `GET /api/v1/admin/dlq`, inspect error, fix cause, `POST /api/v1/admin/dlq/drain`. SLO: drained <4h |
| `FaithfulnessDrop` (avg confidence <0.9, 15m) | RAG/rerank degraded | Check Langfuse Faithfulness trend, Qdrant/Chroma latency, rerank errors; if RAG down, chat abstains by design — do NOT force answers |
| `ServerErrorsSpike` (5xx >2% 5m) | gateway failing | `GET /metrics`, Sentry, `docker compose logs`; rollback image if deploy-correlated |
| `ExecuteFailureBurst` | post-approval tools failing | `docs/runbooks/kill-switch.md`; inspect `action.failed` audit rows; halt case if side effects uncertain |
| `NeedsAttentionAgeing` (>24h) | HR SLA breach | Pair with HR pilot lead; pause intake via Workflow A toggle if overloaded |

<a id="dlq"></a>
## DLQ drill
1. `GET /api/v1/admin/dlq` → note depth + first error.
2. Fix root cause (tool creds, MCP down, bad payload).
3. `POST /api/v1/admin/dlq/drain` → depth must return to 0.
4. Verify `execution.completed` audit events for drained plans.
5. Log drill in game-day sheet (date, duration, drain time).

<a id="faithfulness"></a>
## Faithfulness drop
1. Grafana: `onboarding_chat_avg_confidence`; Langfuse: per-case cost/latency + Faithfulness trend.
2. Check RAG `/metrics`, Chroma dir health, `ANSWER_CONFIDENCE_THRESHOLD` unchanged.
3. Rerank/Qdrant outage → graceful abstain is CORRECT (no hallucination). Escalate to HR, do not lower threshold without eval gate green.

<a id="5xx"></a>
## 5xx spike
1. `GET /metrics` + Sentry issues; correlate with deploy (`readiness.production_blockers`).
2. Rollback: redeploy previous image tag; migrations are forward-fix only.
3. Postgres PITR if data corruption: RTO <1h, RPO <15min (rehearsed pre-pilot).

<a id="needs-attention"></a>
## needs_attention >24h
1. List: `GET /api/v1/cases?status=needs_attention` (hr_admin).
2. For each: completeness check `GET /api/v1/admin/audit/completeness/{case_id}`.
3. Pair with HR pilot lead; resolve or escalate; never auto-approve.

## Useful endpoints
- `GET /health`, `GET /metrics`, `GET /api/v1/admin/readiness` (promotion gate)
- `GET /api/v1/admin/audit/export?case_id=...` (auditor CSV, redacted)
- `GET /api/v1/admin/retention/dry-run` (legal sign-off preview)
