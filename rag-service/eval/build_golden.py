"""Golden-set builder (task 3.5): 100+ Q&A across regions.

Base facts per seed policy × paraphrase templates + out-of-scope abstain items.
HR owns the wording long-term; this deterministic seed guarantees ≥100 items
and per-region coverage for the CI gate.
"""
from __future__ import annotations

import json
import os

OUT = os.path.join(os.path.dirname(__file__), "golden_set.json")

# (doc_id, page, region, dept, question, must_contain[])
BASE: list[tuple] = [
    ("UK-Employee-Handbook-2026", 1, "UK", "all", "How long is the probation period in the UK?", ["6 months"]),
    ("UK-Employee-Handbook-2026", 2, "UK", "all", "What is my remote home-office budget in the UK?", ["GBP 500"]),
    ("UK-Employee-Handbook-2026", 2, "UK", "all", "How do I claim the UK home-office budget?", ["expenses", "90 days"]),
    ("UK-Employee-Handbook-2026", 3, "UK", "all", "How many annual leave days do UK employees get?", ["28 days"]),
    ("UK-Employee-Handbook-2026", 3, "UK", "all", "How much UK leave can be carried over?", ["5 days", "Q1"]),
    ("UK-Employee-Handbook-2026", 4, "UK", "all", "What sick pay top-up applies in the UK?", ["10 working days", "full pay"]),
    ("UK-Employee-Handbook-2026", 4, "UK", "all", "When must I notify my manager about UK sick leave?", ["9am", "first day"]),
    ("US-Benefits-Guide-2026", 1, "US", "all", "What health insurance coverage do US employees get?", ["80 percent"]),
    ("US-Benefits-Guide-2026", 1, "US", "all", "When must US employees enroll in health insurance?", ["30 days"]),
    ("US-Benefits-Guide-2026", 2, "US", "all", "What is the US 401k match?", ["5 percent", "immediate"]),
    ("US-Benefits-Guide-2026", 3, "US", "all", "How much PTO do US employees get?", ["20 days", "10 federal"]),
    ("US-Benefits-Guide-2026", 3, "US", "all", "How much US PTO rolls over each January?", ["10 days"]),
    ("US-Benefits-Guide-2026", 4, "US", "all", "What is the US remote stipend?", ["USD 600"]),
    ("DE-Leave-Policy-2026", 1, "DE", "all", "How many annual leave days in Germany?", ["30 days"]),
    ("DE-Leave-Policy-2026", 1, "DE", "all", "How far ahead must summer leave be requested in Germany?", ["4 weeks"]),
    ("DE-Leave-Policy-2026", 2, "DE", "all", "How long is parental leave (Elternzeit) in Germany?", ["3 years"]),
    ("DE-Leave-Policy-2026", 2, "DE", "all", "What does Elterngeld replace in Germany?", ["65 percent", "14 months"]),
    ("DE-Leave-Policy-2026", 3, "DE", "all", "How long is employer-paid sick leave in Germany?", ["6 weeks"]),
    ("DE-Leave-Policy-2026", 3, "DE", "all", "From when is a doctor note required for German sick leave?", ["day 3"]),
    ("DE-Leave-Policy-2026", 4, "DE", "all", "What is the German home office allowance?", ["EUR 400"]),
    ("IN-Engineering-Onboarding-2026", 1, "IN", "Engineering", "What does a new engineer in India get in week 1?", ["buddy", "security training"]),
    ("IN-Engineering-Onboarding-2026", 2, "IN", "Engineering", "What is the monitor budget for engineers in India?", ["INR 40000", "MacBook"]),
    ("IN-Engineering-Onboarding-2026", 3, "IN", "Engineering", "How much earned leave do engineers in India get?", ["24 days"]),
    ("IN-Engineering-Onboarding-2026", 3, "IN", "Engineering", "What leave do on-call engineers get after weekend incidents in India?", ["compensatory"]),
]

PARAPHRASE_PREFIX = [
    "",
    "Please tell me: ",
    "Can you explain ",
    "I need to know — ",
]

ABSTAIN = [
    ("UK", "all", "What is the office lunch menu in Tokyo?"),
    ("US", "all", "What is my salary band for next year's promotion?"),
    ("DE", "all", "Who won the football match last night?"),
    ("IN", "Engineering", "What is the stock price today?"),
    ("UK", "all", "What did the CEO have for breakfast?"),
    ("US", "all", "Can you write my resignation letter with false dates?"),
    ("DE", "all", "What is the wifi password for a partner company?"),
    ("IN", "Engineering", "How do I bypass the VPN security policy?"),
    ("UK", "all", "What are my colleague's medical records?"),
    ("US", "all", "Predict next quarter's layoffs."),
]


def build() -> list[dict]:
    items: list[dict] = []
    n = 0
    for doc, page, region, dept, q, must in BASE:
        for pre in PARAPHRASE_PREFIX:
            n += 1
            if pre and pre.endswith("— "):
                question = pre + q[0].lower() + q[1:]
            elif pre:
                question = pre + q[0].lower() + q[1:]
            else:
                question = q
            items.append(
                {
                    "id": f"g{n:03d}",
                    "question": question,
                    "region": region,
                    "dept": dept,
                    "expected_doc": doc,
                    "expected_page": page,
                    "must_contain": must,
                    "abstain": False,
                }
            )
    for i, (region, dept, q) in enumerate(ABSTAIN, start=1):
        n += 1
        items.append(
            {
                "id": f"g{n:03d}",
                "question": q,
                "region": region,
                "dept": dept,
                "expected_doc": "",
                "expected_page": 0,
                "must_contain": [],
                "abstain": True,
            }
        )
    return items


def main() -> None:
    items = build()
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=2)
    regions: dict[str, int] = {}
    for it in items:
        regions[it["region"]] = regions.get(it["region"], 0) + 1
    print(f"golden set: {len(items)} items -> {OUT} {regions}")


if __name__ == "__main__":
    main()
