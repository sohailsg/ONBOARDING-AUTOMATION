"""Unit+integration: citations mandatory, abstain behavior (RTM F-RAG-4)."""
from conftest import seed_doc


def _chunks():
    return [
        {"text": "Remote home-office budget in the UK is GBP 500 per employee.",
         "doc": "UK-HB", "page": 2, "effective_date": "2026-04-01", "score": 0.8,
         "chunk_id": "UK-HB:2:0"},
        {"text": "Claim it via the expenses tool within 90 days.",
         "doc": "UK-HB", "page": 2, "effective_date": "2026-04-01", "score": 0.5,
         "chunk_id": "UK-HB:2:1"},
    ]


def test_answer_carries_citations_and_confidence():
    from answer import answer

    res = answer("What is the UK home-office budget?", _chunks(), llm="extractive")
    assert not res["abstained"]
    assert "GBP 500" in res["answer"]
    assert res["citations"] and all(
        c["doc"] and c["page"] and c["effective_date"] for c in res["citations"]
    )
    assert 0.0 <= res["confidence"] <= 1.0


def test_abstain_on_empty_retrieval():
    from answer import answer
    from config import SETTINGS

    res = answer("What is the stock price today?", [], llm="extractive")
    assert res["abstained"] and res["answer"] == SETTINGS.abstain_text
    assert res["citations"] == [] and res["confidence"] == 0.0


def test_abstain_on_low_confidence_junk():
    from answer import answer

    junk = [
        {"text": "Annual leave in Germany is 30 days per calendar year.",
         "doc": "DE-LP", "page": 1, "effective_date": "2026-03-01", "score": 0.02,
         "chunk_id": "DE-LP:1:0"},
    ]
    res = answer("What is the stock price today?", junk, llm="extractive")
    assert res["abstained"]


def test_no_uncited_claims_grep():
    """Every factual (non-abstain) answer must carry citations."""
    from answer import answer

    for q in ("UK home-office budget?", "How to claim UK budget?"):
        res = answer(q, _chunks(), llm="extractive")
        if not res["abstained"]:
            assert res["citations"], q


def test_chat_endpoint_abstains_gracefully():
    from fastapi.testclient import TestClient

    import app as app_mod

    client = TestClient(app_mod.app)
    r = client.post("/chat", json={"question": "stats?", "region": "XX", "dept": "all"})
    assert r.status_code == 200
    body = r.json()
    assert body["abstained"] is True and body["citations"] == []
