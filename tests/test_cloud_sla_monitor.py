"""
Unit tests for Sentinel Cloud SLA Monitor.
Validates Google SRE multi-window multi-burn-rate algorithms and budget alerts.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.cloud_sla_monitor import (
    CloudSlaMonitor,
    run_sla_monitor_audit,
)


def test_sla_monitor_nominal_healthy():
    monitor = CloudSlaMonitor(target_slo=0.999)
    res = monitor.evaluate_burn_rates(window_1h_error_rate=0.0001, window_6h_error_rate=0.00005)

    assert res["status"] == "HEALTHY"
    assert res["verdict"] == "PASS"
    assert res["page_alert_active"] is False


def test_sla_monitor_triggers_page_on_high_burn():
    monitor = CloudSlaMonitor(target_slo=0.999)
    # Error rate 0.02 (20x budget)
    res = monitor.evaluate_burn_rates(window_1h_error_rate=0.02, window_6h_error_rate=0.01)

    assert res["status"] == "CRITICAL_PAGE"
    assert res["verdict"] == "SLO_BURN_RATE_EXCEEDED"
    assert res["burn_rate_1h"] >= 14.4
    assert res["page_alert_active"] is True


def test_run_sla_monitor_audit_artifact(tmp_path: Path):
    report = run_sla_monitor_audit(output_dir=tmp_path)
    assert report["verdict"] == "PASS"
    out_file = tmp_path / "cloud-sla-burnrate-report.json"
    assert out_file.exists()
