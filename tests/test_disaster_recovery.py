"""
Unit tests for Sentinel Multi-Region Disaster Recovery Orchestrator.
Validates zero-RPO and sub-5s-RTO failover across Cloud Run regions.
"""

from __future__ import annotations

import pytest

from sentinel.scripts.disaster_recovery import DisasterRecoveryOrchestrator


def test_disaster_recovery_simulation_rto_rpo():
    orchestrator = DisasterRecoveryOrchestrator(primary_region="us-central1", secondary_region="us-east1")
    report = orchestrator.simulate_regional_outage_and_failover()

    assert report["status"] == "PASS"
    assert report["active_region_post_failover"] == "us-east1"
    assert report["recovery_metrics"]["rto_seconds"] <= 5.0
    assert report["recovery_metrics"]["rto_sla_satisfied"] is True
    assert report["recovery_metrics"]["rpo_seconds"] == 0.0
    assert report["recovery_metrics"]["rpo_sla_satisfied"] is True
    assert len(report["audit_trail"]) >= 4
