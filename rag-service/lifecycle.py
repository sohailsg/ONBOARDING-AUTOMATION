"""Lifecycle (task 3.4): version bump via ``superseded_by`` — never delete.

``POST /rag/reindex {doc_id, version, ...}`` ingests the new file version then
marks all old active points ``superseded_by=<new_doc_version_id>`` so old
answers stay reproducible from superseded vectors (audit), while live queries
exclude them via the code filter.
"""
from __future__ import annotations

from config import SETTINGS
from ingest import ingest_file


def reindex(
    path: str,
    *,
    doc_id: str,
    region: str,
    department: str = "all",
    effective_date: str,
    version: int,
    store=None,
    embed_backend=None,
) -> dict:
    from vector_store import PolicyStore

    store = store or PolicyStore(
        persist_dir=SETTINGS.chroma_dir, collection=SETTINGS.collection
    )
    new_version_id = f"{doc_id}:v{version}"
    summary = ingest_file(
        path,
        doc_id=doc_id,
        region=region,
        department=department,
        effective_date=effective_date,
        version=version,
        store=store,
        embed_backend=embed_backend,
    )
    # Stamp the freshly ingested points with the new version id is implicit via
    # version int; now supersede older versions of the same doc.
    marked = _supersede_older(store, doc_id, version, new_version_id)
    summary.update({"new_version_id": new_version_id, "superseded": marked})
    return summary


def _supersede_older(store, doc_id: str, keep_version: int, new_version_id: str) -> int:
    try:
        got = store._coll.get(
            where={"document_name": doc_id}, include=["metadatas"], limit=100000
        )
    except Exception:
        return 0
    n = 0
    for i, m in zip(got.get("ids", []) or [], got.get("metadatas", []) or []):
        m = m or {}
        try:
            v = int(m.get("version", 1) or 1)
        except Exception:
            v = 1
        if v < keep_version and not m.get("superseded_by"):
            m["superseded_by"] = new_version_id
            try:
                store._coll.update(ids=[i], metadatas=[m])
                n += 1
            except Exception:
                pass
    return n
