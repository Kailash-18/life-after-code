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


def test_disaster_recovery_failback_reinstatement():
    orchestrator = DisasterRecoveryOrchestrator(primary_region="us-central1", secondary_region="us-east1")
    # First simulate failover to secondary
    failover_report = orchestrator.simulate_regional_outage_and_failover()
    assert failover_report["active_region_post_failover"] == "us-east1"

    # Then execute failback reinstatement to primary
    reinstatement_report = orchestrator.reinstate_primary_region()
    assert reinstatement_report["status"] == "PASS"
    assert reinstatement_report["action"] == "FAILBACK_REINSTATEMENT"
    assert reinstatement_report["active_region_post_reinstatement"] == "us-central1"
    assert reinstatement_report["recovery_metrics"]["rto_seconds"] <= 5.0
    assert reinstatement_report["recovery_metrics"]["rpo_seconds"] == 0.0
    assert len(reinstatement_report["audit_trail"]) >= 7


def test_disaster_recovery_custom_regions():
    orchestrator = DisasterRecoveryOrchestrator(primary_region="europe-west1", secondary_region="europe-west4")
    report = orchestrator.simulate_regional_outage_and_failover(outage_type="dns_anycast_blackhole")

    assert report["primary_region"] == "europe-west1"
    assert report["secondary_region"] == "europe-west4"
    assert report["disaster_type"] == "dns_anycast_blackhole"
    assert report["active_region_post_failover"] == "europe-west4"
    assert report["status"] == "PASS"
