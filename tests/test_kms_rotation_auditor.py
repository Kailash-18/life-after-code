"""
Unit tests for Sentinel Multi-Cloud KMS Rotation Auditor.
Validates key rotation intervals, envelope encryption status, and violation alerts.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.kms_rotation_auditor import (
    CloudKmsRotationAuditor,
    run_kms_audit,
)


def test_kms_rotation_nominal_pass():
    auditor = CloudKmsRotationAuditor(max_rotation_days=90)
    report = auditor.audit_key_lifecycle()

    assert report["verdict"] == "PASS"
    assert report["envelope_encryption_active"] is True
    assert len(report["violations"]) == 0


def test_kms_rotation_detects_unrotated_key():
    auditor = CloudKmsRotationAuditor(max_rotation_days=90)
    stale_aws_keys = [
        {
            "key_arn": "arn:aws:kms:us-east-1:123456789012:key/stale-key",
            "automatic_rotation_enabled": True,
            "last_rotated_days_ago": 180,
            "state": "Enabled",
        }
    ]
    report = auditor.audit_key_lifecycle(aws_keys=stale_aws_keys)

    assert report["verdict"] == "KMS_ROTATION_BREACH"
    assert len(report["violations"]) > 0


def test_run_kms_audit_artifact(tmp_path: Path):
    report = run_kms_audit(output_dir=tmp_path)
    assert report["verdict"] == "PASS"
    out_file = tmp_path / "kms-rotation-audit-report.json"
    assert out_file.exists()
    alias_file = tmp_path / "kms-rotation-report.json"
    assert alias_file.exists()
