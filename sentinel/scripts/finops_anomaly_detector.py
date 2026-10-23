#!/usr/bin/env python3
"""
Project Sentinel — Multi-Cloud Cost Anomaly & Z-Score Spike Predictor
Stage: Plan / Govern.
Detects runaway billing trends across Google Cloud Run and AWS S3 State infrastructure
using rolling statistical moving averages, Z-scores, and Interquartile Range (IQR).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class CloudCostAnomalyDetector:
    """Evaluates multi-day cloud spend samples and predicts billing runaway spikes."""

    def __init__(self, z_score_threshold: float = 2.5, iqr_multiplier: float = 1.5) -> None:
        self.z_score_threshold = z_score_threshold
        self.iqr_multiplier = iqr_multiplier

    def analyze_spend_series(
        self,
        historical_daily_spend: list[float],
        current_daily_spend: float,
    ) -> dict[str, Any]:
        """Calculates Z-score and IQR bounds to flag abnormal financial anomalies."""
        if len(historical_daily_spend) < 3:
            return {
                "status": "INSUFFICIENT_HISTORY",
                "is_anomaly": False,
                "current_spend": current_daily_spend,
                "recommendation": "Collect at least 3 historical billing checkpoints",
            }

        n = len(historical_daily_spend)
        mean_spend = sum(historical_daily_spend) / n
        variance = sum((x - mean_spend) ** 2 for x in historical_daily_spend) / (n - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.001

        # Z-score of current spend
        z_score = (current_daily_spend - mean_spend) / std_dev

        # IQR Anomaly Bounds
        sorted_spend = sorted(historical_daily_spend)
        q1 = sorted_spend[int(n * 0.25)]
        q3 = sorted_spend[int(n * 0.75)]
        iqr = q3 - q1
        upper_bound = q3 + (self.iqr_multiplier * iqr)

        is_z_anomaly = z_score > self.z_score_threshold
        is_iqr_anomaly = current_daily_spend > upper_bound
        is_anomaly = is_z_anomaly or is_iqr_anomaly

        severity = "CRITICAL" if z_score > 3.5 else "HIGH" if is_anomaly else "NORMAL"

        return {
            "status": "ALERT" if is_anomaly else "NORMAL",
            "is_anomaly": is_anomaly,
            "severity": severity,
            "current_spend_usd": round(current_daily_spend, 2),
            "historical_mean_usd": round(mean_spend, 2),
            "std_dev_usd": round(std_dev, 2),
            "z_score": round(z_score, 2),
            "upper_fence_iqr_usd": round(upper_bound, 2),
            "alert_message": (
                f"Cloud spend anomaly detected! Current (${current_daily_spend}) is {z_score:.1f}σ above 7-day mean (${mean_spend:.2f})"
                if is_anomaly
                else "Cloud spend metrics within normal statistical distribution"
            ),
        }


def run_cost_anomaly_audit(
    historical_spend: list[float] | None = None,
    current_spend: float = 18.50,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    if historical_spend is None:
        historical_spend = [12.40, 11.80, 12.10, 13.00, 12.50, 12.20, 12.60]

    detector = CloudCostAnomalyDetector()
    report = detector.analyze_spend_series(historical_spend, current_spend)
    report["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "finops-cost-anomaly-report.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Multi-Cloud Cost Anomaly Detector")
    parser.add_argument("--current-spend", type=float, default=18.50, help="Observed daily spend")
    parser.add_argument("--output-dir", default="artifacts", help="Report output dir")
    args = parser.parse_args()

    report = run_cost_anomaly_audit(current_spend=args.current_spend, output_dir=Path(args.output_dir))
    print(f"\n{'='*65}")
    print("  PROJECT SENTINEL — FINOPS COST ANOMALY DETECTOR")
    print(f"  Decision: [{report['status']}] | Severity: {report['severity']}")
    print(f"  Current Spend: ${report['current_spend_usd']} | Mean: ${report['historical_mean_usd']} (Z={report['z_score']}σ)")
    print(f"  Diagnosis: {report['alert_message']}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
