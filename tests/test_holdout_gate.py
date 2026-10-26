"""
Unit tests for the Hidden Holdout Gate (sentinel/scripts/holdout_gate.py).
"""

from sentinel.scripts.holdout_gate import run_holdout_gate


def test_holdout_gate_runs_and_verifies_invariants(tmp_path):
    report_file = tmp_path / "holdout-report.json"
    report = run_holdout_gate(output_json=report_file)

    assert report["gate"] == "holdout_tests"
    assert report["verdict"] == "PASS"
    assert report["invariants_tested"] >= 5
    assert report["invariants_passed"] == report["invariants_tested"]
    assert report["invariants_failed"] == 0
    assert report_file.exists()
