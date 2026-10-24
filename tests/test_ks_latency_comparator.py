"""
Unit tests for Kolmogorov-Smirnov Latency Distribution Comparator.
Validates non-parametric two-sample D_KS calculation and drift rejection.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.ks_latency_comparator import (
    KolmogorovSmirnovLatencyComparator,
    run_ks_comparator_audit,
)


def test_ks_comparator_identical_distributions():
    comparator = KolmogorovSmirnovLatencyComparator()
    samples = [50.0 + i for i in range(30)]
    res = comparator.compare_distributions(samples, samples)

    assert res["verdict"] == "PASS"
    assert res["d_statistic"] == 0.0
    assert res["is_statistically_different"] is False


def test_ks_comparator_detects_distribution_drift():
    comparator = KolmogorovSmirnovLatencyComparator()
    stable = [40.0 + (i * 0.5) for i in range(50)]
    # Candidate experiences heavy tail shift
    candidate = [75.0 + (i * 2.0) for i in range(50)]
    res = comparator.compare_distributions(candidate, stable)

    assert res["verdict"] == "LATENCY_DISTRIBUTION_DRIFT"
    assert res["d_statistic"] > 0.50
    assert res["is_statistically_different"] is True


def test_run_ks_comparator_audit_artifact(tmp_path: Path):
    report = run_ks_comparator_audit(output_dir=tmp_path)
    assert report["verdict"] == "PASS"
    assert "wasserstein_distance" in report
    assert "candidate_p99_ms" in report
    out_file = tmp_path / "ks-latency-distribution-report.json"
    assert out_file.exists()
    alias_file = tmp_path / "ks-latency-report.json"
    assert alias_file.exists()
