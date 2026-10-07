# CrewAI worker (W4, spec 04 + impl 04)

Background plan crew: drafts (never executes) versioned, cited onboarding plans.
Ollama chat model only (`OLLAMA_CHAT_MODEL`, default `llama3.1:8b`). No Anthropic key.

## Layout

| File | Task |
|---|---|
| `schemas.py` | 4.1 Pydantic v2 outputs (`EntitlementSet`, `OnboardingPlan`, `SystemActionPlan`, `FullPlanPayload`) |
| `tools.py` | 4.2 read-only wrappers (`policy_retrieve`, `find_slots`) + entitlement cache + run budgets |
| `guards.py` | 4.2 prompt-injection + PII guards |
| `agents/{policy,experience,ops}.py` | 4.3 three agents (ops has **no tools** by design) |
| `crew.py` | 4.3 sequential crew (`output_pydantic` per task) + 1 self-repair retry |
| `jobs.py` | 4.4 Arq `plan_job(case_id, session_id)` — status machine, versioned insert, traces, audit |
| `config.py` | 4.5 env-driven caps (`MAX_STEPS_PER_RUN=12`, `MAX_TOKENS_PER_RUN=30000`), cache TTL |
| `tracing.py` | 4.5 trace fan-out + per-case cost/latency log |
| `prompts.py` | versioned system/task prompts (`PROMPT_VERSION=v1`) |
| `llm.py` | CrewAI LLM factory (API-drift isolation wrapper) |

## Run

```bash
# Arq worker (from onboarding/):
arq worker.jobs.WorkerSettings --max-jobs $WORKER_CONCURRENCY
```

Env: see `.env.example`. `WORKER_FIXTURE_MODE=1` forces the deterministic
(no-LLM) path — used by unit tests and as live fallback when Ollama is down.

## Test

```bash
python -m pytest worker/tests -q        # from onboarding/
python -m pytest onboarding/worker/tests -q  # from repo root
```

DoD: sample hire -> schema-valid cited plan <2 min; traces stream to
`trace:{session_id}`; no write-tool import in worker (CI grep test).
