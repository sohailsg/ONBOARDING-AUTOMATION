"""API p95 smoke on seed data (02-impl DoD: p95 < 300 ms, excl. agent/chat/SSE).

Spins the gateway on loopback with a temp sqlite DB, seeds N hires through
the public API, and reports p50/p95 per route. Exits nonzero on SLO breach.

    python onboarding/backend/tools/perf_smoke.py [--n 30] [--p95-ms 300]
"""

from __future__ import annotations

import argparse
import os
import socket
import statistics
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import httpx
import uvicorn

os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("SERVICE_API_KEY", "perf-service-key")
os.environ.setdefault("JWT_DEV_STUB", "true")

from onboarding.backend.app.auth import mint_dev_token  # noqa: E402
from onboarding.backend.app.db import get_session  # noqa: E402
from onboarding.backend.app.main import create_app  # noqa: E402
from onboarding.backend.app.models import Base  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--p95-ms", type=float, default=300.0)
    args = ap.parse_args()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    fd, dbpath = tempfile.mkstemp(prefix="perf-", suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{dbpath}", connect_args={"check_same_thread": False})

    async def _init() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(_init())
    TestSession = async_sessionmaker(engine, expire_on_commit=False)
    app = create_app()

    async def _override():
        async with TestSession() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    lat: dict[str, list[float]] = {}
    try:
        base = f"http://127.0.0.1:{port}"
        svc_key = os.environ["SERVICE_API_KEY"]
        hr = {"Authorization": f"Bearer {mint_dev_token('hr_admin', 'hr-perf')}"}
        with httpx.Client(base_url=base, timeout=15) as c:
            for _ in range(200):
                try:
                    if c.get("/health").status_code == 200:
                        break
                except Exception:
                    time.sleep(0.05)

            def timed(bucket: str, fn) -> None:
                t0 = time.perf_counter()
                fn()
                lat.setdefault(bucket, []).append((time.perf_counter() - t0) * 1000)

            case_ids: list[str] = []
            for i in range(args.n):
                key = f"perf-{i}-{uuid.uuid4().hex[:6]}"
                body = {"name": f"Hire {i}", "role": "E", "dept": "D", "region": "UK", "start_date": "2026-11-01"}

                def _trig() -> None:
                    r = c.post("/api/v1/onboarding/trigger", json=body,
                               headers={"X-Service-Key": svc_key, "Idempotency-Key": key})
                    assert r.status_code == 201, r.text
                    case_ids.append(r.json()["id"])

                timed("POST trigger", _trig)
            for _ in range(10):
                timed("GET cases", lambda: c.get("/api/v1/cases?page_size=50", headers=hr))
            for cid in case_ids[:10]:
                timed("PUT plan", lambda cid=cid: c.put(f"/api/v1/cases/{cid}/plan",
                      json={"json_payload": {"a": 1}}, headers=hr))

        failed = False
        for route, samples in lat.items():
            p50 = statistics.median(samples)
            p95 = _p95(samples)
            ok = p95 < args.p95_ms
            failed |= not ok
            print(f"{route:14s} n={len(samples):3d} p50={p50:7.1f}ms p95={p95:7.1f}ms {'OK' if ok else 'BREACH'}")
        return 1 if failed else 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        asyncio.run(engine.dispose())
        try:
            os.unlink(dbpath)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
