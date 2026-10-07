"""F-API-7 chat: server-side profile -> RAG call -> chat_logs. Abstains without citations."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import TokenData, require_roles
from ..config import get_settings
from ..db import get_session
from ..models import ChatLog, Employee
from ..pii import scrub_text
from ..ratelimit import limiter
from ..schemas import ChatRequest, ChatResponse, Citation

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
log = logging.getLogger("onboarding.chat")

ABSTAIN = "I don't have a cited policy passage for that yet, so I can't answer reliably. An HR teammate will follow up."
MIN_CONFIDENCE = 0.35


async def rag_answer(question: str, region: str, dept: str) -> dict:
    """Call the RAG service (03). Raises on transport failure so callers abstain."""
    import httpx

    settings = get_settings()
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{settings.RAG_BASE_URL.rstrip('/')}/answer",
            json={"question": question, "region": region, "dept": dept},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "answer": str(data.get("answer", "")),
            "citations": data.get("citations", []) or [],
            "confidence": float(data.get("confidence", 0.0)),
        }


def _allowlisted_log(question: str, answer: str) -> dict:
    """PII minimization: persist only the Q/A + citations, never raw profile fields."""
    return {"q_len": len(question), "a_len": len(answer)}


@router.post("", response_model=ChatResponse)
@limiter.limit("30/minute")
async def policy_chat(
    request: Request,
    payload: ChatRequest,
    user: TokenData = Depends(require_roles("employee", "hr_admin")),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    employee = await session.get(Employee, user.sub)
    region = employee.region if employee else ""
    dept = employee.dept if employee else ""
    employee_id = employee.id if employee else user.sub

    try:
        result = await rag_answer(payload.question, region, dept)
        answer, citations, confidence = result["answer"], result["citations"], float(result["confidence"])
        if not answer.strip() or not citations or confidence < MIN_CONFIDENCE:
            raise ValueError("low-confidence")
        parsed = [
            Citation(doc=str(c.get("doc", "")), page=c.get("page"), effective_date=c.get("effective_date"))
            for c in citations if c.get("doc")
        ]
        if not parsed:
            raise ValueError("no-citations")
        out = ChatResponse(answer=answer, citations=parsed, confidence=confidence)
    except Exception as exc:
        log.info("chat abstain: %s", exc)
        out = ChatResponse(answer=ABSTAIN, citations=[], confidence=0.0)

    _allowlisted_log(payload.question, out.answer)
    from .. import llm_ledger as _ledger
    from ..metrics import observe_chat as _observe_chat

    _observe_chat("cited" if out.citations else "abstained", out.confidence)
    _ledger.record_llm_call(case_id=employee_id, name="chat",
                            faithfulness=out.confidence if out.citations else None)
    session.add(
        ChatLog(
            employee_id=employee_id if employee else user.sub,
            question=scrub_text(payload.question[:2000]),
            answer=scrub_text(out.answer),
            citations=[c.model_dump() for c in out.citations],
            confidence=out.confidence,
        )
    )
    await session.commit()
    return out
