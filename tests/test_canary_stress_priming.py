"""
Unit tests for Sentinel Canary Stress Priming Engine.
Validates stepped concurrency simulation and latency threshold certifications.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.canary_stress_priming import (
    CanaryStressPrimer,
    run_stress_priming_audit,
)


def test_stress_priming_nominal_pass():
    primer = CanaryStressPrimer(max_concurrency=30)
    report = primer.execute_stress_profile(total_probes=90, concurrency_levels=[5, 15, 30])

    assert report["verdict"] == "PASS"
    assert report["peak_concurrency_tested"] == 30
    assert report["p99_latency_ms"] < 200.0
    assert len(report["stepped_concurrency_tiers"]) == 3


def test_run_stress_priming_audit_artifact(tmp_path: Path):
    report = run_stress_priming_audit(output_dir=tmp_path)
    assert report["verdict"] == "PASS"
    out_file = tmp_path / "canary-stress-priming-report.json"
    assert out_file.exists()
