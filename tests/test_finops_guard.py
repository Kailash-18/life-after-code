"""
Unit tests for Sentinel Multi-Cloud FinOps & Carbon Intensity Guard (Task K-FinOps).
Validates multi-cloud cost forecasting, FinOps budget enforcement, and GreenOps carbon metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.finops_guard import CloudFinOpsGuard, evaluate_cloud_finops_guard


def test_finops_cloud_run_cost_estimation():
    guard = CloudFinOpsGuard(monthly_budget_usd=300.0)
    costs = guard.estimate_cloud_run_cost(
        monthly_requests=5_000_000,
        avg_duration_ms=65.0,
        vcpu=1.0,
        memory_gib=0.5,
    )
    assert costs["request_cost_usd"] > 0
    assert costs["vcpu_cost_usd"] > 0
    assert costs["memory_cost_usd"] >= 0.0
    assert costs["total_cloud_run_usd"] > 0

    # Test with higher memory allocation to exceed Cloud Run free tier (360,000 GiB-sec)
    high_mem_costs = guard.estimate_cloud_run_cost(
        monthly_requests=5_000_000,
        avg_duration_ms=65.0,
        vcpu=2.0,
        memory_gib=4.0,
    )
    assert high_mem_costs["memory_cost_usd"] > 0


def test_finops_storage_and_security_cost():
    guard = CloudFinOpsGuard()
    infra_costs = guard.estimate_storage_and_security_cost(
        monthly_requests=5_000_000,
        state_snapshots_stored_gb=20.0,
        monthly_state_mutations=10_000,
    )
    assert infra_costs["cloud_armor_waf_usd"] >= 5.0
    assert infra_costs["s3_remote_state_usd"] > 0
    assert infra_costs["dynamodb_locks_usd"] >= 1.25
    assert infra_costs["total_infra_security_usd"] > 0


def test_finops_carbon_footprint_calculation():
    guard = CloudFinOpsGuard()
    carbon = guard.estimate_carbon_footprint(
        primary_region="us-central1",
        monthly_requests=2_000_000,
        avg_duration_ms=50.0,
        vcpu=1.0,
    )
    assert carbon["region"] == "us-central1"
    assert carbon["regional_grid_intensity_gco2"] == 380.0
    assert carbon["kwh_consumed_monthly"] > 0
    assert carbon["co2_emissions_kg_monthly"] > 0
    assert carbon["green_window_certified"] is True


def test_finops_guard_happy_path_pass():
    guard = CloudFinOpsGuard(monthly_budget_usd=250.0, max_cost_increase_pct=25.0)
    report = guard.evaluate_release_finops(
        candidate_revision="cand-rev-01",
        baseline_revision="stable-rev-01",
        primary_region="us-central1",
        candidate_vcpu=1.0,
        candidate_mem_gib=0.5,
        baseline_vcpu=1.0,
        baseline_mem_gib=0.5,
        monthly_requests=3_000_000,
        candidate_latency_ms=60.0,
        baseline_latency_ms=60.0,
    )
    assert report["verdict"] == "PASS"
    assert report["violations_count"] == 0
    assert report["projected_monthly_spend_usd"] <= 250.0
    assert report["budget_utilization_pct"] < 50.0


def test_finops_guard_budget_breach():
    # Set a tiny budget to verify violation trigger
    guard = CloudFinOpsGuard(monthly_budget_usd=5.0)
    report = guard.evaluate_release_finops(
        candidate_revision="cand-rev-expensive",
        baseline_revision="stable-rev-01",
        monthly_requests=10_000_000,
    )
    assert report["verdict"] == "BUDGET_EXCEEDED"
    assert report["violations_count"] >= 1
    assert any("exceeds maximum FinOps budget" in v for v in report["violations"])


def test_finops_guard_cost_surge_delta_breach():
    # Candidate requires 4x vCPU and 8x RAM compared to baseline
    guard = CloudFinOpsGuard(monthly_budget_usd=1000.0, max_cost_increase_pct=15.0)
    report = guard.evaluate_release_finops(
        candidate_revision="cand-rev-oversized",
        baseline_revision="stable-rev-lean",
        candidate_vcpu=4.0,
        candidate_mem_gib=4.0,
        baseline_vcpu=1.0,
        baseline_mem_gib=0.5,
        monthly_requests=5_000_000,
    )
    assert report["verdict"] == "BUDGET_EXCEEDED"
    assert any("Cost surge" in v for v in report["violations"])


def test_evaluate_cloud_finops_guard_writes_artifact(tmp_path: Path):
    report = evaluate_cloud_finops_guard(
        output_dir=tmp_path,
        emit_to_backend=False,
    )
    assert report["verdict"] == "PASS"
    out_file = tmp_path / "finops-cloud-cost-report.json"
    assert out_file.exists()
    forecast_file = tmp_path / "finops-spend-forecast.json"
    assert forecast_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS"
    assert "cloud_cost_breakdown" in data
    assert "carbon_window_forecast" in data


def test_forecast_carbon_optimal_deployment_window():
    guard = CloudFinOpsGuard()
    forecast = guard.forecast_carbon_optimal_deployment_window("us-central1")

    assert forecast["region"] == "us-central1"
    assert len(forecast["diurnal_24h_forecast"]) == 24
    assert 0 <= forecast["optimal_window_hour_utc"] <= 23
    assert forecast["optimal_window_cfe_pct"] >= 70.0
    assert "recommendation" in forecast
