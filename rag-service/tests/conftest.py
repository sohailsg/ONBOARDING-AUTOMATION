"""Shared fixtures: ephemeral Chroma collection + hash embeddings per test."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("EMBEDDING_BACKEND", "hash")


@pytest.fixture()
def collection_name():
    import uuid

    # chroma EphemeralClient shares in-process state across instances with the
    # same name -> unique collection per test for isolation.
    return f"policies_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def store(collection_name):
    import chromadb

    from vector_store import PolicyStore

    client = chromadb.EphemeralClient()
    coll = client.get_or_create_collection(
        name=collection_name, metadata={"hnsw:space": "cosine"}
    )
    return PolicyStore(collection=collection_name, _coll=coll)


@pytest.fixture()
def hash_backend():
    from embeddings import HashEmbeddingBackend

    return HashEmbeddingBackend()


def seed_doc(store, backend, doc_id, region, dept, date, pages, version=1):
    """Ingest in-memory pages straight through chunk+embed+upsert."""
    from chunking import chunk_pages
    from vector_store import StoredChunk

    parents, children = chunk_pages(doc_id, pages, version=version)
    records = [
        StoredChunk(
            chunk_id=p.chunk_id, text=p.text, document_name=doc_id, region=region,
            department=dept, page=p.page, effective_date=date, version=version,
            chunker_v="test", parent_id="", is_parent=True,
        )
        for p in parents
    ] + [
        StoredChunk(
            chunk_id=c.chunk_id, text=c.text, document_name=doc_id, region=region,
            department=dept, page=c.page, effective_date=date, version=version,
            chunker_v="test", parent_id=c.parent_id, is_parent=False,
        )
        for c in children
    ]
    store.upsert(records, backend.embed([r.text for r in records]))
    return records
