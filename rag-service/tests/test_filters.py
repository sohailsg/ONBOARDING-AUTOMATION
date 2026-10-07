"""Unit: F-RAG-2 filters enforced in code (region/dept/date/superseded)."""
from conftest import seed_doc


def test_region_isolation(store, hash_backend):
    seed_doc(store, hash_backend, "UK-DOC", "UK", "all", "2026-01-01", [(1, "uk leave policy text")])
    seed_doc(store, hash_backend, "US-DOC", "US", "all", "2026-01-01", [(1, "us leave policy text")])
    from retrieve import retrieve

    got = retrieve("leave policy", "UK", "all", store=store, embed_backend=hash_backend)
    assert got and all(c["doc"] == "UK-DOC" for c in got)


def test_dept_filter_all_vs_specific(store, hash_backend):
    seed_doc(store, hash_backend, "ENG-DOC", "IN", "Engineering", "2026-01-01",
             [(1, "monitor budget macbook engineering equipment")])
    from retrieve import retrieve

    assert retrieve("monitor budget", "IN", "Engineering", store=store,
                    embed_backend=hash_backend)
    assert retrieve("monitor budget", "IN", "Sales", store=store,
                    embed_backend=hash_backend) == []
    # dept=all caller sees everything in region
    assert retrieve("monitor budget", "IN", "all", store=store,
                    embed_backend=hash_backend)


def test_effective_date_and_superseded_excluded(store, hash_backend):
    seed_doc(store, hash_backend, "FUTURE", "UK", "all", "2999-01-01", [(1, "future policy content")])
    seed_doc(store, hash_backend, "OLD", "UK", "all", "2026-01-01", [(1, "old policy content")],
             version=1)
    store.mark_superseded("OLD", "OLD:v2")
    from retrieve import retrieve

    for q in ("future policy content", "old policy content"):
        got = retrieve(q, "UK", "all", store=store, embed_backend=hash_backend)
        assert all(c["doc"] not in ("FUTURE", "OLD") for c in got), q


def test_idempotent_upsert(store, hash_backend):
    recs = seed_doc(store, hash_backend, "DOC", "UK", "all", "2026-01-01", [(1, "same text here")])
    n_before = store.count()
    store.upsert(recs, hash_backend.embed([r.text for r in recs]))
    assert store.count() == n_before
