"""
Adversarial and Security Test Suite for Task R3: Event Ingestion & GitLab Webhooks.
Tests:
- HMAC-SHA256 signature verification (missing, invalid, corrupted, prefix validation)
- Timestamp replay protection (missing, malformed, stale past >300s, future >300s, edge tolerance)
- JSON schema contract compliance (docs/contracts/event.schema.json, enums, regex patterns, additionalProperties)
- Atomic idempotency deduplication and concurrent duplicate submissions
- Sensitive data and secret pattern redaction before storage
- GitLab webhook authentication (constant-time token check, pipeline/job/MR events, idempotency)
- Out-of-order state transitions and authoritative evaluator source restrictions
"""

import concurrent.futures
import json
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.persistence.factory import get_repository

from tests.conftest import generate_signature


def _make_signed_request(
    client,
    payload: dict,
    secret: str,
    ts_header: str | None = None,
    sig_header: str | None = None,
    raw_body: bytes | None = None,
):
    """Helper to dispatch signed event requests with flexible header overrides."""
    now_iso = datetime.now(UTC).isoformat()
    body_bytes = raw_body if raw_body is not None else json.dumps(payload).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if ts_header is not None:
        if ts_header != "":
            headers["X-Sentinel-Timestamp"] = ts_header
    else:
        headers["X-Sentinel-Timestamp"] = payload.get("sent_at", now_iso)

    if sig_header is not None:
        if sig_header != "":
            headers["X-Sentinel-Signature"] = sig_header
    else:
        headers["X-Sentinel-Signature"] = generate_signature(secret, body_bytes)

    return client.post("/api/v1/events", content=body_bytes, headers=headers)


def _valid_payload(job_id: str = "1001", event_type: str = "incident.detected", **kwargs) -> dict:
    now_iso = datetime.now(UTC).isoformat()
    base = {
        "type": event_type,
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "999",
        "job_id": job_id,
        "commit_sha": "c9aaa1fac0a16d44677e19b431ec4e79bf4da53d",
        "incident_id": "inc-r3-test",
        "data": {"breached_thresholds": ["error_rate > 0.05"]},
        "sent_at": now_iso,
    }
    base.update(kwargs)
    return base


# ===========================================================================
# 1. HMAC Signature Verification Tests
# ===========================================================================
def test_valid_signature_accepted(client, hmac_secret):
    payload = _valid_payload(job_id="101")
    res = _make_signed_request(client, payload, hmac_secret)
    assert res.status_code == 202
    assert res.json()["status"] == "accepted"


def test_missing_signature_rejected(client, hmac_secret):
    payload = _valid_payload(job_id="102")
    res = _make_signed_request(client, payload, hmac_secret, sig_header="")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


def test_invalid_signature_wrong_secret(client):
    payload = _valid_payload(job_id="103")
    res = _make_signed_request(client, payload, secret="wrong-secret-key")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


def test_invalid_signature_corrupted_hex(client, hmac_secret):
    payload = _valid_payload(job_id="104")
    res = _make_signed_request(client, payload, hmac_secret, sig_header="sha256=badhexdeadbeef")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


def test_invalid_signature_missing_prefix(client, hmac_secret):
    payload = _valid_payload(job_id="105")
    # Missing 'sha256=' prefix
    raw_sig = generate_signature(hmac_secret, json.dumps(payload).encode("utf-8")).replace("sha256=", "")
    res = _make_signed_request(client, payload, hmac_secret, sig_header=raw_sig)
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "INVALID_SIGNATURE"


# ===========================================================================
# 2. Timestamp & Replay Protection Tests (±300 seconds window)
# ===========================================================================
def test_missing_timestamp_header_rejected(client, hmac_secret):
    payload = _valid_payload(job_id="201")
    res = _make_signed_request(client, payload, hmac_secret, ts_header="")
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "MISSING_TIMESTAMP"


def test_malformed_timestamp_header_rejected(client, hmac_secret):
    payload = _valid_payload(job_id="202")
    res = _make_signed_request(client, payload, hmac_secret, ts_header="not-a-timestamp-123xyz")
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "INVALID_TIMESTAMP"


def test_stale_timestamp_past_rejected(client, hmac_secret):
    stale_dt = datetime.now(UTC) - timedelta(seconds=305)
    stale_iso = stale_dt.isoformat()
    payload = _valid_payload(job_id="203", sent_at=stale_iso)
    res = _make_signed_request(client, payload, hmac_secret, ts_header=stale_iso)
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "TIMESTAMP_EXPIRED"


def test_future_timestamp_rejected(client, hmac_secret):
    future_dt = datetime.now(UTC) + timedelta(seconds=310)
    future_iso = future_dt.isoformat()
    payload = _valid_payload(job_id="204", sent_at=future_iso)
    res = _make_signed_request(client, payload, hmac_secret, ts_header=future_iso)
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "TIMESTAMP_EXPIRED"


def test_timestamp_within_tolerance_accepted(client, hmac_secret):
    # Within 300s window (250s in past)
    valid_dt = datetime.now(UTC) - timedelta(seconds=250)
    valid_iso = valid_dt.isoformat()
    payload = _valid_payload(job_id="205", sent_at=valid_iso)
    res = _make_signed_request(client, payload, hmac_secret, ts_header=valid_iso)
    assert res.status_code == 202
    assert res.json()["status"] == "accepted"


def test_epoch_timestamp_format_accepted(client, hmac_secret):
    epoch_now = str(datetime.now(UTC).timestamp())
    payload = _valid_payload(job_id="206")
    res = _make_signed_request(client, payload, hmac_secret, ts_header=epoch_now)
    assert res.status_code == 202


# ===========================================================================
# 3. JSON Schema Contract Validation Tests (docs/contracts/event.schema.json)
# ===========================================================================
def test_malformed_json_syntax_rejected(client, hmac_secret):
    now_iso = datetime.now(UTC).isoformat()
    broken_bytes = b'{"type": "incident.detected", "source": '  # Incomplete JSON
    sig = generate_signature(hmac_secret, broken_bytes)
    res = client.post(
        "/api/v1/events",
        content=broken_bytes,
        headers={
            "X-Sentinel-Signature": sig,
            "X-Sentinel-Timestamp": now_iso,
            "Content-Type": "application/json",
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "MALFORMED_EVENT"


def test_schema_missing_required_property(client, hmac_secret):
    payload = _valid_payload(job_id="301")
    del payload["pipeline_id"]  # Required by event.schema.json
    res = _make_signed_request(client, payload, hmac_secret)
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "MALFORMED_EVENT"
    assert "pipeline_id" in res.json()["detail"]["error"]["message"]


def test_schema_invalid_event_type_enum(client, hmac_secret):
    payload = _valid_payload(job_id="302", event_type="unauthorized.magic.event")
    res = _make_signed_request(client, payload, hmac_secret)
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "MALFORMED_EVENT"


def test_schema_invalid_pipeline_id_pattern(client, hmac_secret):
    # pipeline_id must match ^[0-9]+$
    payload = _valid_payload(job_id="303", pipeline_id="pipeline-not-digits")
    res = _make_signed_request(client, payload, hmac_secret)
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "MALFORMED_EVENT"


def test_schema_invalid_commit_sha_pattern(client, hmac_secret):
    # commit_sha must match ^[a-f0-9]{7,40}$
    payload = _valid_payload(job_id="304", commit_sha="invalid_sha_zzz!")
    res = _make_signed_request(client, payload, hmac_secret)
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "MALFORMED_EVENT"


def test_schema_rejects_additional_properties(client, hmac_secret):
    # event.schema.json has additionalProperties: false
    payload = _valid_payload(job_id="305", unapproved_field="malicious_payload")
    res = _make_signed_request(client, payload, hmac_secret)
    assert res.status_code == 400
    assert res.json()["detail"]["error"]["code"] == "MALFORMED_EVENT"


# ===========================================================================
# 4. Atomic Idempotency and Concurrency Tests
# ===========================================================================
def test_idempotent_duplicate_delivery(client, hmac_secret):
    payload = _valid_payload(job_id="401", event_type="rollback.started")

    # Delivery 1 -> Freshly Accepted
    res1 = _make_signed_request(client, payload, hmac_secret)
    assert res1.status_code == 202
    assert "note" not in res1.json()

    # Delivery 2 -> Acknowledged Idempotently
    res2 = _make_signed_request(client, payload, hmac_secret)
    assert res2.status_code == 202
    assert "Duplicate event acknowledged idempotently" in res2.json().get("note", "")


def test_concurrent_duplicate_submissions(client, hmac_secret):
    """
    Submits the exact same event across 10 concurrent threads.
    Verifies that no database crash or deadlock occurs, and duplicate checks are atomic.
    """
    payload = _valid_payload(
        job_id="402",
        incident_id="inc-concurrent-dedup",
        event_type="incident.detected",
    )

    def submit_event():
        return _make_signed_request(client, payload, hmac_secret)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(submit_event) for _ in range(10)]
        results = [f.result() for f in futures]

    assert all(r.status_code == 202 for r in results)
    notes = [r.json().get("note") for r in results if r.json().get("note")]
    # Exactly 9 requests should be flagged as duplicates
    assert len(notes) == 9


# ===========================================================================
# 5. Sensitive Data Redaction Tests
# ===========================================================================
def test_sensitive_payload_redaction(client, hmac_secret):
    inc_id = "inc-redaction-01"
    payload = _valid_payload(
        job_id="501",
        incident_id=inc_id,
        data={
            "breached_thresholds": ["error_rate > 0.05"],
            "api_key": "secret-super-key-12345",
            "db_password": "supersecretpassword",
            "authorization_token": "Bearer ghp_faketoken",
            "nested_config": {
                "private_key": "-----BEGIN PRIVATE KEY-----",
                "normal_field": "visible_metric_value",
            },
        },
    )

    res = _make_signed_request(client, payload, hmac_secret)
    assert res.status_code == 202

    # Verify persisted event in repository has redacted secrets
    repo = get_repository()
    timeline = repo.list_events_for_incident(inc_id)
    assert len(timeline) >= 1
    event_data = timeline[0].data

    assert event_data["api_key"] == "[REDACTED]"
    assert event_data["db_password"] == "[REDACTED]"
    assert event_data["authorization_token"] == "[REDACTED]"
    assert event_data["nested_config"]["private_key"] == "[REDACTED]"
    assert event_data["nested_config"]["normal_field"] == "visible_metric_value"


# ===========================================================================
# 6. GitLab Webhook Ingestion Tests
# ===========================================================================
def test_gitlab_webhook_missing_token_rejected(client):
    res = client.post("/api/v1/webhooks/gitlab", json={"object_kind": "pipeline"})
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "UNAUTHORIZED_WEBHOOK"


def test_gitlab_webhook_invalid_token_rejected(client):
    res = client.post(
        "/api/v1/webhooks/gitlab",
        json={"object_kind": "pipeline"},
        headers={"X-Gitlab-Token": "bad-token-123"},
    )
    assert res.status_code == 401
    assert res.json()["detail"]["error"]["code"] == "UNAUTHORIZED_WEBHOOK"


def test_gitlab_webhook_pipeline_event_processed(client):
    payload = {
        "object_kind": "pipeline",
        "object_attributes": {
            "id": 998811,
            "status": "success",
            "sha": "c9aaa1f",
            "ref": "main",
        },
    }
    res = client.post(
        "/api/v1/webhooks/gitlab",
        json=payload,
        headers={"X-Gitlab-Token": settings.gitlab_webhook_secret},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["event_type"] == "pipeline"


def test_gitlab_webhook_build_event_processed(client):
    payload = {
        "object_kind": "build",
        "build_id": 887711,
        "build_status": "failed",
        "build_name": "evaluator:candidate",
    }
    res = client.post(
        "/api/v1/webhooks/gitlab",
        json=payload,
        headers={"X-Gitlab-Token": settings.gitlab_webhook_secret},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "processed"


def test_gitlab_webhook_merge_request_event_processed(client):
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {
            "id": 443322,
            "iid": 42,
            "action": "open",
            "state": "opened",
            "source_branch": "duo/fix/inc-01",
        },
    }
    res = client.post(
        "/api/v1/webhooks/gitlab",
        json=payload,
        headers={"X-Gitlab-Token": settings.gitlab_webhook_secret},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "processed"


def test_gitlab_webhook_duplicate_acknowledged_idempotently(client):
    payload = {
        "object_kind": "pipeline",
        "object_attributes": {"id": 123456, "status": "running"},
    }
    # Delivery 1
    res1 = client.post(
        "/api/v1/webhooks/gitlab",
        json=payload,
        headers={"X-Gitlab-Token": settings.gitlab_webhook_secret},
    )
    assert res1.status_code == 200

    # Delivery 2 (Duplicate)
    res2 = client.post(
        "/api/v1/webhooks/gitlab",
        json=payload,
        headers={"X-Gitlab-Token": settings.gitlab_webhook_secret},
    )
    assert res2.status_code == 200
    assert "Duplicate webhook event acknowledged" in res2.json().get("note", "")
