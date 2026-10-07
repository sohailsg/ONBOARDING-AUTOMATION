"""Integration: lifecycle supersede flow (RTM F-RAG-5) + cache (3.6)."""
from conftest import seed_doc


def test_reindex_supersedes_never_deletes(store, hash_backend):
    seed_doc(store, hash_backend, "UK-HB", "UK", "all", "2026-04-01",
             [(2, "Remote home-office budget in the UK is GBP 500.")], version=1)
    n_v1 = store.count()
    assert n_v1 > 0
    seed_doc(store, hash_backend, "UK-HB", "UK", "all", "2026-07-01",
             [(2, "Remote home-office budget in the UK is GBP 750.")], version=2)
    marked = store.mark_superseded("UK-HB", "UK-HB:v2", keep_version=2)
    assert marked == n_v1 > 0
    assert store.count() == 2 * n_v1  # nothing deleted: v1 + v2 coexist
    from retrieve import retrieve

    got = retrieve("UK home-office budget", "UK", "all", store=store,
                   embed_backend=hash_backend)
    assert got  # v2 still served
    # old vectors retained for audit/reproducibility
    raw = store._coll.get(where={"document_name": "UK-HB"}, include=["metadatas"], limit=100)
    assert any((m or {}).get("superseded_by") for m in raw["metadatas"])


def test_lifecycle_helper_marks_older_versions(store, hash_backend, tmp_path):
    seed_doc(store, hash_backend, "DOC", "UK", "all", "2026-01-01", [(1, "v1 text here")],
             version=1)
    p = tmp_path / "v2.txt"
    p.write_text("--- page 1 ---\nv2 text here with more words about policy")
    import lifecycle

    summary = lifecycle.reindex(
        str(p), doc_id="DOC", region="UK", department="all",
        effective_date="2026-06-01", version=2, store=store, embed_backend=hash_backend,
    )
    assert summary["superseded"] >= 1
    assert summary["new_version_id"] == "DOC:v2"


def test_entitlement_cache_roundtrip():
    import cache

    cache.invalidate()
    assert cache.get("Engineer", "UK") is None
    cache.put("Engineer", "UK", {"budget": "GBP 500"})
    assert cache.get("Engineer", "UK") == {"budget": "GBP 500"}
    cache.invalidate("Engineer", "UK")
    assert cache.get("Engineer", "UK") is None
