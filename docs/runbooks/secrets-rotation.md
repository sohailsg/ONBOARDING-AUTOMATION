# Secrets rotation runbook (07 hardening, task 7.1)

Secrets live in Vault (or cloud secret manager) with agent injection; local
dev uses `.env` (NEVER committed — `.gitignore` covers `.env`; CI runs
`python scripts/check_secrets.py`). `*_GENERATED` placeholders in committed
`.env.example` files must stay EMPTY.

## Vault paths (provision before pilot)
- `secret/onboarding/jwt-secret` → `JWT_SECRET` (HS256; SSO/JWKS later, no route changes via `AuthProvider`)
- `secret/onboarding/service-api-key` → `SERVICE_API_KEY` (n8n → trigger)
- `secret/onboarding/webhook-hmac` → `WEBHOOK_HMAC_SECRET` (HRIS → n8n)
- `secret/onboarding/db/app-rw` → `app_rw` password (least-privilege role)
- `secret/onboarding/db/migrate` → `migrate` password (DDL only)
- MCP tool creds: least-privilege per tool (email/calendar/ticket/HRIS), sandbox scopes in pilot

## Rotation (rehearsed pre-pilot, drill logged)
1. Generate: `openssl rand -hex 32` per secret.
2. Write new value to Vault path; keep old value valid during overlap.
3. Rolling restart: API → worker → n8n (agent injection picks up new value).
4. Verify: `GET /health`, trigger test hire (service key), login (JWT), `GET /api/v1/admin/readiness` shows no blockers.
5. Revoke old value in Vault; confirm old token/key now 401s.
6. DB passwords: `ALTER ROLE app_rw WITH PASSWORD '...'` as superuser, then restart API/worker.

## Least-privilege MCP creds
- Sandbox mode (`MCP_MODE=sandbox`) for staging/game-day; pilot uses real tools behind the approval gate.
- Each tool wrapper gets only its own credential; service role cannot approve; employee cannot read others' cases (RBAC matrix test).

## CI gates
- `security.yml`: secret scan (blocking) + `pip-audit` + ZAP baseline (required green pre-pilot).
- Prod guard: `Settings.validate_production()` blocks staging/pilot/prod boot on dev defaults (`JWT_DEV_STUB=true`, `dev-service-key`, `dev-only-change-me`).
