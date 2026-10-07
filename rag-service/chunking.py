"""Chunking: parent (~1024 tokens) / child (~256 tokens) with page preservation.

Pure-python word-based chunker (no vendor dep) so CI is deterministic.
Token estimate: ~4 chars per token.

Deterministic chunk IDs: ``{doc_id}:{page}:{child_idx}`` for idempotent upserts.
Parent IDs: ``{doc_id}:{page}:p{parent_idx}``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParentChunk:
    chunk_id: str
    doc_id: str
    page: int
    text: str
    child_ids: list[str]


@dataclass
class ChildChunk:
    chunk_id: str
    doc_id: str
    page: int
    parent_id: str
    text: str


def _words(text: str) -> list[str]:
    return text.split()


def _chunk_words(words: list[str], max_tokens: int) -> list[str]:
    # ~1 token ≈ 0.75 words → words budget ≈ tokens * 0.75; simpler: 1 word ≈ 1.3 tokens
    max_words = max(16, int(max_tokens / 1.3))
    out: list[str] = []
    for i in range(0, len(words), max_words):
        piece = " ".join(words[i : i + max_words])
        if piece.strip():
            out.append(piece)
    return out


def chunk_pages(
    doc_id: str,
    pages: list[tuple[int, str]],
    parent_tokens: int = 1024,
    child_tokens: int = 256,
    version: int | None = None,
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    """Chunk ``[(page_no, text)]`` preserving page numbers.

    Each page is chunked independently so citations keep exact pages
    (F-RAG-1 page-citation test). Empty pages are skipped.

    Chunk IDs are deterministic. Without ``version`` they are
    ``{doc}:{page}:{child}`` (idempotent re-ingest of the same file).
    With ``version`` they become ``{doc}:v{n}:{page}:{child}`` so a new
    doc version coexists with superseded ones (lifecycle audit, F-RAG-5).
    """
    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    tag = f"v{version}:" if version is not None else ""
    for page_no, text in pages:
        words = _words(text or "")
        if not words:
            continue
        parent_texts = _chunk_words(words, parent_tokens)
        for p_idx, p_text in enumerate(parent_texts):
            parent_id = f"{doc_id}:{tag}{page_no}:p{p_idx}"
            child_texts = _chunk_words(_words(p_text), child_tokens)
            c_ids: list[str] = []
            for c_idx, c_text in enumerate(child_texts):
                # child index is global within the page for stable ids
                global_c = sum(len(_chunk_words(_words(t), child_tokens)) for t in parent_texts[:p_idx]) + c_idx
                cid = f"{doc_id}:{tag}{page_no}:{global_c}"
                c_ids.append(cid)
                children.append(
                    ChildChunk(
                        chunk_id=cid, doc_id=doc_id, page=page_no, parent_id=parent_id, text=c_text
                    )
                )
            parents.append(
                ParentChunk(
                    chunk_id=parent_id, doc_id=doc_id, page=page_no, text=p_text, child_ids=c_ids
                )
            )
    return parents, children
