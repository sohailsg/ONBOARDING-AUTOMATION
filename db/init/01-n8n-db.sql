-- W1 (01-infra-data-impl). Separate n8n database.
-- Runs once at first `db` init (fresh volume). Keeps n8n's own tables out
-- of the app database so `alembic check` stays a strict drift gate.
-- For existing volumes, create manually:  CREATE DATABASE n8n;
SELECT 'CREATE DATABASE n8n' WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'n8n'
)\gexec
