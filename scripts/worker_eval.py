"""4.6 HR citation-quality pass + nightly e2e benchmark (impl §5/§6).

Generates N plans (fixture mode by default; live Ollama when --live and
reachable), grades citation precision, and writes a markdown HR sign-off
report + JSONL cost/latency ledger.

Usage (from onboarding/):
  python scripts/worker_eval.py --n 20 --out eval-report.md --ledger eval-ledger.jsonl
  python scripts/worker_eval.py --n 3 --live --out nightly.md --ledger nightly.jsonl  # nightly e2e
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--target", type=float, default=0.9)
    ap.add_argument("--live", action="store_true",
                    help="use live Ollama path instead of deterministic fixtures")
    ap.add_argument("--out", default="")
    ap.add_argument("--ledger", default="")
    args = ap.parse_args(argv)

    if args.live:
        os.environ["WORKER_FIXTURE_MODE"] = ""
    else:
        os.environ["WORKER_FIXTURE_MODE"] = "1"
    os.environ.setdefault("RAG_BASE_URL", "http://127.0.0.1:9")
    os.environ.setdefault("REDIS_URL", "")

    from worker.config import reset_worker_settings
    from worker.eval import GRADE_TARGET, generate_hires, render_report, run_eval

    reset_worker_settings()
    hires = generate_hires(args.n)
    # --live is strict: crew/LLM errors fail the run instead of silently
    # degrading to deterministic output (which would make the gate vacuous).
    rows = asyncio.run(run_eval(hires, use_fixtures=not args.live,
                                strict=args.live))
    report = render_report(rows, target=args.target or GRADE_TARGET,
                           strict=args.live)
    if args.out:
        with open(args.out, "w") as f:
            f.write(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    if args.ledger:
        with open(args.ledger, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"wrote {args.ledger} ({len(rows)} rows)")
    gate = all(r["within_budget"] and not r["error"] for r in rows) and (
        sum(r["citation_precision"] for r in rows) / max(1, len(rows)) >= (args.target or GRADE_TARGET)
    )
    if args.live:
        gate = gate and all(r.get("llm_used", False) for r in rows)
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
