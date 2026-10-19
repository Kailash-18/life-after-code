#!/usr/bin/env python3
"""
Project Sentinel — Statistical EWMA & CUSUM Adaptive Drift Detector
Principal SRE Tier: Implements Exponentially Weighted Moving Average (EWMA)
and Cumulative Sum (CUSUM) change-point detection algorithms.
Identifies insidious micro-regressions and slow-bleed latency creep (e.g. +2ms per 1k requests)
before hard static SLO thresholds are breached.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AdaptiveDriftDetector:
    """
    Two-sided CUSUM and EWMA quality control engine for continuous production telemetry.
    Detects statistically significant mean shifts and trend changes in latency/error streams.
    """

    def __init__(
        self,
        baseline_mean: float = 25.0,
        baseline_std: float = 5.0,
        ewma_alpha: float = 0.2,
        cusum_k: float = 0.5,  # Slack parameter (half the shift to detect in std units)
        cusum_h: float = 4.0,  # Decision interval threshold in std units
    ):
        self.baseline_mean = baseline_mean
        self.baseline_std = max(0.1, baseline_std)
        self.ewma_alpha = ewma_alpha
        self.cusum_k = cusum_k * self.baseline_std
        self.cusum_h = cusum_h * self.baseline_std

        self.current_ewma = baseline_mean
        self.s_high = 0.0  # Upper CUSUM statistic
        self.s_low = 0.0   # Lower CUSUM statistic
        self.history: list[dict[str, Any]] = []

    def update(self, observed_val: float) -> dict[str, Any]:
        """Processes a new telemetry observation and updates EWMA and CUSUM state."""
        # 1. Update EWMA
        self.current_ewma = (self.ewma_alpha * observed_val) + ((1.0 - self.ewma_alpha) * self.current_ewma)

        # 2. Update Two-Sided CUSUM
        # S_H[t] = max(0, S_H[t-1] + (X[t] - mu - K))
        self.s_high = max(0.0, self.s_high + (observed_val - self.baseline_mean - self.cusum_k))
        # S_L[t] = max(0, S_L[t-1] - (X[t] - mu + K))
        self.s_low = max(0.0, self.s_low - (observed_val - self.baseline_mean + self.cusum_k))

        is_high_drift = self.s_high > self.cusum_h
        is_low_drift = self.s_low > self.cusum_h
        drift_detected = is_high_drift or is_low_drift

        status = "NOMINAL"
        if is_high_drift:
            status = "UPWARD_LATENCY_CREEP_DETECTED"
        elif is_low_drift:
            status = "SIGNIFICANT_IMPROVEMENT"

        step_record = {
            "observed": round(observed_val, 2),
            "ewma": round(self.current_ewma, 2),
            "cusum_upper": round(self.s_high, 2),
            "cusum_lower": round(self.s_low, 2),
            "threshold": round(self.cusum_h, 2),
            "drift_detected": drift_detected,
            "status": status,
        }
        self.history.append(step_record)
        return step_record

    def evaluate_series(self, data_points: list[float]) -> dict[str, Any]:
        """Evaluates an entire time-series for insidious drift."""
        for pt in data_points:
            self.update(pt)

        drift_points = [i for i, step in enumerate(self.history) if step["drift_detected"]]
        first_drift_index = drift_points[0] if drift_points else None

        final_status = "STABLE"
        if drift_points:
            final_status = "DRIFT_ALERT_TRIGGERED"

        return {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "series_length": len(data_points),
            "baseline_mean": self.baseline_mean,
            "baseline_std": self.baseline_std,
            "final_ewma": round(self.current_ewma, 2),
            "cusum_threshold": round(self.cusum_h, 2),
            "drift_detected": len(drift_points) > 0,
            "first_drift_observation_index": first_drift_index,
            "total_drift_violations": len(drift_points),
            "verdict": final_status,
            "history": self.history,
        }


def run_drift_analysis(
    baseline: list[float],
    candidate: list[float],
    output_path: str = "artifacts/drift-analysis-report.json",
) -> dict[str, Any]:
    """Computes baseline statistics and evaluates candidate stream for drift."""
    if not baseline:
        baseline = [24.0, 25.0, 26.0, 24.5, 25.5]
    mean = sum(baseline) / len(baseline)
    variance = sum((x - mean) ** 2 for x in baseline) / max(1, len(baseline) - 1)
    std = math.sqrt(variance)

    detector = AdaptiveDriftDetector(baseline_mean=mean, baseline_std=std)
    report = detector.evaluate_series(candidate)

    out = Path(output_path)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel Statistical Adaptive Drift Detector")
    parser.add_argument("--simulate-leak", action="store_true", help="Simulate insidious memory leak / latency creep")
    args = parser.parse_args()

    base = [25.0 + (i % 3) for i in range(20)]
    if args.simulate_leak:
        # Gradually increase by 2ms every 5 steps
        cand = [25.0 + (i * 1.8) for i in range(25)]
    else:
        cand = [25.0 + (i % 4) for i in range(25)]

    res = run_drift_analysis(base, cand)
    print(f"Drift Analysis Complete: Verdict={res['verdict']} | Drift Detected={res['drift_detected']} | Violations={res['total_drift_violations']}")
