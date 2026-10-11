"""Unit+integration: citations mandatory, abstain behavior (RTM F-RAG-4)."""


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

    app_mod = _load_app()

    client = TestClient(app_mod.app)
    r = client.post("/chat", json={"question": "stats?", "region": "XX", "dept": "all"})
    assert r.status_code == 200
    body = r.json()
    assert body["abstained"] is True and body["citations"] == []


def _load_app():
    """Load rag-service/app.py by path.

    The service module is named `app`, which collides with backend/app
    (importable as top-level `app` once backend suites run in the same pytest
    process). importlib keeps this hermetic either way.
    """
    import importlib.util
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "rag_service_app", os.path.join(here, "app.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_answer_gateway_shape_retrieves_then_answers():
    """Gateway (02) posts {question, region, dept} with no chunks — the
    service must retrieve server-side, not 422/abstain (integration RTM)."""
    from fastapi.testclient import TestClient

    app_mod = _load_app()
    chunks = [{
        "text": "Remote home-office budget in the UK is GBP 500 per employee.",
        "doc": "UK-HB", "page": 2, "effective_date": "2026-04-01",
        "score": 0.8, "chunk_id": "UK-HB:v1:2:0",
    }]
    app_mod.retrieve_fn = lambda *a, **k: chunks
    client = TestClient(app_mod.app)
    r = client.post("/answer", json={"question": "UK home-office budget?",
                                     "region": "UK", "dept": "all"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert not body["abstained"] and "GBP 500" in body["answer"]
    assert body["citations"][0]["doc"] == "UK-HB"
