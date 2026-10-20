"""
Tests for Project Sentinel S3 State Manager & DynamoDB Lock CLI Utility.
"""

from pathlib import Path
from sentinel.scripts.s3_state_manager import S3StateManager


def test_s3_state_audit():
    mgr = S3StateManager()
    audit = mgr.bootstrap_audit()
    assert audit["status"] == "PASS"
    assert audit["checks"]["versioning_enabled"] is True
    assert audit["checks"]["sse_kms_enforced"] is True
    assert audit["checks"]["public_access_blocked"] is True
    assert audit["checks"]["tls_1_2_enforced"] is True


def test_s3_snapshot_and_cryptographic_verification(tmp_path):
    mgr = S3StateManager()
    test_state = {"cluster": "cloud-run-mesh", "instances": 3, "healthy": True}
    res = mgr.snapshot_state_file(test_state)
    assert res["status"] == "PASS"
    snap_id = res["snapshot_id"]

    # Verify integrity
    verify_res = mgr.verify_state_integrity(snap_id)
    assert verify_res["status"] == "PASS"
    assert verify_res["valid"] is True
    assert verify_res["expected_sha256"] == verify_res["computed_sha256"]


def test_dynamodb_lock_probe():
    mgr = S3StateManager()
    locks = mgr.check_dynamodb_lock()
    assert "table_name" in locks
    assert locks["status"] in ("UNLOCKED", "LOCKED")


def test_dr_cross_region_replication():
    mgr = S3StateManager()
    rep = mgr.dr_cross_region_replication()
    assert rep["status"] == "PASS"
    assert rep["rpo_seconds"] == 0.0
    assert rep["sha256_checksum_matched"] is True
