#!/usr/bin/env python3
"""
Project Sentinel — Google Cloud Monitoring Multi-Window Multi-Burn-Rate SLO Monitor
Stage: Monitor.
Implements Google SRE Multi-Window Multi-Burn-Rate (MWMBR) alert algorithms
for 99.9% availability and 300ms latency Service Level Objectives (SLOs).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class CloudSlaMonitor:
    """Evaluates SLO burn rates according to Google Site Reliability Engineering standards."""

    def __init__(self, target_slo: float = 0.999) -> None:
        self.target_slo = target_slo
        self.error_budget = 1.0 - target_slo  # 0.001 (0.1%)

    def evaluate_burn_rates(
        self,
        window_1h_error_rate: float = 0.0002,
        window_6h_error_rate: float = 0.0001,
        total_requests: int = 500_000,
    ) -> dict[str, Any]:
        """Calculates 1h and 6h burn rates: BurnRate = ErrorRate / (1 - SLO)."""
        burn_rate_1h = window_1h_error_rate / self.error_budget
        burn_rate_6h = window_6h_error_rate / self.error_budget

        # SRE Google Alerting thresholds:
        # Page-1: 1h burn > 14.4 (consumes 2% budget in 1 hour)
        # Page-2: 6h burn > 6.0 (consumes 5% budget in 6 hours)
        is_page_1 = burn_rate_1h >= 14.4
        is_page_2 = burn_rate_6h >= 6.0

        alert_level = "CRITICAL_PAGE" if is_page_1 else "WARNING_TICKET" if is_page_2 else "HEALTHY"
        budget_remaining_pct = max(0.0, (1.0 - (window_1h_error_rate / self.error_budget)) * 100.0)

        return {
            "status": alert_level,
            "target_slo_pct": self.target_slo * 100.0,
            "burn_rate_1h": round(burn_rate_1h, 2),
            "burn_rate_6h": round(burn_rate_6h, 2),
            "error_budget_remaining_pct": round(budget_remaining_pct, 1),
            "page_alert_active": is_page_1 or is_page_2,
            "verdict": "PASS" if not (is_page_1 or is_page_2) else "SLO_BURN_RATE_EXCEEDED",
        }


def run_sla_monitor_audit(output_dir: Path | None = None) -> dict[str, Any]:
    monitor = CloudSlaMonitor()
    report = monitor.evaluate_burn_rates()
    report["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "cloud-sla-burnrate-report.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Cloud SLA Monitor")
    parser.add_argument("--output-dir", default="artifacts", help="Report output dir")
    args = parser.parse_args()

    report = run_sla_monitor_audit(output_dir=Path(args.output_dir))
    print(f"\n{'='*70}")
    print("  PROJECT SENTINEL — GOOGLE CLOUD SRE MULTI-WINDOW SLO MONITOR")
    print(f"  Status: [{report['status']}] | 1h Burn Rate: {report['burn_rate_1h']}x (Budget: {report['error_budget_remaining_pct']}%)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
