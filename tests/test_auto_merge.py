"""
Unit tests for the Sentinel auto-merge controller (Task K10).
It may only merge when every required gate report exists and passed, and it never reports
a merge that GitLab did not confirm.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sentinel.scripts.auto_merge import execute_gitlab_merge, run_auto_merge, verify_gate_reports


def _reports(d: Path, integrity="PASS", proof="PROVEN"):
    if integrity is not None:
        (d / "integrity-gate.json").write_text(json.dumps({"verdict": integrity}), encoding="utf-8")
    if proof is not None:
        (d / "regression-proof.json").write_text(json.dumps({"verdict": proof}), encoding="utf-8")


def test_all_required_gates_pass(tmp_path: Path):
    _reports(tmp_path)
    res = verify_gate_reports(tmp_path)
    assert res["all_passed"] is True
    assert res["gates"] == {"integrity_gate": "PASS", "regression_proof": "PROVEN"}


@pytest.mark.parametrize("integrity,proof", [("FAIL", "PROVEN"), ("PASS", "REJECTED"), (None, "PROVEN"), ("PASS", None)])
def test_failed_or_missing_gate_blocks(tmp_path: Path, integrity, proof):
    _reports(tmp_path, integrity, proof)
    assert verify_gate_reports(tmp_path)["all_passed"] is False


def test_env_vars_cannot_stand_in_for_reports(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SENTINEL_INTEGRITY_PASSED", "true")
    monkeypatch.setenv("SENTINEL_PROOF_PASSED", "true")
    assert verify_gate_reports(tmp_path)["all_passed"] is False


def test_dry_run_merges_nothing(tmp_path: Path):
    _reports(tmp_path)
    res = run_auto_merge(project_id="p", mr_iid=101, fix_sha="c7d8e9f", artifacts_dir=tmp_path, dry_run=True, emit_to_backend=False)
    assert res["status"] == "SIMULATED"
    assert execute_gitlab_merge("p", 1, dry_run=True)["merged"] is False


def test_dry_run_still_enforces_gates(tmp_path: Path):
    _reports(tmp_path, integrity="FAIL")
    with pytest.raises(RuntimeError, match="Auto-merge blocked"):
        run_auto_merge(project_id="p", mr_iid=102, fix_sha="deadbee", artifacts_dir=tmp_path, dry_run=True, emit_to_backend=False)


def test_api_failure_is_not_a_merge(tmp_path: Path, monkeypatch):
    _reports(tmp_path)
    monkeypatch.setenv("GITLAB_PROJECT_TOKEN", "glpat-test")
    monkeypatch.delenv("SENTINEL_SIMULATION_MODE", raising=False)
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        with pytest.raises(RuntimeError, match="Merge did not happen"):
            run_auto_merge(project_id="p", mr_iid=103, fix_sha="deadbee", artifacts_dir=tmp_path, emit_to_backend=False)


def test_confirmed_merge_uses_gitlab_sha(tmp_path: Path, monkeypatch):
    _reports(tmp_path)
    monkeypatch.setenv("GITLAB_PROJECT_TOKEN", "glpat-test")
    monkeypatch.delenv("SENTINEL_SIMULATION_MODE", raising=False)
    resp = MagicMock()
    resp.read.return_value = json.dumps({"state": "merged", "merge_commit_sha": "abc1234def"}).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = None
    with patch("urllib.request.urlopen", return_value=resp):
        res = run_auto_merge(project_id="p", mr_iid=104, fix_sha="deadbee", artifacts_dir=tmp_path, emit_to_backend=False)
    assert res["status"] == "MERGED"
    assert res["merge_res"]["merge_commit_sha"] == "abc1234def"
