"""Seed policies (task 3.1 DoD: 3 sample policies queryable with page cites).

Generates both PDF (via reportlab) and .txt (with ``--- page N ---`` markers)
under ``rag-service/seeds/``. Ingest accepts either; PDFs exercise the
page-preservation path.
"""
from __future__ import annotations

import json
import os

SEED_DIR = os.path.join(os.path.dirname(__file__))

POLICIES: list[dict] = [
    {
        "doc_id": "UK-Employee-Handbook-2026",
        "region": "UK",
        "department": "all",
        "effective_date": "2026-04-01",
        "version": 1,
        "pages": [
            "UK Employee Handbook 2026. Welcome to the company. Your probation period "
            "is 6 months from your start date. During probation you meet your manager "
            "biweekly for feedback and goal reviews.",
            "Remote home-office budget in the UK is GBP 500 per employee. Claim it via "
            "the expenses tool within your first 90 days. The budget covers a chair, "
            "desk, monitor and keyboard.",
            "Annual leave in the UK is 28 days per year including bank holidays. "
            "Book leave in the HR portal with at least 2 weeks notice for blocks over "
            "5 days. Unused leave up to 5 days carries over to Q1.",
            "Sick pay in the UK follows Statutory Sick Pay (SSP) plus a company top-up "
            "at full pay for the first 10 working days per year. Notify your manager "
            "before 9am on the first day of absence.",
        ],
    },
    {
        "doc_id": "US-Benefits-Guide-2026",
        "region": "US",
        "department": "all",
        "effective_date": "2026-01-15",
        "version": 1,
        "pages": [
            "US Benefits Guide 2026. Health insurance covers 80 percent of premiums "
            "for employees, with dental and vision included. Enroll within 30 days of "
            "your start date.",
            "The 401k retirement plan matches 100 percent of contributions up to 5 "
            "percent of salary. Vesting is immediate. You may change contributions "
            "each pay period.",
            "Paid time off in the US is 20 days per year plus 10 federal holidays. "
            "New joiners accrue monthly. Unused PTO up to 10 days rolls over each January.",
            "Remote stipend in the US is USD 600 per year for home-office equipment. "
            "Submit receipts in the expenses tool. The stipend renews every January.",
        ],
    },
    {
        "doc_id": "DE-Leave-Policy-2026",
        "region": "DE",
        "department": "all",
        "effective_date": "2026-03-01",
        "version": 1,
        "pages": [
            "DE Leave Policy 2026. Annual leave in Germany is 30 days per calendar year "
            "for full-time employees. Submit requests in the HR portal at least 4 weeks "
            "ahead for summer months.",
            "Parental leave (Elternzeit) in Germany is up to 3 years per child with job "
            "protection. Elterngeld replaces 65 percent of net income for up to 14 "
            "months shared between parents.",
            "Sick leave in Germany is employer-paid at full salary for the first 6 "
            "weeks of illness. From week 7, health insurance pays Krankengeld. A doctor "
            "note is required from day 3.",
            "Home office allowance in Germany is EUR 400 per year. It covers internet, "
            "electricity and office supplies. Claim it with your tax documents each December.",
        ],
    },
    {
        "doc_id": "IN-Engineering-Onboarding-2026",
        "region": "IN",
        "department": "Engineering",
        "effective_date": "2026-02-01",
        "version": 1,
        "pages": [
            "IN Engineering Onboarding 2026. Every new engineer gets a buddy and a "
            "30-day plan with weekly check-ins. Complete security training in week 1.",
            "Engineering equipment in India is a MacBook plus a monitor budget of INR "
            "40000. Raise an IT ticket on day 1. Replacements follow a 3-year refresh cycle.",
            "Engineering leave in India is 24 days earned leave per year. Sick and casual "
            "leave add 12 days. On-call engineers get compensatory leave after weekend incidents.",
        ],
    },
]


def write_txt(policy: dict) -> str:
    path = os.path.join(SEED_DIR, policy["doc_id"] + ".txt")
    with open(path, "w", encoding="utf-8") as fh:
        for i, page in enumerate(policy["pages"], start=1):
            fh.write(f"--- page {i} ---\n{page}\n")
    return path


def write_pdf(policy: dict) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = os.path.join(SEED_DIR, policy["doc_id"] + ".pdf")
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    for i, page in enumerate(policy["pages"], start=1):
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, height - 72, f"{policy['doc_id']} — page {i}")
        c.setFont("Helvetica", 11)
        y = height - 110
        words, line = page.split(), ""
        for w in words:
            trial = (line + " " + w).strip()
            if len(trial) > 85:
                c.drawString(72, y, line)
                y -= 16
                line = w
            else:
                line = trial
        if line:
            c.drawString(72, y, line)
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(72, 48, f"Effective {policy['effective_date']} · v{policy['version']}")
        c.showPage()
    c.save()
    return path


def main() -> None:
    manifest = []
    for p in POLICIES:
        txt = write_txt(p)
        try:
            pdf = write_pdf(p)
        except Exception as e:  # noqa: BLE001
            pdf = ""
            print(f"pdf skipped for {p['doc_id']}: {e}")
        manifest.append(
            {
                "doc_id": p["doc_id"],
                "region": p["region"],
                "department": p["department"],
                "effective_date": p["effective_date"],
                "version": p["version"],
                "txt": os.path.basename(txt),
                "pdf": os.path.basename(pdf),
                "pages": len(p["pages"]),
            }
        )
        print(f"seeded {p['doc_id']}: {txt} {pdf}")
    with open(os.path.join(SEED_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"manifest: {len(manifest)} policies")


if __name__ == "__main__":
    main()
