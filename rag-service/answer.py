"""Answer path (task 3.3): context-only prompt, citations, confidence, abstain.

Contract: ``answer(query, chunks) -> (text, citations[], confidence)``.

- Empty retrieval → abstain (never 500, never hallucinate).
- Confidence < threshold → abstain text + HR escalation flag, still logged.
- Every non-abstain answer carries doc+page+effective_date citations and the
  response is built only from retrieved context (extractive fallback when the
  local LLM is unreachable so tests/CI stay deterministic).
"""
from __future__ import annotations

import os
import re

import httpx

from bm25 import tokenize
from config import SETTINGS

_SENT = re.compile(r"(?<=[.!?])\s+")

# Function words carry no topical signal; coverage is measured on content
# words only so polite prefixes ("please tell me ...") don't sink confidence.
STOPWORDS = frozenset(
    "a an the and or but if then else when what which who whom whose how why "
    "whats whats whatever however many much more most some such no nor not only "
    "own same so than too very can will just don should now do does did is are "
    "was were be been being have has had having i me my we us our you your he "
    "him his she her it its they them their please tell explain know need want "
    "like get got to of in for on with about into over after before between "
    "out up down off there here this that these those am as at by from".split()
)


def _stem(tok: str) -> str:
    """Porter-lite: identical rule on query AND context, so plural/singular
    mismatches ("leaves"/"leave") meet while same-form tokens are untouched."""
    if len(tok) <= 3 or tok.endswith("ss"):
        return tok
    if tok.endswith("ies"):
        return tok[:-3] + "y"
    if tok.endswith("s"):
        return tok[:-1]
    return tok


def _content_tokens(text: str) -> set[str]:
    return {_stem(t) for t in tokenize(text) if t not in STOPWORDS and len(t) > 1}


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT.split(text.strip()) if s.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _best_sentence(query: str, chunk_text: str) -> str:
    qtok = set(tokenize(query))
    if not qtok:
        s = _sentences(chunk_text)
        return s[0] if s else ""
    best, best_n = "", -1
    for s in _sentences(chunk_text):
        n = len(qtok & set(tokenize(s)))
        if n > best_n:
            best, best_n = s, n
    return best or (_sentences(chunk_text)[0] if _sentences(chunk_text) else "")


def _extractive_answer(query: str, chunks: list[dict]) -> str:
    lines = []
    for c in chunks[:5]:
        s = _best_sentence(query, c.get("text", ""))
        if s:
            lines.append(
                f"{s} [{c.get('doc', '')}, p.{int(c.get('page', 0) or 0)}]"
            )
    return " ".join(lines)


def _ollama_answer(query: str, chunks: list[dict], model: str, host: str) -> str | None:
    context = "\n\n".join(
        f"[SOURCE doc={c.get('doc')} page={c.get('page')} date={c.get('effective_date')}]\n{c.get('text','')[:2000]}"
        for c in chunks[:5]
    )
    prompt = (
        "Answer STRICTLY from the SOURCES below. Every factual sentence must end "
        "with a citation like [doc, p.N]. If the sources do not contain the answer, "
        f"reply EXACTLY: {SETTINGS.abstain_text}\n\n"
        f"SOURCES:\n{context}\n\nQUESTION: {query}\nANSWER:"
    )
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{host.rstrip('/')}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False,
                      # Greedy decoding: identical queries must give identical
                      # answers (the chat log showed cited/abstain flips from
                      # sampling variance tripping the confidence threshold).
                      "options": {"temperature": 0, "seed": 42}},
            )
            r.raise_for_status()
            text = (r.json().get("response") or "").strip()
            return text or None
    except Exception:
        return None


def _confidence(query: str, chunks: list[dict], answer_text: str) -> float:
    if not chunks or not answer_text:
        return 0.0
    # Top-1 signal (mean over top-k dilutes: ranks 3-5 are distractors by design).
    top1 = float(chunks[0].get("score", 0.0))
    if top1 > 1.0:  # cross-encoder logits → squash to [0,1]
        top1 = 1.0 / (1.0 + pow(2.71828, -top1))
    score_c = min(1.0, top1 / 0.6)
    # Content-word coverage: is the retrieved context about the query?
    # Both sides stemmed identically so plurals meet ("leaves"/"leave").
    qtok = _content_tokens(query) or set(tokenize(query))
    ctx = {_stem(t) for t in tokenize(" ".join(c.get("text", "") for c in chunks[:5]))}
    cover_c = len(qtok & ctx) / max(1, len(qtok))
    # Grounding: is the answer built from the context?
    ans_tok = set(tokenize(answer_text))
    ground = len(ans_tok & ctx) / max(1, len(ans_tok))
    conf = 0.30 * score_c + 0.50 * cover_c + 0.20 * ground
    # Hard floors protect the abstain path for out-of-scope queries.
    # The 0.5 coverage floor is calibrated: answerable questions cover >=50%
    # of content words on both embedding backends, junk tops out at 40%.
    if cover_c < 0.5:
        conf = min(conf, 0.50)
    if cover_c < 0.2:
        conf = min(conf, 0.30)
    if top1 < 0.05:
        conf = min(conf, 0.20)
    return round(conf, 3)


def answer(
    query: str,
    chunks: list[dict],
    *,
    threshold: float = -1.0,
    llm: str = "auto",  # auto | ollama | extractive
    model: str = "",
    host: str = "",
) -> dict:
    """Returns ``{answer, citations, confidence, abstained}``."""
    threshold = SETTINGS.confidence_threshold if threshold < 0 else threshold
    if not chunks:
        return {
            "answer": SETTINGS.abstain_text,
            "citations": [],
            "confidence": 0.0,
            "abstained": True,
        }
    text: str | None = None
    if llm in ("auto", "ollama"):
        try:
            text = _ollama_answer(
                query,
                chunks,
                model or os.getenv("OLLAMA_CHAT_MODEL", SETTINGS.chat_model),
                host or SETTINGS.ollama_host,
            )
        except Exception:
            text = None
    if not text and llm in ("auto", "extractive"):
        text = _extractive_answer(query, chunks)
    text = (text or "").strip()
    citations = [
        {
            "doc": c.get("doc", ""),
            "page": int(c.get("page", 0) or 0),
            "effective_date": c.get("effective_date", ""),
        }
        for c in chunks[:5]
    ]
    conf = _confidence(query, chunks, text)
    if not text or conf < threshold or text == SETTINGS.abstain_text:
        return {
            "answer": SETTINGS.abstain_text,
            "citations": [],
            "confidence": conf,
            "abstained": True,
        }
    return {"answer": text, "citations": citations, "confidence": conf, "abstained": False}
