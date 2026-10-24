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


def _signed_post(path, body):
    """State write endpoints require the CI HMAC signature (same scheme as /events)."""
    import json
    from datetime import UTC, datetime

    from app.config import settings
    from tests.conftest import generate_signature

    now = datetime.now(UTC).isoformat()
    raw = json.dumps({**body, "sent_at": now}).encode()
    return client.post(path, content=raw, headers={
        "Content-Type": "application/json",
        "X-Sentinel-Signature": generate_signature(settings.hmac_secret, raw),
        "X-Sentinel-Timestamp": now,
    })


def test_state_write_endpoints_reject_unsigned_requests():
    for path, body in [("/api/v1/state/snapshot", {"metadata": {}}),
                       ("/api/v1/state/restore", {"snapshot_id": "snap-x"}),
                       ("/api/v1/state/rollback", {"dry_run": True})]:
        resp = client.post(path, json=body)
        assert resp.status_code == 401, path
        assert resp.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_state_api_endpoints():
    from app.models.entities import Incident
    from app.persistence.factory import get_repository

    # 1. Storage status reports what is real: no S3 here, so local cache only.
    resp = client.get("/api/v1/state/storage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["storage_type"] == "LOCAL_CACHE_ONLY"
    assert data["s3_connected"] is False
    assert data["versioning_enabled"] is None
    assert data["durable_across_restarts"] is False

    # 2. Snapshot contains the incidents actually stored in the repository.
    repo = get_repository()
    repo.clear()
    repo.save_incident(Incident(id="inc-api-test", release_id="rel-v1.0.0", breached_thresholds=["x"]))
    snap_resp = _signed_post("/api/v1/state/snapshot", {"metadata": {"test": "api"}})
    assert snap_resp.status_code == 201
    snap_data = snap_resp.json()
    assert snap_data["status"] == "CREATED"
    assert snap_data["snapshot"]["active_incidents"] == 1
    snap_id = snap_data["snapshot"]["snapshot_id"]

    # 3. List snapshots
    list_resp = client.get("/api/v1/state/snapshots")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    # 4. Restore really writes the incidents back into the repository.
    repo.clear()
    assert client.get("/api/v1/incidents/inc-api-test").status_code == 404
    restore_resp = _signed_post("/api/v1/state/restore", {"snapshot_id": snap_id})
    assert restore_resp.status_code == 200
    assert restore_resp.json()["success"] is True
    assert restore_resp.json()["restored_incidents_count"] == 1
    assert client.get("/api/v1/incidents/inc-api-test").json()["status"] == "DETECTED"

    # 5. Rollback to snapshot (dry run): state restored, but no traffic was moved,
    #    so the API must not claim a successful traffic shift.
    rollback_resp = _signed_post("/api/v1/state/rollback", {"snapshot_id": snap_id, "dry_run": True})
    assert rollback_resp.status_code == 200
    rb_data = rollback_resp.json()
    assert rb_data["snapshot_id"] == snap_id
    assert rb_data["snapshot_integrity_verified"] is True
    assert rb_data["restored_incidents"] == 1
    assert rb_data["traffic_shift"]["ok"] is False
    assert rb_data["status"] == "STATE_RESTORED_TRAFFIC_NOT_SHIFTED"


def test_unwritable_cache_dir_does_not_crash(tmp_path, monkeypatch):
    """The image runs as a non-root user: an unwritable cache path must not stop the backend."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("SENTINEL_STATE_CACHE_DIR", str(blocker / "cache"))
    store = S3StateStore()
    assert store.local_cache_enabled is False
    summary = store.snapshot_state({"inc-1": {"id": "inc-1"}})
    assert summary["status"] == "NOT_PERSISTED"
    assert store.get_storage_status()["storage_type"] == "NONE"


def test_local_cache_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_STATE_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("SENTINEL_STATE_CACHE_MAX", "3")
    store = S3StateStore()
    for i in range(6):
        store.snapshot_state({f"inc-{i}": {"id": f"inc-{i}"}})
        # distinct ids even within one second (content hash differs)
    assert len(list(tmp_path.glob("snap-*.json"))) <= 3
    assert len(store._snapshots_history) <= 3


def test_tampered_snapshot_is_not_restored(tmp_path, monkeypatch):
    import json as _json

    monkeypatch.setenv("SENTINEL_STATE_CACHE_DIR", str(tmp_path))
    store = S3StateStore()
    snap = store.snapshot_state({"inc-1": {"id": "inc-1", "status": "DETECTED"}})
    path = tmp_path / f"{snap['snapshot_id']}.json"
    payload = _json.loads(path.read_text())
    payload["incidents"]["inc-1"]["status"] = "RECOVERED"
    path.write_text(_json.dumps(payload))
    res = store.restore_snapshot(snap["snapshot_id"], {})
    assert res["success"] is False and "mismatch" in res["error"]
