"""
Unit tests for Multiple Candidate Fix Selector (sentinel/scripts/candidate_selector.py).
"""

from sentinel.scripts.candidate_selector import CandidateSelector


def test_candidate_selector_identifies_winner_and_rejection_reasons():
    selector = CandidateSelector()
    res = selector.evaluate_all()

    assert res["total_candidates"] == 3
    assert res["selected_candidate_id"] == "cand-003-sound"
    assert res["winner"]["status"] == "SELECTED"

    cand_map = {c["candidate_id"]: c for c in res["candidates"]}
    # Candidate 1: Evasion -> blocked by Integrity Gate
    assert cand_map["cand-001-evasion"]["status"] == "REJECTED"
    assert "Integrity Gate blocked" in cand_map["cand-001-evasion"]["rejection_reason"]
    assert cand_map["cand-001-evasion"]["trust_score"] < 40

    # Candidate 2: Shallow -> fails holdout invariant
    assert cand_map["cand-002-shallow"]["status"] == "REJECTED"
    assert "Holdout Gate failed" in cand_map["cand-002-shallow"]["rejection_reason"]

    # Candidate 3: Sound -> selected
    assert cand_map["cand-003-sound"]["status"] == "SELECTED"
    assert cand_map["cand-003-sound"]["trust_score"] >= 90
