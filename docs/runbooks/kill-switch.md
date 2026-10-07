# Kill-switch runbook (07 hardening, task 7.5/7.6)

HR pilot lead and on-call SRE can halt executions. Halt is checked by the
executor BETWEEN actions; the in-flight tool call settles, remaining actions
go to `halted` and the case to `needs_attention`. No unapproved side effects.

## Halt a case
```
POST /api/v1/admin/kill-switch/{case_id}   (hr_admin)
→ {"case_id": "...", "halted": true}
```
- Writes `execute.halted` audit event.
- Verify: case status → `needs_attention`; pending actions → `halted`.

## Resume a case
```
DELETE /api/v1/admin/kill-switch/{case_id}  (hr_admin)
```
- Then re-approve the plan to re-enqueue `execute_job` (single-effect replay:
  succeeded actions are skipped via `{plan_id}:{idx}` idempotency keys).

## Game-day drill (required pre-pilot)
1. Trigger test hire → approve → `POST kill-switch` mid-execution.
2. Assert: ≤1 effect per action (check `external_ref`s), rest `halted`.
3. Resume → re-run → assert zero duplicate tool calls (replay guard).
4. Sign drill log: date, case_id, on-call name.

## Redis mirror
Halt flags are process-local (single-worker pilot) with a best-effort Redis
mirror. If multi-worker is introduced, promote the Redis key to authoritative
before wider rollout (post-pilot backlog).
