"""7.4 in-process metrics (spec F-HD-4).

Free-stack counters exposed at GET /metrics (Prometheus text) and bundled
into GET /api/v1/admin/readiness. OTel/Sentry/Langfuse remain optional
sidecars configured via env; this module is the always-on baseline so
dashboards + alerts have stable series even with sidecars off.

Series:
  onboarding_requests_total{route,status}
  onboarding_request_latency_ms (last/avg per route)
  onboarding_jobs_total{job,status}
  onboarding_chat_total{outcome}  (cited | abstained)
  onboarding_chat_confidence_sum / count -> avg confidence proxy for Faithfulness trend
  onboarding_actions_total{status}
  onboarding_dlq_depth (gauge via jobs.dlq_depth)
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_requests: dict[tuple[str, str], int] = defaultdict(int)
_latency_ms: dict[str, list[float]] = defaultdict(list)
_jobs: dict[tuple[str, str], int] = defaultdict(int)
_chat: dict[str, int] = defaultdict(int)
_chat_conf_sum = 0.0
_chat_conf_n = 0
_actions: dict[str, int] = defaultdict(int)
_started = time.time()


def observe_request(route: str, status: str, duration_ms: float) -> None:
    with _lock:
        _requests[(route, status)] += 1
        buf = _latency_ms[route]
        buf.append(duration_ms)
        if len(buf) > 200:
            del buf[: len(buf) - 200]


def observe_job(job: str, status: str) -> None:
    with _lock:
        _jobs[(job, status)] += 1


def observe_chat(outcome: str, confidence: float) -> None:
    global _chat_conf_sum, _chat_conf_n
    with _lock:
        _chat[outcome] += 1
        _chat_conf_sum += float(confidence or 0.0)
        _chat_conf_n += 1


def observe_action(status: str) -> None:
    with _lock:
        _actions[status] += 1


def reset() -> None:  # tests only
    global _chat_conf_sum, _chat_conf_n
    with _lock:
        _requests.clear()
        _latency_ms.clear()
        _jobs.clear()
        _chat.clear()
        _actions.clear()
        _chat_conf_sum = 0.0
        _chat_conf_n = 0


def snapshot() -> dict:
    with _lock:
        avg_lat = {r: (sum(v) / len(v) if v else 0.0) for r, v in _latency_ms.items()}
        return {
            "uptime_s": round(time.time() - _started, 1),
            "requests": {f"{r}:{s}": n for (r, s), n in _requests.items()},
            "avg_latency_ms": {r: round(v, 1) for r, v in avg_lat.items()},
            "jobs": {f"{j}:{s}": n for (j, s), n in _jobs.items()},
            "chat": dict(_chat),
            "chat_avg_confidence": round(_chat_conf_sum / _chat_conf_n, 3) if _chat_conf_n else 0.0,
            "actions": dict(_actions),
        }


def render_prometheus(dlq_depth: int = 0) -> str:
    snap = snapshot()
    lines = ["# HELP onboarding_requests_total Gateway requests by route/status."]
    lines.append("# TYPE onboarding_requests_total counter")
    for k, v in snap["requests"].items():
        route, status = k.rsplit(":", 1)
        lines.append(f'onboarding_requests_total{{route="{route}",status="{status}"}} {v}')
    lines.append("# HELP onboarding_chat_avg_confidence Mean chat confidence (Faithfulness proxy).")
    lines.append("# TYPE onboarding_chat_avg_confidence gauge")
    lines.append(f"onboarding_chat_avg_confidence {snap['chat_avg_confidence']}")
    lines.append("# HELP onboarding_dlq_depth Dead-letter queue depth (page if >0 for 15m).")
    lines.append("# TYPE onboarding_dlq_depth gauge")
    lines.append(f"onboarding_dlq_depth {dlq_depth}")
    return "\n".join(lines) + "\n"
