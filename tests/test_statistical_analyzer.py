"""
Unit tests for Sentinel Statistical Telemetry & Error Budget Analysis Engine.
Validates Mann-Whitney U test, IQR bounds, outlier z-scores, and Google SRE error budget burn rates.
"""

from __future__ import annotations

import pytest

from sentinel.scripts.statistical_analyzer import (
    calculate_iqr,
    calculate_z_score_anomalies,
    calculate_error_budget_burn_rate,
    compute_composite_health_score,
    mann_whitney_u_test,
)


def test_calculate_iqr_empty():
    res = calculate_iqr([])
    assert res["median"] == 0.0
    assert res["iqr"] == 0.0
    assert res["outlier_threshold"] == 0.0


def test_calculate_iqr_nominal():
    values = [10.0, 12.0, 14.0, 15.0, 18.0, 20.0, 22.0]
    res = calculate_iqr(values)
    assert res["median"] == 15.0
    assert res["q1"] <= res["median"] <= res["q3"]
    assert res["iqr"] > 0
    assert res["outlier_threshold"] > res["q3"]


def test_calculate_z_score_anomalies():
    # 9 normal values around 20, 1 extreme outlier at 500
    values = [20.0, 21.0, 19.0, 20.5, 22.0, 19.5, 20.0, 21.5, 19.8, 500.0]
    anomalies = calculate_z_score_anomalies(values, threshold=2.5)
    assert len(anomalies) == 1
    assert anomalies[0] == 500.0


def test_mann_whitney_u_test_empty():
    res = mann_whitney_u_test([], [10.0, 20.0])
    assert res["is_significant"] is False
    assert res["p_value"] == 1.0


def test_mann_whitney_u_test_identical_distributions():
    sample_a = [20.0, 22.0, 21.0, 23.0, 20.5, 22.5]
    sample_b = [20.1, 21.9, 21.2, 22.8, 20.6, 22.4]
    res = mann_whitney_u_test(sample_a, sample_b)
    assert res["is_significant"] is False
    assert res["p_value"] > 0.05


def test_mann_whitney_u_test_significant_regression():
    # Candidate latencies heavily shifted higher compared to stable baseline
    candidate = [150.0, 160.0, 175.0, 180.0, 190.0, 210.0, 220.0, 250.0]
    stable = [15.0, 18.0, 20.0, 22.0, 19.0, 21.0, 23.0, 20.0]
    res = mann_whitney_u_test(candidate, stable)
    assert res["is_significant"] is True
    assert res["p_value"] < 0.05
    assert "regression confirmed" in res["interpretation"]


def test_error_budget_burn_rate_healthy():
    res = calculate_error_budget_burn_rate(error_rate=0.0001, slo_target=0.999)
    assert res["burn_rate"] == 0.1
    assert res["alert_tier"] == "NORMAL"
    assert res["hours_to_exhaustion"] > 720


def test_error_budget_burn_rate_elevated_page2():
    # 0.8% error rate with 99.9% SLO -> burn_rate = 8.0x
    res = calculate_error_budget_burn_rate(error_rate=0.008, slo_target=0.999)
    assert res["burn_rate"] >= 6.0
    assert res["alert_tier"] == "PAGE_SEVERITY_2"


def test_error_budget_burn_rate_critical_page1():
    # 2.0% error rate with 99.9% SLO -> burn_rate = 20.0x (> 14.4x)
    res = calculate_error_budget_burn_rate(error_rate=0.02, slo_target=0.999)
    assert res["burn_rate"] >= 14.4
    assert res["alert_tier"] == "PAGE_SEVERITY_1"
    assert "CRITICAL_CIRCUIT_BREAK" in res["recommended_action"]


def test_compute_composite_health_score_pass():
    cand_latencies = [18.0, 20.0, 22.0, 19.0, 21.0]
    stab_latencies = [18.5, 19.5, 21.5, 20.0, 20.5]
    res = compute_composite_health_score(cand_latencies, stab_latencies, error_rate=0.001)
    assert res["status"] == "PASS"
    assert res["health_score"] >= 80.0


def test_compute_composite_health_score_fail():
    cand_latencies = [400.0, 450.0, 500.0, 600.0, 700.0]
    stab_latencies = [20.0, 22.0, 21.0, 25.0, 23.0]
    res = compute_composite_health_score(cand_latencies, stab_latencies, error_rate=0.08)
    assert res["status"] == "FAIL"
    assert res["health_score"] < 60.0
