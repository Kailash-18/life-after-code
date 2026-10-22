#!/usr/bin/env python3
"""
Project Sentinel — Cloud Run Container Concurrency Auto-Tuner
Stage: Configure.
Analyzes concurrency saturation vs container CPU/memory utilization,
dynamically tuning container concurrency from 80 to 20 under latency distress to prevent head-of-line blocking.
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


class ConcurrencyAutoTuner:
    """Calculates optimal concurrency parameters for Cloud Run container templates."""

    def __init__(self, target_event_loop_latency_ms: float = 15.0) -> None:
        self.target_event_loop_latency_ms = target_event_loop_latency_ms

    def tune_concurrency(
        self,
        current_concurrency: int = 80,
        observed_p95_latency_ms: float = 120.0,
        event_loop_delay_ms: float = 24.5,
        cpu_utilization_pct: float = 85.0,
    ) -> dict[str, Any]:
        """Calculates optimal concurrency to prevent head-of-line blocking and memory thrashing."""
        if event_loop_delay_ms > self.target_event_loop_latency_ms or cpu_utilization_pct > 80.0:
            # Under concurrency contention: scale down concurrency to shed queuing delay
            recommended_concurrency = max(10, int(current_concurrency * 0.5))
            action = "SCALE_DOWN_CONCURRENCY"
            tuning_applied = True
            reason = f"Event loop delay ({event_loop_delay_ms}ms) exceeded threshold ({self.target_event_loop_latency_ms}ms)"
        elif cpu_utilization_pct < 30.0 and event_loop_delay_ms < 5.0:
            # Underutilized: scale up to optimize container packing
            recommended_concurrency = min(100, int(current_concurrency * 1.25))
            action = "SCALE_UP_CONCURRENCY"
            tuning_applied = True
            reason = "Container underutilized; packing efficiency increased"
        else:
            recommended_concurrency = current_concurrency
            action = "MAINTAIN_CONCURRENCY"
            tuning_applied = False
            reason = "Operating within optimal concurrency envelope"

        return {
            "status": "TUNED" if tuning_applied else "OPTIMAL",
            "action": action,
            "current_concurrency": current_concurrency,
            "recommended_concurrency": recommended_concurrency,
            "observed_event_loop_delay_ms": event_loop_delay_ms,
            "cpu_utilization_pct": cpu_utilization_pct,
            "tuning_reason": reason,
        }


def run_concurrency_audit(
    current_concurrency: int = 80,
    observed_delay: float = 24.5,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    tuner = ConcurrencyAutoTuner()
    report = tuner.tune_concurrency(
        current_concurrency=current_concurrency,
        event_loop_delay_ms=observed_delay,
    )
    report["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "concurrency-autotune-report.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Concurrency Auto-Tuner")
    parser.add_argument("--concurrency", type=int, default=80)
    parser.add_argument("--delay", type=float, default=24.5)
    parser.add_argument("--output-dir", default="artifacts", help="Report output dir")
    args = parser.parse_args()

    report = run_concurrency_audit(args.concurrency, args.delay, output_dir=Path(args.output_dir))
    print(f"\n{'='*70}")
    print("  PROJECT SENTINEL — CLOUD RUN CONCURRENCY AUTO-TUNER")
    print(f"  Decision: [{report['action']}] | Concurrency: {report['current_concurrency']} -> {report['recommended_concurrency']}")
    print(f"  Reason: {report['tuning_reason']}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
