"""
Unit tests for Sentinel Cold Start Primer.
Validates idle threshold detection and priming pulse execution.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.cold_start_primer import (
    ColdStartPrimer,
    run_primer_audit,
)


def test_cold_start_primer_dispatches_when_idle():
    primer = ColdStartPrimer(idle_timeout_sec=870.0)
    res = primer.evaluate_and_prime(last_request_seconds_ago=850.0, warm_instances_count=3)

    assert res["status"] == "PRIMED"
    assert res["priming_pulse_dispatched"] is True
    assert res["instances_kept_warm"] == 3


def test_cold_start_primer_skips_when_active():
    primer = ColdStartPrimer(idle_timeout_sec=870.0)
    res = primer.evaluate_and_prime(last_request_seconds_ago=120.0)

    assert res["status"] == "WARM_ACTIVE"
    assert res["priming_pulse_dispatched"] is False


def test_run_primer_audit_artifact(tmp_path: Path):
    report = run_primer_audit(output_dir=tmp_path)
    assert report["cold_start_mitigated"] is True
    out_file = tmp_path / "cold-start-priming-report.json"
    assert out_file.exists()
