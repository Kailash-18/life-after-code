"""
Task R5: one flow per incident attempt, failures and timeouts recorded honestly.
The GitLab Flows API is mocked here; the real call is UNVERIFIED until spike S1.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app import flow_dispatch
from app.config import settings
from app.persistence.factory import get_repository
from tests.helpers import drive_to, ok, send


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.fixture
def gitlab_api_mode(monkeypatch):
    monkeypatch.setattr(settings, "flow_dispatch_mode", "gitlab_api")
    monkeypatch.setattr(settings, "gitlab_project_id", "12345")
    monkeypatch.setattr(settings, "gitlab_flow_token", "test-token-not-real")
    monkeypatch.setattr(settings, "gitlab_flow_definition", "sentinel_investigate")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(201, {"id": 9001})

    monkeypatch.setattr(flow_dispatch.httpx, "post", fake_post)
    return calls


def test_disabled_mode_waits_for_ci_flow_started(client, hmac_secret):
    inc_id = "inc-dispatch-off"
    drive_to(client, hmac_secret, inc_id, "EVIDENCE_COLLECTED")
    assert client.get(f"/api/v1/incidents/{inc_id}").json()["status"] == "EVIDENCE_COLLECTED"


def test_evidence_collected_dispatches_flow_once(client, hmac_secret, gitlab_api_mode):
    inc_id = "inc-dispatch-01"
    drive_to(client, hmac_secret, inc_id, "EVIDENCE_COLLECTED")  # background task runs in TestClient
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["status"] == "INVESTIGATING"
    att = inc["recovery_attempts"][-1]
    assert att["flow_session_id"] == "9001"
    assert att["deadline_at"] is not None

    assert len(gitlab_api_mode) == 1
    call = gitlab_api_mode[0]
    assert call["url"].endswith("/ai/duo_workflows/workflows")
    assert call["json"]["start_workflow"] is True
    assert call["json"]["workflow_definition"] == "sentinel_investigate"
    goal = call["json"]["goal"]
    assert inc_id in goal and "evidence" in goal.lower()
    assert "test-token-not-real" not in goal and "{{" not in goal

    # A second trigger for the same attempt never starts another flow.
    flow_dispatch.maybe_dispatch(inc_id)
    assert len(gitlab_api_mode) == 1

    types = [e["type"] for e in client.get(f"/api/v1/incidents/{inc_id}/timeline").json()]
    assert "flow.started" in types


def test_dispatch_failure_records_investigation_failed(client, hmac_secret, gitlab_api_mode, monkeypatch):
    monkeypatch.setattr(flow_dispatch.httpx, "post", lambda *a, **k: FakeResponse(403, {"message": "forbidden"}))
    inc_id = "inc-dispatch-fail"
    drive_to(client, hmac_secret, inc_id, "EVIDENCE_COLLECTED")
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["status"] == "INVESTIGATION_FAILED"
    assert "HTTP 403" in inc["recovery_attempts"][-1]["failure_reason"]
    types = [e["type"] for e in client.get(f"/api/v1/incidents/{inc_id}/timeline").json()]
    assert "flow.dispatch_failed" in types


def test_flow_deadline_moves_to_timed_out(client, hmac_secret):
    inc_id = "inc-timeout-01"
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    repo = get_repository()
    inc = repo.get_incident(inc_id)
    inc.recovery_attempts[-1].deadline_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    repo.save_incident(inc)

    body = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert body["status"] == "TIMED_OUT"
    assert "did not propose a repair" in body["recovery_attempts"][-1]["failure_reason"]
    timeline = client.get(f"/api/v1/incidents/{inc_id}/timeline").json()
    assert timeline[-1]["type"] == "flow.timed_out"

    # A late repair proposal cannot revive a timed-out attempt.
    r = send(client, hmac_secret, "repair.proposed", inc_id, data={"mr_iid": 3, "fix_sha": "abcdef1"})
    assert r.status_code == 409


def test_flow_started_before_deadline_stays_investigating(client, hmac_secret):
    inc_id = "inc-timeout-02"
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    assert client.get(f"/api/v1/incidents/{inc_id}").json()["status"] == "INVESTIGATING"


def test_flow_completed_fail_marks_investigation_failed(client, hmac_secret):
    inc_id = "inc-flow-fail"
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    ok(send(client, hmac_secret, "flow.completed", inc_id, data={"verdict": "FAIL", "reason": "agent stopped"}))
    assert client.get(f"/api/v1/incidents/{inc_id}").json()["status"] == "INVESTIGATION_FAILED"
