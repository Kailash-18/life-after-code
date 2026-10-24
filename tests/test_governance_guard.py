"""
Unit tests for Sentinel Multi-Cloud Governance Guard.
Validates CIS GCP & AWS Foundations Benchmark compliance scores.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.governance_guard import (
    MultiCloudGovernanceGuard,
    run_governance_audit,
)


def test_governance_guard_nominal_compliance():
    guard = MultiCloudGovernanceGuard(target_compliance_score=90.0)
    report = guard.audit_governance_controls()

    assert report["verdict"] == "COMPLIANT"
    assert report["compliance_score"] >= 90.0
    assert report["controls_audited"] >= 7
    assert report["controls_failed"] == 0


def test_run_governance_audit_artifact(tmp_path: Path):
    report = run_governance_audit(output_dir=tmp_path)
    assert report["verdict"] == "COMPLIANT"
    out_file = tmp_path / "governance-compliance-report.json"
    assert out_file.exists()
    alias_file = tmp_path / "cis-governance-report.json"
    assert alias_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["specification"] == "CIS Multi-Cloud Benchmark v2.0"
