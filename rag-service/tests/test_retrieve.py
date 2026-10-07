"""Integration: hybrid->rerank->expand ordering + recall on seed corpus (RTM F-RAG-3)."""
import time

from conftest import seed_doc


def _seed(store, hash_backend):
    seed_doc(store, hash_backend, "UK-HB", "UK", "all", "2026-04-01",
             [(2, "Remote home-office budget in the UK is GBP 500 per employee. "
                  "Claim it via the expenses tool within 90 days."),
              (3, "Annual leave in the UK is 28 days per year including bank holidays.")])
    seed_doc(store, hash_backend, "US-BG", "US", "all", "2026-01-15",
             [(2, "The 401k retirement plan matches 100 percent of contributions "
                  "up to 5 percent of salary.")])


def test_hybrid_returns_ranked_cited_chunks(store, hash_backend):
    _seed(store, hash_backend)
    from retrieve import retrieve

    chunks = retrieve("UK home-office budget GBP", "UK", "all", store=store,
                      embed_backend=hash_backend)
    assert len(chunks) <= 10  # top-5 + parent expansion
    top = chunks[0]
    assert top["doc"] == "UK-HB" and top["page"] == 2
    assert top["effective_date"] == "2026-04-01"
    scores = [c["score"] for c in chunks if not c.get("parent_expanded")]
    assert scores == sorted(scores, reverse=True)


def test_rerank_prefers_exact_terms_over_dense_noise(store, hash_backend):
    _seed(store, hash_backend)
    from retrieve import retrieve

    chunks = retrieve("401k match 5 percent contributions", "US", "all", store=store,
                      embed_backend=hash_backend)
    assert chunks and chunks[0]["doc"] == "US-BG"


def test_retrieval_latency_budget(store, hash_backend):
    _seed(store, hash_backend)
    from retrieve import retrieve

    t0 = time.perf_counter()
    retrieve("annual leave UK days", "UK", "all", store=store, embed_backend=hash_backend)
    assert (time.perf_counter() - t0) * 1000 < 1500  # NFR p95 < 1.5 s


def test_empty_index_returns_empty(store, hash_backend):
    from retrieve import retrieve

    assert retrieve("anything", "UK", "all", store=store, embed_backend=hash_backend) == []
