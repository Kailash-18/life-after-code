"""
Unit tests for Sentinel Automated Rollback Controller (Task K6).
Validates 100% traffic diversion to known-good revision, post-rollback health probing,
and report artifact generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from sentinel.scripts.rollback import (
    execute_cloud_run_traffic_shift,
    get_known_good_revision,
    run_post_rollback_probe,
    run_rollback,
)


def test_get_known_good_revision_explicit():
    rev = get_known_good_revision("sentinel-target-app", explicit_revision="rev-known-good-999")
    assert rev == "rev-known-good-999"


def test_get_known_good_revision_from_env(monkeypatch):
    monkeypatch.setenv("SENTINEL_KNOWN_GOOD_REVISION", "rev-env-good-123")
    rev = get_known_good_revision("sentinel-target-app")
    assert rev == "rev-env-good-123"


def test_execute_cloud_run_traffic_shift_simulation():
    res = execute_cloud_run_traffic_shift(
        service_name="sentinel-target-app",
        target_revision="rev-known-good-01",
        dry_run=True,
    )
    assert res["success"] is True
    assert res["revisions"]["rev-known-good-01"] == 100
    assert res["mode"] == "simulation"


def test_run_post_rollback_probe_mock():
    # Mock urllib.request.urlopen to simulate 100% healthy endpoint
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        probe = run_post_rollback_probe("http://localhost:8080", sample_count=5)
        assert probe["probe_ok"] is True
        assert probe["samples"] == 5
        assert probe["successes"] == 5
        assert probe["errors"] == 0
        assert probe["error_rate"] == 0.0


def test_run_rollback_writes_artifact(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        report = run_rollback(
            service_name="sentinel-target-app",
            stable_url="http://localhost:8080",
            known_good_rev="target-app-known-good-01",
            dry_run=True,
            emit_to_backend=False,
        )
        # A dry run is labelled as such and never claims a healthy probe.
        assert report["status"] == "SIMULATED"
        assert report["post_rollback_probe_ok"] is False
        assert report["restored_revision"] == "target-app-known-good-01"

        art_file = tmp_path / "artifacts" / "rollback-report.json"
        assert art_file.exists()
        saved = json.loads(art_file.read_text(encoding="utf-8"))
        assert saved["status"] == "SIMULATED"


def test_real_rollback_needs_traffic_shift_and_probe(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SENTINEL_SIMULATION_MODE", raising=False)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    with patch("urllib.request.urlopen", return_value=mock_resp), patch("time.sleep"):
        with patch("subprocess.check_output", return_value="{}"):
            ok = run_rollback(service_name="svc", stable_url="http://x", known_good_rev="rev-1", emit_to_backend=False)
        assert ok["status"] == "ROLLED_BACK" and ok["post_rollback_probe_ok"] is True
        with patch("subprocess.check_output", side_effect=FileNotFoundError("gcloud")):
            bad = run_rollback(service_name="svc", stable_url="http://x", known_good_rev="rev-1", emit_to_backend=False)
        assert bad["status"] == "ROLLBACK_FAILED" and bad["post_rollback_probe_ok"] is False
