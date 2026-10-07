"""4.2 Read-only tool wrappers. Planning may READ only — never execute.

Exposes:
  policy_retrieve(query, region, dept) -> cited chunks  (03 wrapper, read-only)
  find_slots(attendees, window) -> slots[]              (Calendar MCP read-only)

Both degrade safely: retrieval failure -> fixture-backed cited chunks for the
hire's region (never hallucinated policy without citation); calendar failure
-> TBD slots (never invented confirmed meetings). Write attempts are rejected
by _assert_read_only().
NOTE: this module must never import a write-capable client (mail sending,
chat posting, ticket creation, calendar write scopes, ...). CI greps it.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from .config import get_worker_settings
from .guards import BLOCKED_WRITE_VERBS, guard_tool_text
from .schemas import Citation, Slot

# ---------------------------------------------------------------- fixtures

# Minimal cited policy fixture per region (used in unit tests + when the RAG
# service is unreachable; keeps runs hermetic and fast — no live LLM needed).
_FIXTURE_CHUNKS: dict[str, list[dict[str, Any]]] = {
    "UK": [
        {
            "text": "UK employees receive 25 days annual leave + 8 bank holidays.",
            "citation": {"doc": "UK-Employee-Handbook-2026.pdf", "page": 14, "effective_date": "2026-04-01"},
        },
        {
            "text": "GBP 500 remote home-office equipment budget for Engineering.",
            "citation": {"doc": "UK-Employee-Handbook-2026.pdf", "page": 22, "effective_date": "2026-04-01"},
        },
        {
            "text": "Security awareness training must complete before production access.",
            "citation": {"doc": "UK-Employee-Handbook-2026.pdf", "page": 31, "effective_date": "2026-04-01"},
        },
    ],
    "DEFAULT": [
        {
            "text": "New hires receive statutory leave per regional handbook.",
            "citation": {"doc": "Employee-Handbook-2026.pdf", "page": 3, "effective_date": "2026-04-01"},
        },
        {
            "text": "Security awareness training must complete before production access.",
            "citation": {"doc": "Employee-Handbook-2026.pdf", "page": 9, "effective_date": "2026-04-01"},
        },
    ],
}


class CitedChunk(BaseModel):
    text: str = Field(min_length=1)
    citation: Citation
    score: float = 0.0


class RetrieveInput(BaseModel):
    query: str = Field(min_length=1)
    region: str = ""
    dept: str = ""


class SlotsInput(BaseModel):
    attendees: list[str] = Field(min_length=1)
    window: dict[str, str] = Field(default_factory=dict)


# ------------------------------------------------------- read-only enforcement

def _assert_read_only(name: str, payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, default=str).lower()
    for verb in BLOCKED_WRITE_VERBS:
        # A *tool call request* asking planning to perform a write is rejected.
        if f'"op": "{verb}' in blob or f'"action": "{verb}' in blob:
            raise PermissionError(f"read-only tool {name!r} blocked write attempt: {verb}")
    if "idempotency" in blob and name in ("policy_retrieve", "find_slots"):
        # Planning tools never mint execution idempotency keys; executor (05) owns that.
        pass


# ------------------------------------------------------- entitlement cache (role, region)

_cache: dict[tuple[str, str], tuple[float, list[CitedChunk]]] = {}


def cache_key(role: str, region: str) -> tuple[str, str]:
    return (role.strip().lower(), region.strip().lower())


def cache_get(role: str, region: str) -> list[CitedChunk] | None:
    settings = get_worker_settings()
    hit = _cache.get(cache_key(role, region))
    if not hit:
        return None
    ts, chunks = hit
    if time.time() - ts > settings.entitlement_cache_ttl_s:
        _cache.pop(cache_key(role, region), None)
        return None
    return chunks


def cache_set(role: str, region: str, chunks: list[CitedChunk]) -> None:
    _cache[cache_key(role, region)] = (time.time(), chunks)


def clear_cache() -> None:
    _cache.clear()


def cache_stats() -> dict[str, int]:
    return {"entries": len(_cache)}


# ------------------------------------------------------- budgets (4.5 caps)

class BudgetExceeded(RuntimeError):
    pass


class RunBudget:
    """Step + token caps per run (defaults: 12 steps, 30k tokens)."""

    def __init__(self, max_steps: int = 12, max_tokens: int = 30000) -> None:
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.steps = 0
        self.tokens = 0

    def consume_step(self, tokens: int = 0) -> None:
        self.steps += 1
        self.tokens += tokens
        if self.steps > self.max_steps:
            raise BudgetExceeded(f"step cap exceeded ({self.steps}>{self.max_steps})")
        if self.tokens > self.max_tokens:
            raise BudgetExceeded(f"token cap exceeded ({self.tokens}>{self.max_tokens})")

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, len(text or "") // 4)

    def snapshot(self) -> dict[str, int]:
        return {"steps": self.steps, "tokens": self.tokens,
                "max_steps": self.max_steps, "max_tokens": self.max_tokens}

    @classmethod
    def from_settings(cls) -> RunBudget:
        s = get_worker_settings()
        return cls(max_steps=s.max_steps_per_run, max_tokens=s.max_tokens_per_run)


def new_budget(max_steps: int | None = None, max_tokens: int | None = None) -> RunBudget:
    s = get_worker_settings()
    return RunBudget(max_steps=max_steps or s.max_steps_per_run,
                     max_tokens=max_tokens or s.max_tokens_per_run)


# ------------------------------------------------------- policy_retrieve (03 wrapper)

def _rag_http_retrieve(query: str, region: str, dept: str, timeout_s: float = 4.0) -> list[CitedChunk] | None:
    settings = get_worker_settings()
    base = (settings.rag_base_url or "").rstrip("/")
    if not base:
        return None
    body = json.dumps({"query": query, "region": region, "dept": dept, "k": 5}).encode()
    req = urllib.request.Request(f"{base}/api/v1/retrieve", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode())
        chunks = []
        for item in data.get("chunks", [])[:5]:
            cit = item.get("citation", {})
            chunks.append(CitedChunk(
                text=item.get("text", "")[:2000],
                citation=Citation(doc=cit.get("doc", "Employee-Handbook-2026.pdf"),
                                 page=cit.get("page"), effective_date=cit.get("effective_date")),
                score=float(item.get("score", 0.0)),
            ))
        return chunks or None
    except Exception:
        return None


def policy_retrieve(query: str, region: str = "", dept: str = "",
                    budget: RunBudget | None = None) -> list[CitedChunk]:
    """Read-only policy lookup. Returns cited chunks; never raises on lookup failure."""
    cleaned, injected = guard_tool_text(query)
    _assert_read_only("policy_retrieve", {"query": cleaned, "region": region, "dept": dept})
    if budget is not None:
        budget.consume_step(RunBudget.estimate_tokens(cleaned))
    chunks = _rag_http_retrieve(cleaned, region, dept)
    if chunks is None:
        fixture = _FIXTURE_CHUNKS.get(region, _FIXTURE_CHUNKS["DEFAULT"])
        chunks = [CitedChunk(text=c["text"], citation=Citation(**c["citation"]), score=0.9 - i * 0.1)
                  for i, c in enumerate(fixture)]
    if injected:
        chunks = [CitedChunk(text=guard_tool_text(c.text)[0], citation=c.citation, score=c.score)
                  for c in chunks]
    return chunks


# ------------------------------------------------------- find_slots (Calendar MCP read-only)

def _calendar_mcp_slots(attendees: list[str], window: dict[str, str]) -> list[Slot] | None:
    import os

    url = os.getenv("CALENDAR_MCP_URL", "")
    if not url:
        return None
    body = json.dumps({"attendees": attendees, "window": window, "mode": "read-only"}).encode()
    req = urllib.request.Request(f"{url.rstrip('/')}/slots", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode())
        return [Slot(start=s["start"], end=s["end"],
                     attendees=s.get("attendees", attendees), status="confirmed")
                for s in data.get("slots", [])[:5]]
    except Exception:
        return None


def find_slots(attendees: list[str], window: dict[str, str] | None = None,
               budget: RunBudget | None = None) -> list[Slot]:
    """Read-only calendar lookup. Unreachable scope -> TBD slots (never invented)."""
    window = window or {}
    _assert_read_only("find_slots", {"attendees": attendees, "window": window})
    if budget is not None:
        budget.consume_step(RunBudget.estimate_tokens(" ".join(attendees)))
    slots = _calendar_mcp_slots(attendees, window)
    if slots:
        return slots
    start = window.get("start") or "TBD"
    end = window.get("end") or "TBD"
    # Degraded TBD slot surfaces in the plan for HR edit (spec risk table).
    return [Slot(start=start, end=end, attendees=attendees, status="tbd")]


# ------------------------------------------------------- CrewAI tool adapters (read-only)

def crewai_tools():  # lazy import so unit tests don't need live LLM
    from crewai.tools import BaseTool

    class _PolicyTool(BaseTool):
        name: str = "policy_retrieve"
        description: str = "Read-only policy lookup. Input: {query, region, dept}. Returns cited chunks."

        def _run(self, query: str, region: str = "", dept: str = "") -> str:
            chunks = policy_retrieve(query, region, dept)
            return json.dumps([{"text": c.text, "citation": c.citation.model_dump(),
                                "score": c.score} for c in chunks])

    class _SlotsTool(BaseTool):
        name: str = "find_slots"
        description: str = ("Read-only calendar lookup. Input: {attendees, window}. "
                            "Returns slots; status may be 'tbd' when calendars are unreachable.")

        def _run(self, attendees: list[str], window: dict | None = None) -> str:
            slots = find_slots(attendees, window or {})
            return json.dumps([s.model_dump() for s in slots])

    return [_PolicyTool(), _SlotsTool()]
