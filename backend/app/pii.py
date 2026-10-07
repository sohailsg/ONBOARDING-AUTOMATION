"""7.2 PII allowlist + scrub (spec F-HD-2).

Only allowlisted hire fields may enter prompts/logs/vectors. Everything else
(national ID, salary, bank details, SSN/card shapes, emails, phones) is
redacted before the LLM call, before audit insert, and before log lines.

Strictest default ships first; legal adjusts N (retention months) later.
"""
from __future__ import annotations

import re

# Fields the model / retriever / logs are allowed to see.
PROMPT_ALLOWLIST = frozenset({
    "name", "role", "dept", "region", "timezone", "start_date",
    "manager_id", "buddy_id",
})

# Explicitly forbidden even if a caller adds them to a payload.
PII_DENY_KEYS = frozenset({
    "national_id", "nationalid", "ssn", "salary", "compensation",
    "bank_account", "bankaccount", "iban", "credit_card", "creditcard",
    "passport", "aadhaar", "pan_number",
})

_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
    re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),  # card
    re.compile(r"(?i)\b(salary|national\s*id|bank\s*(account|iban)|ssn)\b[\s:]*[^\s,;]+"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),  # email
    re.compile(r"(?i)\b(passport|aadhaar)\b[\s:]*[A-Z0-9\- ]{4,}"),
    re.compile(r"\+?\d[\d\s\-()]{7,}\d"),  # phone-ish (last: avoids over-matching years)
)

REDACTED = "[REDACTED]"

# Grep gate for CI / game day: log PII grep must be 0.
PII_GREP_PATTERN = r"national.?id|salary|bank.?account|iban|\b\d{3}-\d{2}-\d{4}\b"


def scrub_text(text: str) -> str:
    if not text:
        return text
    out = text
    for p in _PATTERNS:
        out = p.sub(REDACTED, out)
    return out


def allowlisted_hire(payload: dict) -> dict:
    """Project a hire/HRIS payload down to the prompt allowlist + scrub values."""
    return {k: scrub_text(str(v)) for k, v in payload.items() if k in PROMPT_ALLOWLIST}


def scrub_mapping(mapping: dict) -> dict:
    """Scrub arbitrary metadata before audit/log insert. Deny-keys are dropped."""
    clean: dict = {}
    for k, v in mapping.items():
        if str(k).lower() in PII_DENY_KEYS:
            clean[k] = REDACTED
        elif isinstance(v, str):
            clean[k] = scrub_text(v)
        elif isinstance(v, dict):
            clean[k] = scrub_mapping(v)
        elif isinstance(v, list):
            clean[k] = [scrub_text(i) if isinstance(i, str) else (scrub_mapping(i) if isinstance(i, dict) else i) for i in v]
        else:
            clean[k] = v
    return clean


def contains_pii(text: str) -> bool:
    if not text:
        return False
    return scrub_text(text) != text
