"""
Unit tests for Sentinel Shadow Traffic Replay Engine (Tier 2 Feature 7).
Verifies that failing incident traffic is replayed against candidate fixes,
proving baseline failure (100% errors) is eliminated on candidate fix (100% success).
"""

from __future__ import annotations

from pathlib import Path
import pytest
from sentinel.scripts.shadow_replay import ShadowReplayEngine, run_shadow_replay


def test_shadow_replay_engine_simulation():
    engine = ShadowReplayEngine(service_name="sentinel-target-app")
    report = engine.run_replay(
        incident_id="inc-test-01",
        candidate_revision="cand-003",
        sample_multiplier=2,
    )

    assert report["verdict"] == "PASS"
    assert report["summary"]["total_replayed_requests"] == 10
    assert report["summary"]["baseline_failures"] == 10
    assert report["summary"]["baseline_error_rate_pct"] == 100.0
    assert report["summary"]["candidate_failures"] == 0
    assert report["summary"]["candidate_error_rate_pct"] == 0.0
    assert report["summary"]["shadow_parity_score_pct"] == 100.0
    assert len(report["replayed_samples"]) > 0

    sample = report["replayed_samples"][0]
    assert sample["baseline_status"] == 500
    assert sample["candidate_status"] == 200
    assert sample["mitigated"] is True


def test_shadow_replay_artifact_generation(tmp_path: Path):
    report = run_shadow_replay(
        incident_id="inc-test-02",
        candidate_revision="cand-003",
        sample_count=20,
        emit_to_backend=False,
        output_dir=tmp_path,
    )

    assert (tmp_path / "shadow-replay-report.json").exists()
    assert report["verdict"] == "PASS"
