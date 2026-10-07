"""Ingest pipeline (task 3.1): PDF/TXT/MD → chunks → embed → upsert.

- Page numbers preserved (pypdf per-page text; ``.txt`` uses ``--- page N ---``
  markers, ``.md`` is treated as a single page unless markers present).
- Deterministic chunk IDs (``doc:page:child``) → idempotent upserts.
- Payload carries region/department/effective_date/version/superseded_by/
  chunker_v/parent_id (RTM F-RAG-1).
"""
from __future__ import annotations

import os
import re

from chunking import chunk_pages
from config import SETTINGS
from vector_store import PolicyStore, StoredChunk

_PAGE_MARK = re.compile(r"^---\s*page\s+(\d+)\s*---\s*$", re.IGNORECASE | re.MULTILINE)


def extract_pages(path: str) -> list[tuple[int, str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages: list[tuple[int, str]] = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append((i, text))
        return pages
    with open(path, encoding="utf-8", errors="ignore") as fh:
        raw = fh.read()
    parts = _PAGE_MARK.split(raw)
    if len(parts) >= 3:
        # split -> ['', '1', text, '2', text, ...]
        pages = []
        for i in range(1, len(parts), 2):
            try:
                n = int(parts[i])
            except ValueError:
                n = len(pages) + 1
            pages.append((n, parts[i + 1] if i + 1 < len(parts) else ""))
        return pages
    return [(1, raw)]


def ingest_file(
    path: str,
    *,
    doc_id: str = "",
    region: str,
    department: str = "all",
    effective_date: str,
    version: int = 1,
    store: PolicyStore | None = None,
    embed_backend=None,
    parent_tokens: int = 0,
    child_tokens: int = 0,
) -> dict:
    """Ingest one file. Returns summary dict."""
    doc_id = doc_id or os.path.splitext(os.path.basename(path))[0]
    pages = extract_pages(path)
    parents, children = chunk_pages(
        doc_id,
        pages,
        parent_tokens or SETTINGS.chunk_parent_tokens,
        child_tokens or SETTINGS.chunk_child_tokens,
        version=version,
    )
    store = store or PolicyStore(
        persist_dir=SETTINGS.chroma_dir, collection=SETTINGS.collection
    )
    if embed_backend is None:
        import embeddings as _emb

        embed_backend = _emb.get_backend(
            SETTINGS.embedding_backend, SETTINGS.ollama_host, SETTINGS.embed_model
        )

    records: list[StoredChunk] = []
    for p in parents:
        records.append(
            StoredChunk(
                chunk_id=p.chunk_id,
                text=p.text,
                document_name=doc_id,
                region=region,
                department=department,
                page=p.page,
                effective_date=effective_date,
                version=version,
                chunker_v=SETTINGS.chunker_version,
                parent_id="",
                is_parent=True,
            )
        )
    for c in children:
        records.append(
            StoredChunk(
                chunk_id=c.chunk_id,
                text=c.text,
                document_name=doc_id,
                region=region,
                department=department,
                page=c.page,
                effective_date=effective_date,
                version=version,
                chunker_v=SETTINGS.chunker_version,
                parent_id=c.parent_id,
                is_parent=False,
            )
        )
    vectors = embed_backend.embed([r.text for r in records]) if records else []
    n = store.upsert(records, vectors)
    return {
        "doc_id": doc_id,
        "pages": len(pages),
        "parents": len(parents),
        "children": len(children),
        "upserted": n,
    }


def ingest_many(specs: list[dict], **kwargs) -> list[dict]:
    """Ingest multiple ``{path, doc_id, region, department, effective_date, version}``."""
    out = []
    for s in specs:
        out.append(
            ingest_file(
                s["path"],
                doc_id=s.get("doc_id", ""),
                region=s["region"],
                department=s.get("department", "all"),
                effective_date=s["effective_date"],
                version=int(s.get("version", 1)),
                **kwargs,
            )
        )
    return out
