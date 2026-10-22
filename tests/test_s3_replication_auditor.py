"""
Unit tests for Sentinel S3 Replication Auditor.
Validates zero-RPO cross-region replication synchronization and SHA-256 digest matching.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.s3_replication_auditor import (
    S3ReplicationAuditor,
    run_s3_replication_audit,
)


def test_s3_replication_nominal_pass():
    auditor = S3ReplicationAuditor()
    res = auditor.audit_replication_stream()

    assert res["verdict"] == "PASS"
    assert res["rpo_seconds"] == 0.0
    assert res["cryptographic_integrity_verified"] is True
    assert len(res["violations"]) == 0


def test_s3_replication_detects_checksum_mismatch():
    auditor = S3ReplicationAuditor()
    corrupt_sums = {
        "snap-primary-latest": "aaaa" * 16,
        "snap-replica-latest": "bbbb" * 16,
    }
    res = auditor.audit_replication_stream(snapshot_checksums=corrupt_sums)

    assert res["verdict"] == "REPLICATION_DESYNC"
    assert res["cryptographic_integrity_verified"] is False
    assert len(res["violations"]) > 0


def test_run_s3_replication_audit_artifact(tmp_path: Path):
    report = run_s3_replication_audit(output_dir=tmp_path)
    assert report["verdict"] == "PASS"
    out_file = tmp_path / "s3-replication-sync-report.json"
    assert out_file.exists()
