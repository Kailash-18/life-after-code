"""
Unit tests for Sentinel EWMA & CUSUM Adaptive Drift Detector.
Validates sequential change-point detection, recursive moving variance, and early anomaly alerting.
"""

from __future__ import annotations

import pytest

from sentinel.scripts.drift_detector import AdaptiveDriftDetector, run_drift_analysis


def test_drift_detector_stable_stream():
    detector = AdaptiveDriftDetector(baseline_mean=25.0, baseline_std=2.0)
    stable_points = [25.1, 24.8, 25.2, 24.9, 25.0, 25.3, 24.7, 25.1]
    report = detector.evaluate_series(stable_points)

    assert report["drift_detected"] is False
    assert report["verdict"] == "STABLE"
    assert report["total_drift_violations"] == 0


def test_drift_detector_detects_gradual_latency_creep():
    detector = AdaptiveDriftDetector(baseline_mean=25.0, baseline_std=2.0)
    # Slow creeping leak: latency increases by +3ms on each step
    creeping_points = [25.0 + (i * 3.0) for i in range(15)]
    report = detector.evaluate_series(creeping_points)

    assert report["drift_detected"] is True
    assert report["verdict"] == "DRIFT_ALERT_TRIGGERED"
    assert report["first_drift_observation_index"] is not None


def test_run_drift_analysis_wrapper():
    baseline = [20.0, 21.0, 19.5, 20.5, 20.0]
    candidate = [20.1, 20.4, 19.8, 20.2]
    res = run_drift_analysis(baseline, candidate)

    assert res["verdict"] == "STABLE"
    assert res["drift_detected"] is False
