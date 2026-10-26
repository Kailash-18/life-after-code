"""
Unit tests for Deterministic Trust Scorer (sentinel/scripts/trust_scorer.py).
"""

from sentinel.scripts.trust_scorer import RepairMetrics, calculate_trust_score


def test_trust_scorer_exemplary_case():
    metrics = RepairMetrics(
        integrity_blocking_count=0,
        integrity_warning_count=0,
        regression_proven=True,
        regression_has_correct_assertion=True,
        holdout_invariants_passed=True,
        sast_violations_count=0,
        added_lines=8,
        deleted_lines=2,
        has_isolated_regression_test=True,
        coverage_delta_percent=1.2,
    )
    res = calculate_trust_score(metrics)
    assert res["trust_score"] == 100
    assert res["rating"] == "EXEMPLARY"
    assert len(res["deductions"]) == 0
    assert len(res["bonuses"]) >= 2


def test_trust_scorer_severe_penalty_on_integrity_violation():
    metrics = RepairMetrics(
        integrity_blocking_count=2,  # -100 points
        regression_proven=False,
    )
    res = calculate_trust_score(metrics)
    assert res["trust_score"] == 0
    assert res["rating"] == "DANGEROUS"
    assert any("Integrity Gate" in d["factor"] for d in res["deductions"])


def test_ai_explanation_and_governance():
    metrics = RepairMetrics(holdout_invariants_passed=False)
    res = calculate_trust_score(metrics)
    assert "AI can explain but never set" in res["governance_rule"]
    assert "secret holdout test invariants" in res["ai_explanation"]
