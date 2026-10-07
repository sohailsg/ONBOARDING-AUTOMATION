# db — W1 infra + data (spec 01 / impl 01)

System of record: Postgres 16 (+ Redis queue, Chroma-local vectors, n8n —
see `../docker-compose.yml` and `../docs/STACK_DECISION_FREE.md` for why
Qdrant was replaced by embedded Chroma).

```
db/
  models.py        # SQLAlchemy 2 source of truth (8 tables)
  database.py      # DSN helpers (async runtime vs sync migrate/seed/test)
  alembic.ini      # run: alembic -c db/alembic.ini upgrade head
  migrations/      # env.py + versions/0001_initial.py
  roles.sql        # least-privilege roles (app_rw, migrate)
  seeds/seed_demo.py  # idempotent demo seed (dev/staging only)
```

## Quick start

```bash
cp .env.example .env
make up                # postgres + redis + n8n (all healthchecked)
make migrate && make seed
make test              # fixture tests; make test-infra for DB tests
```

## Schema changes

One migration per change (expand→migrate→contract); never direct DDL on
shared envs. After editing `models.py`:

```bash
alembic -c db/alembic.ini revision --autogenerate -m "describe change"
alembic -c db/alembic.ini upgrade head && make test-infra
```

Keep `alembic check` green (CI enforces it) and update spec §7 + RTM row.

## Roles

```bash
make roles APP_PW=$(openssl rand -hex 32) MIG_PW=$(openssl rand -hex 32)
```

`audit_events` is append-only (trigger + REVOKE); any migration that
recreates it must re-apply the REVOKEs (see `roles.sql` note).
