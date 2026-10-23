"""
Unit tests for Sentinel Multi-Cloud Cost Anomaly Detector.
Validates statistical Z-score and IQR runaway spend detection.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.finops_anomaly_detector import (
    CloudCostAnomalyDetector,
    run_cost_anomaly_audit,
)


def test_anomaly_detector_nominal_stable():
    detector = CloudCostAnomalyDetector()
    history = [10.0, 10.5, 9.8, 10.2, 10.1, 10.4, 9.9]
    res = detector.analyze_spend_series(history, current_daily_spend=10.3)

    assert res["status"] == "NORMAL"
    assert res["is_anomaly"] is False
    assert res["severity"] == "NORMAL"
    assert abs(res["z_score"]) < 2.0


def test_anomaly_detector_detects_cost_surge():
    detector = CloudCostAnomalyDetector(z_score_threshold=2.5)
    history = [10.0, 10.5, 9.8, 10.2, 10.1, 10.4, 9.9]
    # Huge spike to $45.00
    res = detector.analyze_spend_series(history, current_daily_spend=45.0)

    assert res["status"] == "ALERT"
    assert res["is_anomaly"] is True
    assert res["z_score"] > 3.0
    assert "anomaly detected" in res["alert_message"]


def test_anomaly_detector_short_history():
    detector = CloudCostAnomalyDetector()
    res = detector.analyze_spend_series([10.0, 12.0], current_daily_spend=15.0)
    assert res["status"] == "INSUFFICIENT_HISTORY"


def test_run_cost_anomaly_audit_artifact(tmp_path: Path):
    report = run_cost_anomaly_audit(output_dir=tmp_path)
    assert report["status"] in ("NORMAL", "ALERT")
    out_file = tmp_path / "finops-cost-anomaly-report.json"
    assert out_file.exists()
