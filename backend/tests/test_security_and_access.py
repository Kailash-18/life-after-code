"""
Tasks R7 + R8: no secrets stored, writes only from CI, dashboard is read-only.
"""

import json

import pytest
from app.config import Settings, settings

from tests.helpers import FIX_SHA, drive_to, ok, send

FAKE_GITLAB_TOKEN = "glpat-" + "x1Y2z3" * 4  # seeded fake secret, not a real token


@pytest.mark.parametrize(
    "value",
    [
        FAKE_GITLAB_TOKEN,
        "AKIA" + "ABCDEFGHIJKLMNOP",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAuexample0123456789\n",
        "header was Bearer abcdefghijklmnopqrstuvwxyz012345",
    ],
)
def test_event_with_secret_value_is_rejected(client, hmac_secret, value):
    r = send(client, hmac_secret, "incident.detected", "inc-secret",
             data={"breached_thresholds": ["error_rate > 0.02"], "notes": value})
    assert r.status_code == 422
    err = r.json()["detail"]["error"]
    assert err["code"] == "SECRET_DETECTED"
    assert value not in json.dumps(r.json())  # never echo the secret
    assert client.get("/api/v1/incidents/inc-secret").status_code == 404


def test_backend_own_secret_is_rejected(client, hmac_secret):
    r = send(client, hmac_secret, "pipeline.started", data={"debug": f"secret={settings.hmac_secret}"})
    assert r.status_code == 422


def test_ordinary_values_are_not_flagged(client, hmac_secret):
    ok(send(client, hmac_secret, "pipeline.started",
            data={"version": "1.2.3", "note": "tokenizer bench passed", "revision_name": "target-app-00003-xyz"}))


def test_webhook_payload_secrets_are_masked_not_stored(client):
    payload = {
        "object_kind": "build",
        "build_id": 77,
        "build_status": "failed",
        "commit": {"message": f"oops committed {FAKE_GITLAB_TOKEN}"},
    }
    r = client.post("/api/v1/webhooks/gitlab", json=payload,
                    headers={"X-Gitlab-Token": settings.gitlab_webhook_secret})
    assert r.status_code == 200
    from app.persistence.factory import get_repository

    stored = get_repository().list_events_for_incident("77")
    assert stored and FAKE_GITLAB_TOKEN not in json.dumps(stored[0].data)


# ---------------------------------------------------------------------------
# R8 access control
# ---------------------------------------------------------------------------
def test_write_endpoint_rejects_dashboard_style_credentials(client):
    body = json.dumps({"type": "recovery.verified"}).encode()
    for headers in (
        {},
        {"Authorization": "Bearer dashboard-read-token"},
        {"Origin": "http://localhost:5173", "X-Gitlab-Token": settings.gitlab_webhook_secret},
    ):
        r = client.post("/api/v1/events", content=body, headers={"Content-Type": "application/json", **headers})
        assert r.status_code == 401


def test_webhook_token_is_not_accepted_as_ci_signature(client):
    body = b'{"type":"incident.detected"}'
    r = client.post("/api/v1/events", content=body,
                    headers={"X-Sentinel-Signature": "sha256=" + settings.gitlab_webhook_secret})
    assert r.status_code == 401


def test_read_endpoints_do_not_accept_writes(client):
    for path in ("/api/v1/status", "/api/v1/incidents", "/api/v1/releases"):
        assert client.post(path, json={}).status_code == 405
        assert client.put(path, json={}).status_code == 405
        assert client.delete(path).status_code == 405


def test_cors_lets_browsers_read_but_not_write(client):
    origin = settings.cors_origins[0]
    pre = client.options("/api/v1/events", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 400 or "POST" not in pre.headers.get("access-control-allow-methods", "")
    get_pre = client.options("/api/v1/status", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET"})
    assert get_pre.status_code == 200


def test_analysis_is_labelled_advisory(client, hmac_secret):
    from app.models.entities import Analysis
    from app.persistence.factory import get_repository

    drive_to(client, hmac_secret, "inc-advisory", "INVESTIGATING")
    repo = get_repository()
    inc = repo.get_incident("inc-advisory")
    att = inc.recovery_attempts[-1]
    repo.set_attempt_analysis("inc-advisory", att.id, Analysis(attempt_id=att.id, facts=["x"]))
    body = client.get("/api/v1/incidents/inc-advisory").json()
    assert body["recovery_attempts"][-1]["analysis"]["advisory"] is True


def test_production_refuses_dev_secrets(monkeypatch):
    s = Settings()
    monkeypatch.setattr(s, "sentinel_env", "production")
    with pytest.raises(RuntimeError, match="SENTINEL_HMAC_SECRET"):
        s.validate_for_startup()
    monkeypatch.setattr(s, "hmac_secret", "r" * 40)
    monkeypatch.setattr(s, "gitlab_webhook_secret", "w" * 40)
    s.validate_for_startup()


def test_schema_missing_fails_closed(monkeypatch, tmp_path):
    from app.routes import events

    monkeypatch.setattr(events, "_VALIDATOR", None)
    monkeypatch.setattr(events, "SCHEMA_CANDIDATES", [tmp_path / "missing.json"])
    monkeypatch.setattr(settings, "event_schema_path", None)
    with pytest.raises(RuntimeError, match="Event contract not found"):
        events.get_contract_validator()


# ---------------------------------------------------------------------------
# GitLab MR webhooks drive repair.proposed / merge.completed
# ---------------------------------------------------------------------------
def _mr(action, inc_id, iid=21, sha=FIX_SHA):
    return {
        "object_kind": "merge_request",
        "object_attributes": {
            "iid": iid, "action": action, "state": "opened",
            "source_branch": f"duo/fix/{inc_id}", "last_commit": {"id": sha},
        },
    }


def test_mr_open_webhook_proposes_repair(client, hmac_secret):
    inc_id = "inc-mr-01"
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    r = client.post("/api/v1/webhooks/gitlab", json=_mr("open", inc_id),
                    headers={"X-Gitlab-Token": settings.gitlab_webhook_secret})
    assert r.status_code == 200
    assert r.json()["state_machine"]["applied"] == "repair.proposed"
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["status"] == "REPAIR_PROPOSED"
    assert inc["recovery_attempts"][-1]["mr_iid"] == 21
    assert inc["recovery_attempts"][-1]["fix_sha"] == FIX_SHA
    types = [e["type"] for e in client.get(f"/api/v1/incidents/{inc_id}/timeline").json()]
    assert "gitlab.merge_request.open" in types


def test_mr_merge_webhook_without_gates_escalates_but_returns_200(client, hmac_secret):
    inc_id = "inc-mr-02"
    drive_to(client, hmac_secret, inc_id, "REPAIR_PROPOSED")
    r = client.post("/api/v1/webhooks/gitlab", json=_mr("merge", inc_id),
                    headers={"X-Gitlab-Token": settings.gitlab_webhook_secret})
    assert r.status_code == 200
    assert client.get(f"/api/v1/incidents/{inc_id}").json()["status"] == "ESCALATED"


def test_mr_on_unrelated_branch_is_only_recorded(client):
    payload = _mr("open", "whatever")
    payload["object_attributes"]["source_branch"] = "feature/x"
    r = client.post("/api/v1/webhooks/gitlab", json=payload,
                    headers={"X-Gitlab-Token": settings.gitlab_webhook_secret})
    assert r.status_code == 200 and "state_machine" not in r.json()


def test_error_body_follows_contract(client):
    r = client.get("/api/v1/incidents/inc-missing")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert set(r.json()["error"]) == {"code", "message", "retryable"}


def test_oversized_event_is_rejected(client, hmac_secret):
    r = send(client, hmac_secret, "pipeline.started", data={"blob": "x" * (300 * 1024)})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_gitlab_pipeline_webhook_joins_incident_timeline(client, hmac_secret):
    drive_to(client, hmac_secret, "inc-gl-pipe", "DETECTED")  # helper uses pipeline 999
    payload = {"object_kind": "pipeline", "object_attributes": {"id": 999, "status": "failed", "sha": "abc"}}
    r = client.post("/api/v1/webhooks/gitlab", json=payload, headers={"X-Gitlab-Token": settings.gitlab_webhook_secret})
    assert r.status_code == 200
    types = [e["type"] for e in client.get("/api/v1/incidents/inc-gl-pipe/timeline").json()]
    assert "gitlab.pipeline.failed" in types
    assert client.get("/api/v1/incidents/inc-gl-pipe").json()["status"] == "DETECTED"
