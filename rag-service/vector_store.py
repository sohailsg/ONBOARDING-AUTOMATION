"""Chroma-backed vector store (persistent local; replaces Qdrant per free stack).

Collection ``policies_v1``. Metadata per point (1:1 with Qdrant payload plan):

    document_name, region, department, page_number, effective_date (ISO),
    superseded_by ("" = active), version, chunker_v, parent_id, is_parent, text

Active filter: ``superseded_by == ""``. Superseded points are retained for
audit/reproducibility and excluded from queries by the code filter (F-RAG-2).
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field


@dataclass
class StoredChunk:
    chunk_id: str
    text: str
    document_name: str
    region: str
    department: str
    page: int
    effective_date: str
    superseded_by: str = ""
    version: int = 1
    chunker_v: str = "pypdf-v1"
    parent_id: str = ""
    is_parent: bool = False


def _client(persist_dir: str):
    import chromadb

    os.makedirs(persist_dir, exist_ok=True)
    return chromadb.PersistentClient(path=persist_dir)


class PolicyStore:
    def __init__(
        self, persist_dir: str = "", collection: str = "", client=None, _coll=None
    ) -> None:
        self.persist_dir = persist_dir or os.getenv("CHROMA_DIR", "./data/chroma")
        self.collection_name = collection or os.getenv(
            "CHROMA_COLLECTION", "policies_v1"
        )
        if _coll is not None:
            self._coll = _coll
        else:
            cli = client or _client(self.persist_dir)
            self._coll = cli.get_or_create_collection(
                name=self.collection_name, metadata={"hnsw:space": "cosine"}
            )

    # -- writes ---------------------------------------------------------
    def upsert(
        self, chunks: list[StoredChunk], embeddings: list[list[float]]
    ) -> int:
        assert len(chunks) == len(embeddings)
        if not chunks:
            return 0
        self._coll.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=[list(map(float, e)) for e in embeddings],
            documents=[c.text for c in chunks],
            metadatas=[self._meta(c) for c in chunks],
        )
        return len(chunks)

    @staticmethod
    def _meta(c: StoredChunk) -> dict:
        return {
            "document_name": c.document_name,
            "region": c.region,
            "department": c.department,
            "page_number": int(c.page),
            "effective_date": c.effective_date,
            "superseded_by": c.superseded_by or "",
            "version": int(c.version),
            "chunker_v": c.chunker_v,
            "parent_id": c.parent_id or "",
            "is_parent": bool(c.is_parent),
        }

    def mark_superseded(
        self, doc_id: str, new_version_id: str, keep_version: int = 0
    ) -> int:
        """Set superseded_by on old active points of doc_id. Never deletes.

        Points with ``version >= keep_version`` are left active (the freshly
        ingested version); everything older is superseded but retained.
        """
        got = self._coll.get(
            where={"document_name": doc_id}, include=["metadatas"], limit=100000
        )
        ids = got.get("ids", []) or []
        metas = got.get("metadatas", []) or []
        targets: list[str] = []
        for i, m in zip(ids, metas):
            m = m or {}
            if (m or {}).get("document_name") != doc_id or (m or {}).get("superseded_by"):
                continue
            try:
                v = int(m.get("version", 1) or 1)
            except Exception:
                v = 1
            if keep_version and v >= keep_version:
                continue
            targets.append(i)
        for tid in targets:
            cur = self._coll.get(ids=[tid], include=["metadatas", "documents"])
            meta = (cur.get("metadatas") or [{}])[0] or {}
            meta["superseded_by"] = new_version_id
            self._coll.update(ids=[tid], metadatas=[meta])
        return len(targets)

    # -- reads ----------------------------------------------------------
    def dense_query(
        self,
        query_embedding: list[float],
        region: str,
        dept: str,
        today: str = "",
        n_results: int = 30,
    ) -> list[dict]:
        """Chroma dense query with code-enforced pre-filter (F-RAG-2)."""
        today = today or dt.date.today().isoformat()
        where = self._where(region, dept)
        try:
            res = self._coll.query(
                query_embeddings=[list(map(float, query_embedding))],
                n_results=min(max(1, n_results), 200),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []
        out: list[dict] = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, doc_id in enumerate(ids):
            m = metas[i] or {}
            if not self._active(m, dept, region, today):
                continue
            out.append(
                {
                    "chunk_id": doc_id,
                    "text": docs[i],
                    "document_name": m.get("document_name", ""),
                    "region": m.get("region", ""),
                    "department": m.get("department", ""),
                    "page": int(m.get("page_number", 0) or 0),
                    "effective_date": m.get("effective_date", ""),
                    "version": int(m.get("version", 1) or 1),
                    "parent_id": m.get("parent_id", ""),
                    "is_parent": bool(m.get("is_parent", False)),
                    "distance": float(dists[i]) if i < len(dists) else 1.0,
                }
            )
        return out

    def filtered_corpus(
        self, region: str, dept: str, today: str = ""
    ) -> list[dict]:
        """All active chunks for (region, dept) — BM25 side + parent expansion."""
        today = today or dt.date.today().isoformat()
        try:
            got = self._coll.get(
                where=self._where(region, dept),
                include=["documents", "metadatas"],
                limit=100000,
            )
        except Exception:
            return []
        out: list[dict] = []
        for i, doc_id in enumerate(got.get("ids", []) or []):
            m = (got.get("metadatas") or [{}])[i] or {}
            if not self._active(m, dept, region, today):
                continue
            docs = got.get("documents") or []
            out.append(
                {
                    "chunk_id": doc_id,
                    "text": docs[i] if i < len(docs) else "",
                    "document_name": m.get("document_name", ""),
                    "region": m.get("region", ""),
                    "department": m.get("department", ""),
                    "page": int(m.get("page_number", 0) or 0),
                    "effective_date": m.get("effective_date", ""),
                    "version": int(m.get("version", 1) or 1),
                    "parent_id": m.get("parent_id", ""),
                    "is_parent": bool(m.get("is_parent", False)),
                }
            )
        return out

    def get_parent(self, parent_id: str) -> dict | None:
        try:
            got = self._coll.get(ids=[parent_id], include=["documents", "metadatas"])
        except Exception:
            return None
        if not got.get("ids"):
            return None
        m = (got.get("metadatas") or [{}])[0] or {}
        d = (got.get("documents") or [""])[0]
        return {
            "chunk_id": parent_id,
            "text": d,
            "document_name": m.get("document_name", ""),
            "page": int(m.get("page_number", 0) or 0),
            "effective_date": m.get("effective_date", ""),
        }

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _where(region: str, dept: str) -> dict:
        # region must match; dept matches user dept OR "all"
        clauses: list[dict] = [{"region": region}]
        if dept and dept.lower() != "all":
            clauses.append({"$or": [{"department": "all"}, {"department": dept}]})
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _active(m: dict, dept: str, region: str, today: str) -> bool:
        if (m.get("region") or "") != region:
            return False
        md = (m.get("department") or "all").lower()
        if dept and dept.lower() != "all" and md not in ("all", dept.lower()):
            # chroma may store original case; compare case-insensitively
            if (m.get("department") or "") != dept:
                return False
        if (m.get("superseded_by") or "") != "":
            return False
        eff = (m.get("effective_date") or "0000-00-00")
        try:
            if eff > today:
                return False
        except Exception:
            pass
        return True

    def count(self) -> int:
        try:
            return int(self._coll.count())
        except Exception:
            return 0
