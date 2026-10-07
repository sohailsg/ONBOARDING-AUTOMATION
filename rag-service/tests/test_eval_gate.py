"""Eval gate tests (RTM F-RAG-6): gate math + mutation check.

The full golden eval runs in CI (nightly/main); these unit tests pin the gate
semantics: faithful answers pass, hallucinated answers fail, and lowering the
threshold below 0.9 is what the gate forbids.
"""
from eval.evaluate import GATE_ABSTAIN, GATE_FAITHFULNESS, GATE_RECALL, faithfulness


def test_gate_thresholds_match_spec():
    assert GATE_FAITHFULNESS == 0.9
    assert GATE_RECALL == 0.8
    assert GATE_ABSTAIN == 0.8


def test_faithfulness_grounded_vs_hallucinated():
    ctx = ["Remote home-office budget in the UK is GBP 500 per employee."]
    assert faithfulness("The UK budget is GBP 500 per employee.", ctx) >= 0.9
    assert faithfulness("The moon is made of cheese and dragons.", ctx) == 0.0
    assert faithfulness("", ctx) == 0.0


def test_golden_set_shape_and_coverage():
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "eval", "golden_set.json")
    items = json.load(open(path))
    assert len(items) >= 100
    regions = {it["region"] for it in items}
    assert {"UK", "US", "DE", "IN"} <= regions
    assert any(it["abstain"] for it in items)
    for it in items:
        assert it["question"] and it["region"]
        if not it["abstain"]:
            assert it["expected_doc"] and it["expected_page"] and it["must_contain"]


def test_mutation_fails_gate():
    """A mutated (hallucinated) answer must score below the gate."""
    ctx = ["Annual leave in Germany is 30 days per calendar year."]
    mutated = "Germany gives 500 days leave plus a free car. [made-up cite]"
    assert faithfulness(mutated, ctx) < GATE_FAITHFULNESS
