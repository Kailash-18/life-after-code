import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta


def generate_signature(secret: str, body_bytes: bytes) -> str:
    hex_digest = hmac.new(
        secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()
    return f"sha256={hex_digest}"


def test_events_missing_signature_rejected(client):
    payload = {
        "type": "evaluator.verdict",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "1001",
        "job_id": "2001",
        "commit_sha": "abc1234",
        "sent_at": datetime.now(UTC).isoformat(),
        "data": {"verdict": "PASS"},
    }
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


def test_events_invalid_signature_rejected(client):
    payload = {
        "type": "evaluator.verdict",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "1001",
        "job_id": "2002",
        "commit_sha": "abc1234",
        "sent_at": datetime.now(UTC).isoformat(),
        "data": {"verdict": "PASS"},
    }
    headers = {
        "X-Sentinel-Signature": "sha256=invalidhexdigest000000000000000000000000000000000000000000000000",
        "X-Sentinel-Timestamp": datetime.now(UTC).isoformat(),
    }
    response = client.post("/api/v1/events", json=payload, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


def test_events_missing_timestamp_rejected(client, hmac_secret):
    payload = {
        "type": "incident.detected",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "1002",
        "job_id": "2003",
        "commit_sha": "c9aaa1f",
        "sent_at": datetime.now(UTC).isoformat(),
        "data": {"breached_thresholds": ["error_rate > 0.02"]},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)

    headers = {"X-Sentinel-Signature": sig, "Content-Type": "application/json"}
    response = client.post("/api/v1/events", content=body_bytes, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "MISSING_TIMESTAMP"


def test_events_invalid_timestamp_rejected(client, hmac_secret):
    payload = {
        "type": "incident.detected",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "1002",
        "job_id": "2003b",
        "commit_sha": "c9aaa1f",
        "sent_at": datetime.now(UTC).isoformat(),
        "data": {"breached_thresholds": ["error_rate > 0.02"]},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)

    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": "not-a-valid-timestamp",
        "Content-Type": "application/json",
    }
    response = client.post("/api/v1/events", content=body_bytes, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_TIMESTAMP"


def test_events_expired_timestamp_rejected_replay_protection(client, hmac_secret):
    payload = {
        "type": "incident.detected",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "1002",
        "job_id": "2003c",
        "commit_sha": "c9aaa1f",
        "sent_at": datetime.now(UTC).isoformat(),
        "data": {"breached_thresholds": ["error_rate > 0.02"]},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)

    # 10 minutes in the past (> 300 seconds window)
    expired_ts = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()

    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": expired_ts,
        "Content-Type": "application/json",
    }
    response = client.post("/api/v1/events", content=body_bytes, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "TIMESTAMP_EXPIRED"


def test_events_valid_signature_and_timestamp_accepted(client, hmac_secret):
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "type": "incident.detected",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "1002",
        "job_id": "2003",
        "commit_sha": "c9aaa1f",
        "incident_id": "inc-test-auth-01",
        "sent_at": now_iso,
        "data": {"breached_thresholds": ["error_rate > 0.02"]},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)

    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": now_iso,
        "Content-Type": "application/json",
    }

    response = client.post("/api/v1/events", content=body_bytes, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert "event_id" in data


def test_events_malformed_payload_rejected(client, hmac_secret):
    # Missing required commit_sha and source
    body_bytes = b'{"type": "incident.detected"}'
    sig = generate_signature(hmac_secret, body_bytes)
    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": datetime.now(UTC).isoformat(),
        "Content-Type": "application/json",
    }
    response = client.post("/api/v1/events", content=body_bytes, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "MALFORMED_EVENT"


def test_events_idempotency_on_duplicate(client, hmac_secret):
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "type": "pipeline.started",
        "source": "sentinel/ci/pipeline",
        "pipeline_id": "1003",
        "job_id": "2004",
        "commit_sha": "c9aaa1f",
        "sent_at": now_iso,
        "data": {"stage": "build"},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)
    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": now_iso,
        "Content-Type": "application/json",
    }

    # First send
    res1 = client.post("/api/v1/events", content=body_bytes, headers=headers)
    assert res1.status_code == 202

    # Second send (retry from CI with identical job_id and type)
    res2 = client.post("/api/v1/events", content=body_bytes, headers=headers)
    assert res2.status_code == 202
    assert "Duplicate event acknowledged idempotently" in res2.json()["note"]
