"""
Unit tests for Sentinel Container Runtime Security Guard.
Validates zero-trust container execution parameters (non-root, read-only root, dropped capabilities).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.container_runtime_guard import (
    ContainerRuntimeGuard,
    run_container_guard_audit,
)


def test_container_guard_nominal_pass():
    guard = ContainerRuntimeGuard()
    res = guard.audit_container_manifest()

    assert res["verdict"] == "PASS"
    assert res["zero_trust_runtime_certified"] is True
    assert len(res["violations"]) == 0


def test_container_guard_detects_root_execution():
    guard = ContainerRuntimeGuard()
    bad_ctx = {
        "runAsNonRoot": False,
        "readOnlyRootFilesystem": True,
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
    }
    res = guard.audit_container_manifest(bad_ctx)

    assert res["verdict"] == "PRIVILEGE_VIOLATION"
    assert any("non-root" in v for v in res["violations"])


def test_run_container_guard_artifact(tmp_path: Path):
    report = run_container_guard_audit(output_dir=tmp_path)
    assert report["verdict"] == "PASS"
    out_file = tmp_path / "container-runtime-security-report.json"
    assert out_file.exists()
