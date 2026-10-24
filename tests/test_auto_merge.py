"""
Unit tests for Sentinel Autonomous Auto-Merge Controller (Task K10).
Validates deterministic gate report verification, blocking on failed gates,
and autonomous merge execution in simulation mode.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.auto_merge import (
    execute_gitlab_merge,
    run_auto_merge,
    verify_gate_reports,
)


def test_verify_gate_reports_all_pass(tmp_path: Path):
    # Setup passing gate reports
    (tmp_path / "integrity-gate-report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")
    (tmp_path / "regression-proof-report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")
    (tmp_path / "sast-report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    res = verify_gate_reports(artifacts_dir=tmp_path)
    assert res["all_passed"] is True
    assert res["gates"]["integrity_gate"] == "PASS"
    assert res["gates"]["regression_proof"] == "PASS"
    assert res["gates"]["sast_gate"] == "PASS"


def test_verify_gate_reports_blocks_on_failing_gate(tmp_path: Path):
    (tmp_path / "integrity-gate-report.json").write_text(json.dumps({"verdict": "FAIL"}), encoding="utf-8")
    (tmp_path / "regression-proof-report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    res = verify_gate_reports(artifacts_dir=tmp_path)
    assert res["all_passed"] is False
    assert res["gates"]["integrity_gate"] == "FAIL"


def test_execute_gitlab_merge_simulation():
    res = execute_gitlab_merge(project_id="sentinel-proj", mr_iid=42, dry_run=True)
    assert res["merged"] is True
    assert res["mode"] == "simulation"
    assert "merge_commit_sha" in res


def test_run_auto_merge_happy_path(tmp_path: Path):
    (tmp_path / "integrity-gate-report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")
    (tmp_path / "regression-proof-report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")
    (tmp_path / "sast-report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")

    report = run_auto_merge(
        project_id="sentinel-proj",
        mr_iid=101,
        fix_sha="c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        artifacts_dir=tmp_path,
        dry_run=True,
        emit_to_backend=False,
    )
    assert report["status"] == "MERGED"
    assert report["mr_iid"] == 101
    assert report["fix_sha"] == "c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


def test_run_auto_merge_raises_on_gate_failure(tmp_path: Path):
    (tmp_path / "integrity-gate-report.json").write_text(json.dumps({"verdict": "FAIL"}), encoding="utf-8")

    with pytest.raises(RuntimeError) as exc_info:
        run_auto_merge(
            project_id="sentinel-proj",
            mr_iid=102,
            fix_sha="deadbeef",
            artifacts_dir=tmp_path,
            dry_run=False,
            emit_to_backend=False,
        )
    assert "Auto-merge blocked!" in str(exc_info.value)
