-- W1 (01-infra-data-impl, tasks 1.3 + 1.4). Least-privilege DB roles.
--
-- Apply as a superuser (compose `app` user) AFTER `alembic upgrade head`:
--   make roles
--   # or: psql "$DATABASE_URL_SYNC" -f db/roles.sql
--
-- * app_rw  — API + worker runtime. No DDL, no access to alembic_version,
--             no UPDATE/DELETE on audit_events (append-only).
-- * migrate — DDL owner used for `alembic upgrade/downgrade` on shared envs.
--             Local dev may keep using the compose superuser; staging/pilot
--             must use this role via `make migrate` with DATABASE_URL of the
--             migrate user.
--
-- Passwords come from the environment at apply time (psql :APP_PW / :MIG_PW).
-- Generate:  openssl rand -hex 32

-- NOTE: psql :'VAR' substitution does not work inside DO $$…$$ bodies,
-- so role creation (no password) happens in DO and passwords are set by
-- top-level ALTERs below.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrate') THEN
    CREATE ROLE migrate LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
    CREATE ROLE app_rw LOGIN;
  END IF;
END $$;

ALTER ROLE migrate LOGIN PASSWORD :'MIG_PW';
ALTER ROLE app_rw LOGIN PASSWORD :'APP_PW';

GRANT CONNECT ON DATABASE onboarding TO app_rw, migrate;
GRANT USAGE ON SCHEMA public TO app_rw, migrate;

-- Runtime grants: DML on domain tables only.
GRANT SELECT, INSERT, UPDATE, DELETE ON
  employees, onboarding_cases, plans, approvals, actions,
  checklist_items, chat_logs
  TO app_rw;
-- Append-only: app can insert + read audit trail, never mutate it.
GRANT SELECT, INSERT ON audit_events TO app_rw;
REVOKE UPDATE, DELETE ON audit_events FROM app_rw;
REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC;
REVOKE ALL ON alembic_version FROM app_rw;

-- Migration role owns future DDL.
GRANT ALL ON ALL TABLES IN SCHEMA public TO migrate;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO migrate;
ALTER DEFAULT PRIVILEGES FOR ROLE migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
-- NOTE: any future migration that recreates audit_events must re-apply
-- the REVOKEs above (append-only invariant, task 1.4).
