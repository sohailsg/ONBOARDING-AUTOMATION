# W1 (01-infra-data-impl, task 1.6). Run from this directory (onboarding/).
.PHONY: up down logs migrate seed roles check test test-infra test-hardening lint gen-api check-env check-ollama secrets-scan retention-dry pilot-report load-probe

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	alembic -c db/alembic.ini upgrade head

# Drift check: metadata (db/models.py) vs live DB. Must stay green.
check:
	alembic -c db/alembic.ini check

seed:
	python db/seeds/seed_demo.py

# Apply least-privilege roles (db/roles.sql) as the compose superuser.
# Usage: make roles APP_PW=<rand> MIG_PW=<rand>
roles:
	psql "postgresql://app:app@localhost:$${POSTGRES_PORT:-5432}/$${POSTGRES_DB:-onboarding}" -v APP_PW="$${APP_PW:?set APP_PW}" -v MIG_PW="$${MIG_PW:?set MIG_PW}" -f db/roles.sql

test:
	python -m pytest tests -q

test-infra:
	python -m pytest -m infra tests -q

# 07 hardening: unit gate (no DB needed) + secret scan + dry-runs.
test-hardening:
	python -m pytest tests/test_hardening.py -q

secrets-scan:
	python scripts/check_secrets.py

retention-dry:
	python -m backend.app.retention --help

pilot-report:
	python scripts/pilot_report.py --demo

load-probe:
	python scripts/load_probe.py --help

lint:
	ruff check . || true

gen-api:
	python backend/tools/gen_types.py --spec backend/openapi.yaml --out frontend/lib/api.types.ts || echo "gen-api: backend not yet implemented (W2)"

check-env:
	test -f .env || (echo "missing .env (copy from .env.example)" && exit 1)

check-ollama:
	curl -sf http://localhost:11434/api/tags >/dev/null && echo "ollama: OK" || echo "ollama: NOT RUNNING — install from https://ollama.com and: ollama pull llama3.1:8b && ollama pull nomic-embed-text"
