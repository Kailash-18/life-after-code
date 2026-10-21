"""
Unit tests for Sentinel Concurrency Auto-Tuner.
Validates dynamic container concurrency shedding and packing adjustments.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.concurrency_autotuner import (
    ConcurrencyAutoTuner,
    run_concurrency_audit,
)


def test_concurrency_tuner_sheds_load_under_delay():
    tuner = ConcurrencyAutoTuner(target_event_loop_latency_ms=15.0)
    res = tuner.tune_concurrency(current_concurrency=80, event_loop_delay_ms=30.0, cpu_utilization_pct=90.0)

    assert res["status"] == "TUNED"
    assert res["action"] == "SCALE_DOWN_CONCURRENCY"
    assert res["recommended_concurrency"] == 40


def test_concurrency_tuner_scales_up_when_underutilized():
    tuner = ConcurrencyAutoTuner(target_event_loop_latency_ms=15.0)
    res = tuner.tune_concurrency(current_concurrency=40, event_loop_delay_ms=2.0, cpu_utilization_pct=20.0)

    assert res["status"] == "TUNED"
    assert res["action"] == "SCALE_UP_CONCURRENCY"
    assert res["recommended_concurrency"] == 50


def test_run_concurrency_audit_artifact(tmp_path: Path):
    report = run_concurrency_audit(output_dir=tmp_path)
    assert report["status"] in ("TUNED", "OPTIMAL")
    out_file = tmp_path / "concurrency-autotune-report.json"
    assert out_file.exists()
