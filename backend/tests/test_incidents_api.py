import json
from datetime import UTC, datetime

from tests.conftest import generate_signature


def test_incidents_api_list_and_detail(client, hmac_secret):
    inc_id = "inc-api-test-01"
    now_iso = datetime.now(UTC).isoformat()

    # Ingest an incident event to create an incident
    payload = {
        "type": "incident.detected",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "888",
        "job_id": "701",
        "commit_sha": "c9aaa1f",
        "incident_id": inc_id,
        "sent_at": now_iso,
        "data": {"breached_thresholds": ["error_rate > 0.05"]},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)
    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": now_iso,
        "Content-Type": "application/json",
    }
    client.post("/api/v1/events", content=body_bytes, headers=headers)

    # 1. Test List Incidents
    res_list = client.get("/api/v1/incidents")
    assert res_list.status_code == 200
    inc_ids = [inc["id"] for inc in res_list.json()]
    assert inc_id in inc_ids

    # 2. Test Get Incident Detail
    res_detail = client.get(f"/api/v1/incidents/{inc_id}")
    assert res_detail.status_code == 200
    data = res_detail.json()
    assert data["id"] == inc_id
    assert data["status"] == "DETECTED"
    assert "error_rate > 0.05" in data["breached_thresholds"]
    assert len(data["recovery_attempts"]) >= 1

    # 3. Test Get Nonexistent Incident (404)
    res_404 = client.get("/api/v1/incidents/inc-does-not-exist")
    assert res_404.status_code == 404
    assert res_404.json()["detail"]["error"]["code"] == "INCIDENT_NOT_FOUND"


def test_incident_timeline(client, hmac_secret):
    inc_id = "inc-timeline-test-01"
    now_iso = datetime.now(UTC).isoformat()

    payload = {
        "type": "incident.detected",
        "source": "sentinel/scripts/evaluator.py",
        "pipeline_id": "889",
        "job_id": "702",
        "commit_sha": "c9aaa1f",
        "incident_id": inc_id,
        "sent_at": now_iso,
        "data": {"breached_thresholds": ["latency > 200ms"]},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)
    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": now_iso,
        "Content-Type": "application/json",
    }
    client.post("/api/v1/events", content=body_bytes, headers=headers)

    res_timeline = client.get(f"/api/v1/incidents/{inc_id}/timeline")
    assert res_timeline.status_code == 200
    timeline = res_timeline.json()
    assert len(timeline) >= 1
    assert timeline[0]["type"] == "incident.detected"
    assert timeline[0]["incident_id"] == inc_id
