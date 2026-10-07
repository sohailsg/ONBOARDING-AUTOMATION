# Game day checklist (07 hardening, task 7.6)

Run in staging (backups ON, sandbox tools) week 11. On-call must resolve each
simulated page unaided. All drills logged below and signed.

| # | Drill | Steps | Pass criteria | Date / sign |
|---|---|---|---|---|
| G-1 | Duplicate trigger + duplicate execute | POST trigger twice with same `Idempotency-Key`; approve; enqueue `execute_job` twice | Single case (2nd POST → 200 same id); replay performs zero duplicate tool calls | |
| G-2 | Kill mid-run | Approve → `POST kill-switch/{case}` mid-execution → resume → re-run | Remaining → `halted`, case → `needs_attention`; resume replays with no dup effects | |
| G-3 | RAG outage → abstain | Stop RAG service; ask chat question | Cited answer withheld; abstain text + `confidence: 0`; `chat.abstained` metric +1; NO hallucination | |
| G-4 | DLQ drain | Push poison job (bad tool type); verify page at 15m (or immediate in drill) | `GET /admin/dlq` depth 1 → fix → `POST /admin/dlq/drain` → depth 0 in <4h | |
| G-5 | Audit immutability | `UPDATE/DELETE audit_events` as app role | Both rejected (`append-only`); auditor CSV export complete for a test hire | |
| G-6 | PII grep | `grep -rE` allowlist-denied patterns over logs; retention dry-run | Log PII grep = 0; `GET /admin/retention/dry-run` clean, live run only after legal sign | |
| G-7 | Secrets rotation rehearsal | Follow `secrets-rotation.md` overlap procedure | Old creds 401, new creds work, `readiness` green | |
| G-8 | Load 20 concurrent cases | `python scripts/load_probe.py --n 20` | No 5xx; p95 within budget; API p95 <300ms on cached reads | |
| G-9 | Rollback | Deploy previous image; forward-fix migration drill | RTO <1h confirmed on staging timer | |

Exit: all rows signed + `security.yml` green + dashboards linked + eval gate green → pilot promotion vote.
