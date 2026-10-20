"""
Tests for Project Sentinel S3 Remote State Storage Subsystem and State API Routes.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.s3_state_store import S3StateStore
from app.state_engine import INCIDENTS_STORE

client = TestClient(app)


def test_snapshot_state_creates_valid_hash_and_payload(tmp_path):
    store = S3StateStore(bucket_name="test-sentinel-state-bucket", region="us-east-1")
    store.local_cache_dir = tmp_path

    sample_incidents = {
        "inc-100": {
            "id": "inc-100",
            "release_id": "rel-v1.0.0",
            "status": "DETECTED",
            "breached_thresholds": ["error_rate_max"],
        }
    }

    res = store.snapshot_state(sample_incidents, extra_metadata={"triggered_by": "test"})
    assert res["status"] == "PASS"
    assert "snapshot_id" in res
    assert len(res["sha256"]) == 64
    assert res["active_incidents"] == 1


def test_restore_snapshot_happy_path(tmp_path):
    store = S3StateStore(bucket_name="test-sentinel-state-bucket", region="us-east-1")
    store.local_cache_dir = tmp_path

    target_incidents = {
        "inc-critical-1": {
            "id": "inc-critical-1",
            "release_id": "rel-v1.2.3",
            "status": "RECOVERED",
        }
    }

    res = store.snapshot_state(target_incidents)
    snapshot_id = res["snapshot_id"]

    # Clear memory
    target_incidents.clear()
    assert len(target_incidents) == 0

    # Restore
    restored = store.restore_snapshot(snapshot_id, target_incidents)
    assert restored["success"] is True
    assert restored["status"] == "RESTORED"
    assert "inc-critical-1" in target_incidents
    assert target_incidents["inc-critical-1"]["status"] == "RECOVERED"


def test_restore_detects_sha256_corruption(tmp_path):
    store = S3StateStore(bucket_name="test-sentinel-state-bucket", region="us-east-1")
    store.local_cache_dir = tmp_path

    initial = {"inc-tamper": {"id": "inc-tamper", "status": "DETECTED"}}
    res = store.snapshot_state(initial)
    snap_id = res["snapshot_id"]

    # Tamper with cached file content without updating sha256
    cache_file = tmp_path / f"{snap_id}.json"
    tampered_data = {
        "snapshot_id": snap_id,
        "sha256": "fake-hash-000000000000000000000000000000000000000000000000000000000000",
        "incidents": {"inc-tamper": {"id": "inc-tamper", "status": "UNAUTHORIZED_EDIT"}},
    }
    import json

    cache_file.write_text(json.dumps(tampered_data), encoding="utf-8")

    mem_store = {}
    restore_res = store.restore_snapshot(snap_id, mem_store)
    assert restore_res["success"] is False
    assert "tampering or corruption detected" in restore_res["error"]


def test_state_api_endpoints():
    # 1. Check storage health
    resp = client.get("/api/v1/state/storage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["storage_type"] == "AWS_S3_REMOTE_STATE"
    assert data["versioning_enabled"] is True

    # 2. Trigger snapshot
    INCIDENTS_STORE["inc-api-test"] = {
        "id": "inc-api-test",
        "release_id": "rel-v1.0.0",
        "status": "DETECTED",
        "breached_thresholds": [],
        "recovery_attempts": [],
    }
    snap_resp = client.post("/api/v1/state/snapshot", json={"metadata": {"test": "api"}})
    assert snap_resp.status_code == 201
    snap_data = snap_resp.json()
    assert snap_data["status"] == "CREATED"
    snap_id = snap_data["snapshot"]["snapshot_id"]

    # 3. List snapshots
    list_resp = client.get("/api/v1/state/snapshots")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1

    # 4. Restore snapshot
    restore_resp = client.post("/api/v1/state/restore", json={"snapshot_id": snap_id})
    assert restore_resp.status_code == 200
    assert restore_resp.json()["success"] is True
