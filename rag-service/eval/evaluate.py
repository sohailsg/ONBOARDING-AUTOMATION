"""Eval + CI gate (task 3.5): RAGAS-style Faithfulness over the golden set.

Metrics (local, no paid API):
- recall@5: expected_doc present in top-5 retrieved chunks.
- faithfulness: fraction of answer sentences grounded in retrieved context
  (token-overlap entailment proxy) + mandatory citations check.
- abstain_correct: out-of-scope items must abstain.

Gate: mean faithfulness (non-abstain items) < 0.9 -> exit 1 (blocks deploy).
Also fails on recall@5 < 0.8 or abstain accuracy < 0.8 to catch filter bugs.

Usage (from repo root ``onboarding/``):
  python rag-service/eval/evaluate.py [--limit N] [--llm extractive|auto]
  CHROMA_DIR / CHROMA_COLLECTION envs respected.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

GATE_FAITHFULNESS = 0.9
GATE_RECALL = 0.8
GATE_ABSTAIN = 0.8


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _toks(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def faithfulness(answer: str, contexts: list[str]) -> float:
    sents = _sentences(answer)
    if not sents:
        return 0.0
    ctx = _toks(" ".join(contexts))
    ok = sum(1 for s in sents if _toks(s) and len(_toks(s) & ctx) / max(1, len(_toks(s))) >= 0.4)
    return ok / max(1, len(sents))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--llm", default="extractive", help="extractive|auto")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    golden_path = args.golden or os.path.join(HERE, "golden_set.json")
    with open(golden_path, encoding="utf-8") as fh:
        items = json.load(fh)
    if args.limit and args.limit < len(items):
        step = max(1, len(items) // args.limit)
        items = items[::step][: args.limit]

    import answer as answer_mod
    import retrieve as retrieve_mod

    faith: list[float] = []
    recalls: list[float] = []
    abstains: list[float] = []
    lat: list[float] = []
    failures: list[dict] = []

    for it in items:
        t0 = time.perf_counter()
        try:
            chunks = retrieve_mod.retrieve(
                it["question"], it["region"], it.get("dept", "all")
            )
        except Exception:
            chunks = []
        lat.append((time.perf_counter() - t0) * 1000)
        ctx = [c.get("text", "") for c in chunks]
        try:
            res = answer_mod.answer(it["question"], chunks, llm=args.llm)
        except Exception:
            from config import SETTINGS

            res = {
                "answer": SETTINGS.abstain_text,
                "citations": [],
                "confidence": 0.0,
                "abstained": True,
            }
        if it.get("abstain"):
            ok = 1.0 if res["abstained"] else 0.0
            abstains.append(ok)
            if not ok:
                failures.append({"id": it["id"], "kind": "abstain", "q": it["question"]})
            continue
        docs = [c.get("doc", "") for c in chunks[:5]]
        hit = 1.0 if it["expected_doc"] in docs else 0.0
        recalls.append(hit)
        f = faithfulness(res["answer"], ctx)
        # uncited factual claims fail faithfulness outright
        if not res["abstained"] and not res.get("citations"):
            f = 0.0
        # keyword recall check on must_contain
        blob = (res["answer"] + " " + " ".join(ctx)).lower()
        if it.get("must_contain") and not all(k.lower() in blob for k in it["must_contain"]):
            f = min(f, 0.5)
        if res["abstained"]:
            f = 0.0  # wrong abstain on answerable question
        faith.append(f)
        if hit < 1.0 or f < GATE_FAITHFULNESS:
            failures.append(
                {"id": it["id"], "kind": "recall/faith", "hit": hit, "faith": round(f, 3),
                 "q": it["question"]}
            )

    m_faith = statistics.mean(faith) if faith else 0.0
    m_rec = statistics.mean(recalls) if recalls else 0.0
    m_abs = statistics.mean(abstains) if abstains else 1.0
    lat_sorted = sorted(lat)
    p95 = lat_sorted[max(0, int(0.95 * len(lat_sorted)) - 1)] if lat_sorted else 0.0

    report = {
        "n": len(items),
        "n_answerable": len(faith),
        "n_abstain": len(abstains),
        "faithfulness_mean": round(m_faith, 4),
        "recall_at_5": round(m_rec, 4),
        "abstain_accuracy": round(m_abs, 4),
        "retrieval_p95_ms": round(p95, 1),
        "gate": {"faithfulness": GATE_FAITHFULNESS, "recall": GATE_RECALL, "abstain": GATE_ABSTAIN},
        "failures": failures[:25],
    }
    print(json.dumps(report, indent=2))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    ok = m_faith >= GATE_FAITHFULNESS and m_rec >= GATE_RECALL and m_abs >= GATE_ABSTAIN
    print(
        f"GATE {'PASS' if ok else 'FAIL'} "
        f"(faith={m_faith:.3f}>={GATE_FAITHFULNESS} "
        f"recall={m_rec:.3f}>={GATE_RECALL} abstain={m_abs:.3f}>={GATE_ABSTAIN})"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
