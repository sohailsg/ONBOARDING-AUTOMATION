"""Unit: chunker page preservation + deterministic ids (RTM F-RAG-1)."""
from chunking import chunk_pages


def test_pages_preserved_and_ids_deterministic():
    pages = [(1, "alpha " * 50), (2, "beta " * 50), (3, "")]
    p1, c1 = chunk_pages("DOC", pages, parent_tokens=1024, child_tokens=256)
    p2, c2 = chunk_pages("DOC", pages, parent_tokens=1024, child_tokens=256)
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]  # idempotent upsert key
    assert all(c.page in (1, 2) for c in c1)  # empty page skipped, pages kept
    assert c1[0].chunk_id == "DOC:1:0"
    assert all(c.parent_id for c in c1)
    parent_ids = {p.chunk_id for p in p1}
    assert {c.parent_id for c in c1} <= parent_ids


def test_child_granularity_smaller_than_parent():
    pages = [(5, "word " * 2000)]
    parents, children = chunk_pages("D", pages)
    assert len(children) > len(parents) > 0
    assert all(c.page == 5 for c in children + parents)
