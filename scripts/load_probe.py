"""7.5 load probe: 20 concurrent trigger cases (2x pilot) against a running API.

Usage:
  python scripts/load_probe.py --base http://localhost:8000 --n 20 --service-key $SERVICE_API_KEY
Exit non-zero if SLOs breach: trigger p95 <3000ms (local stack allowance;
gateway SLO p95 <300ms applies to cached reads in CI) or any 5xx.
"""
from __future__ import annotations

import argparse
import statistics
import time
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor


def one(base: str, key: str, i: int) -> tuple[int, float]:
    body = json.dumps({"name": f"Load {i}", "role": "Eng", "dept": "Eng",
                       "region": "UK", "start_date": "2026-11-01"}).encode()
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/onboarding/trigger", data=body,
        headers={"Content-Type": "application/json", "X-Service-Key": key,
                 "Idempotency-Key": f"load-{i}-{int(time.time())}"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, (time.perf_counter() - t0) * 1000
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", 599)
        return int(code) if isinstance(code, int) else 599, (time.perf_counter() - t0) * 1000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--service-key", default="")
    ap.add_argument("--p95-budget-ms", type=float, default=3000.0)
    args = ap.parse_args()
    if not args.service_key:
        print("missing --service-key (SERVICE_API_KEY)")
        return 2
    with ThreadPoolExecutor(max_workers=args.n) as ex:
        results = list(ex.map(lambda i: one(args.base, args.service_key, i), range(args.n)))
    codes = [c for c, _ in results]
    lat = sorted(d for _, d in results)
    p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else 0.0
    print(f"n={args.n} ok={codes.count(201)} dup={codes.count(200)} "
          f"errors={sum(1 for c in codes if c >= 500)} p50={statistics.median(lat):.0f}ms p95={p95:.0f}ms")
    if any(c >= 500 for c in codes):
        print("LOAD FAIL: 5xx observed")
        return 1
    if p95 > args.p95_budget_ms:
        print(f"LOAD FAIL: p95 {p95:.0f}ms > budget {args.p95_budget_ms:.0f}ms")
        return 1
    print("LOAD OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
