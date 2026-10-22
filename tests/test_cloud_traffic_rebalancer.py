"""
Unit tests for Sentinel Multi-Region Cloud Resilience & Dynamic Traffic Rebalancer.
Validates cross-region serverless traffic steering, container pre-warming, and latency-based shedding.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.cloud_traffic_rebalancer import (
    CloudTrafficRebalancer,
    RegionalEndpoint,
    run_traffic_rebalancer,
)


def test_probe_regional_endpoints_nominal():
    rebalancer = CloudTrafficRebalancer(dry_run=True)
    endpoints = rebalancer.probe_regional_endpoints()

    assert len(endpoints) == 2
    primary = next(e for e in endpoints if e.region == "us-central1")
    secondary = next(e for e in endpoints if e.region == "us-east1")

    assert primary.current_weight_pct == 90
    assert secondary.current_weight_pct == 10
    assert primary.p99_latency_ms < 100.0
    assert primary.health_score == 100.0


def test_pre_warm_secondary_pool():
    rebalancer = CloudTrafficRebalancer(dry_run=True)
    warm_report = rebalancer.pre_warm_secondary_pool(region="us-east1", target_instances=4)

    assert warm_report["status"] == "WARMED"
    assert warm_report["region"] == "us-east1"
    assert warm_report["target_instances_primed"] == 4
    assert warm_report["cold_start_risk_mitigated"] is True
    assert len(warm_report["audit_trail"]) >= 3


def test_compute_adaptive_traffic_split_nominal():
    rebalancer = CloudTrafficRebalancer(dry_run=True)
    endpoints = [
        RegionalEndpoint("svc-central", "us-central1", "https://c.run.app", 90, p99_latency_ms=45.0, error_rate=0.0),
        RegionalEndpoint("svc-east", "us-east1", "https://e.run.app", 10, p99_latency_ms=42.0, error_rate=0.0),
    ]
    analysis = rebalancer.compute_adaptive_traffic_split(endpoints)

    assert analysis["degradation_detected"] is False
    assert analysis["action"] == "MAINTAIN_NOMINAL_SPLIT"
    assert analysis["recommended_allocation"]["us-central1"] == 90
    assert analysis["recommended_allocation"]["us-east1"] == 10


def test_compute_adaptive_traffic_split_latency_breach():
    # Primary region experiences latency degradation (> 180ms SLA)
    rebalancer = CloudTrafficRebalancer(dry_run=True)
    endpoints = [
        RegionalEndpoint("svc-central", "us-central1", "https://c.run.app", 90, p99_latency_ms=220.0, error_rate=0.0),
        RegionalEndpoint("svc-east", "us-east1", "https://e.run.app", 10, p99_latency_ms=45.0, error_rate=0.0),
    ]
    analysis = rebalancer.compute_adaptive_traffic_split(endpoints)

    assert analysis["degradation_detected"] is True
    assert analysis["rebalance_required"] is True
    assert analysis["action"] == "PROPORTIONAL_LATENCY_OFFLOAD"
    assert analysis["recommended_allocation"]["us-central1"] == 40
    assert analysis["recommended_allocation"]["us-east1"] == 60


def test_compute_adaptive_traffic_split_severe_error_evacuation():
    # Primary region experiences total outage / high error rate
    rebalancer = CloudTrafficRebalancer(dry_run=True)
    endpoints = [
        RegionalEndpoint("svc-central", "us-central1", "https://c.run.app", 90, p99_latency_ms=500.0, error_rate=0.85),
        RegionalEndpoint("svc-east", "us-east1", "https://e.run.app", 10, p99_latency_ms=45.0, error_rate=0.0),
    ]
    analysis = rebalancer.compute_adaptive_traffic_split(endpoints)

    assert analysis["degradation_detected"] is True
    assert analysis["rebalance_required"] is True
    assert analysis["action"] == "FULL_REGIONAL_EVACUATION"
    assert analysis["recommended_allocation"]["us-central1"] == 0
    assert analysis["recommended_allocation"]["us-east1"] == 100


def test_apply_traffic_split_simulation():
    rebalancer = CloudTrafficRebalancer(dry_run=True)
    res = rebalancer.apply_traffic_split({"us-central1": 50, "us-east1": 50})

    assert res["status"] == "SUCCESS"
    assert res["applied_weights"] == {"us-central1": 50, "us-east1": 50}
    assert res["execution_mode"] == "SIMULATION"
    assert len(res["audit_trail"]) == 2


def test_run_traffic_rebalancer_writes_artifact(tmp_path: Path):
    report = run_traffic_rebalancer(
        primary_latency_ms=250.0,
        output_dir=tmp_path,
        dry_run=True,
        emit_to_backend=False,
    )

    assert report["status"] == "PASS"
    assert report["analysis"]["rebalance_required"] is True
    assert report["pre_warm"] is not None

    artifact_file = tmp_path / "cloud-traffic-rebalance-report.json"
    assert artifact_file.exists()
    data = json.loads(artifact_file.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["analysis"]["action"] == "PROPORTIONAL_LATENCY_OFFLOAD"
