"""
Unit tests for Sentinel Cloud Region Evacuator.
Validates zero-loss traffic draining and failover state transitions.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.cloud_region_evacuator import (
    CloudRegionEvacuator,
    run_evacuation_audit,
)


def test_cloud_region_evacuation_happy_path():
    evacuator = CloudRegionEvacuator()
    report = evacuator.evacuate_region("us-central1", "us-east1")

    assert report["status"] == "EVACUATED"
    assert report["traffic_allocation"]["us-central1"] == 0
    assert report["traffic_allocation"]["us-east1"] == 100
    assert report["zero_data_loss_verified"] is True
    assert len(report["audit_trail"]) >= 4


def test_run_evacuation_audit_artifact(tmp_path: Path):
    report = run_evacuation_audit(output_dir=tmp_path)
    assert report["status"] == "EVACUATED"
    out_file = tmp_path / "cloud-region-evacuation-report.json"
    assert out_file.exists()


def test_cloud_region_reinstatement_happy_path():
    evacuator = CloudRegionEvacuator()
    report = evacuator.reinstate_region("us-central1", "us-east1")

    assert report["status"] == "REINSTATED"
    assert report["final_traffic_allocation"]["us-central1"] == 100
    assert report["final_traffic_allocation"]["us-east1"] == 0
    assert len(report["ramp_steps_executed"]) == 3
    assert report["thundering_herd_guard"] == "ACTIVE"


def test_probe_regional_health_evaluates_correctly():
    evacuator = CloudRegionEvacuator()
    healthy = evacuator.probe_regional_health("us-central1", simulated_latency_ms=45.0, simulated_error_rate=0.0)
    assert healthy["healthy"] is True
    assert healthy["recommendation"] == "STABLE"

    degraded = evacuator.probe_regional_health("us-central1", simulated_latency_ms=220.0, simulated_error_rate=0.08)
    assert degraded["healthy"] is False
    assert degraded["recommendation"] == "EVACUATE_IMMEDIATELY"
