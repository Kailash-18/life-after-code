"""
R9 contract tests: real responses must validate against docs/contracts/openapi.yaml,
so Mission Control can rely on the documented shapes.
"""

from pathlib import Path

import jsonschema
import pytest
import yaml
from app.models.entities import Analysis
from app.persistence.factory import get_repository

from tests.helpers import BROKEN_SHA, FIX_SHA, drive_to, ok, send

SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.yaml").read_text(encoding="utf-8")
)
EVALUATOR = "sentinel/scripts/evaluator.py"


def response_schema(path: str, method: str, code: str) -> dict:
    content = SPEC["paths"][path][method]["responses"][code]
    if "$ref" in content:  # components/responses/...
        content = SPEC["components"]["responses"][content["$ref"].split("/")[-1]]
    schema = content["content"]["application/json"]["schema"]
    return {**schema, "components": SPEC["components"]}


def assert_matches(body, path, method="get", code="200"):
    schema = response_schema(path, method, code)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:5]]


@pytest.fixture
def populated(client, hmac_secret):
    """A recovered incident, a failed incident, releases with deployments and health."""
    ok(send(client, hmac_secret, "deploy.canary_started", data={"traffic_percent": 10, "revision_name": "r-1"}))
    ok(send(client, hmac_secret, "evaluator.verdict", source=EVALUATOR,
            data={"verdict": "FAIL", "target": "candidate", "traffic_percent": 10,
                  "error_rate": 0.26, "p95_ms": 120.0, "sample_size": 300}))
    drive_to(client, hmac_secret, "inc-contract-ok", "RECOVERED")
    repo = get_repository()
    inc = repo.get_incident("inc-contract-ok")
    att = inc.recovery_attempts[-1]
    repo.set_attempt_analysis(inc.id, att.id, Analysis(
        attempt_id=att.id, facts=["error_rate 0.26 [metrics.json]"], hypotheses=["h (confidence: high)"],
        missing_evidence=[], suspected_change='{"commit_sha": "abc"}', file_ref="x@y"))
    drive_to(client, hmac_secret, "inc-contract-fail", "REPAIR_PROPOSED")
    ok(send(client, hmac_secret, "integrity_gate.verdict", "inc-contract-fail",
            data={"verdict": "FAIL", "findings": ["BLOCKING IG-SKIP"], "reason": "blocked"}))
    send(client, hmac_secret, "recovery.verified", "inc-contract-fail", data={"verdict": "PASS"}, source=EVALUATOR)
    return {"ok": "inc-contract-ok", "fail": "inc-contract-fail"}


def test_status_before_any_data_matches_contract(client):
    assert_matches(client.get("/api/v1/status").json(), "/api/v1/status")


def test_read_endpoints_match_contract(client, populated):
    assert_matches(client.get("/api/v1/healthz").json(), "/api/v1/healthz")
    assert_matches(client.get("/api/v1/status").json(), "/api/v1/status")

    releases = client.get("/api/v1/releases").json()
    assert {r["commit_sha"] for r in releases} >= {BROKEN_SHA, FIX_SHA}
    assert_matches(releases, "/api/v1/releases")
    for rel in releases:
        assert_matches(client.get(f"/api/v1/releases/{rel['id']}").json(), "/api/v1/releases/{id}")

    incidents = client.get("/api/v1/incidents").json()
    assert len(incidents) == 2
    assert_matches(incidents, "/api/v1/incidents")
    for inc_id in populated.values():
        assert_matches(client.get(f"/api/v1/incidents/{inc_id}").json(), "/api/v1/incidents/{id}")
        timeline = client.get(f"/api/v1/incidents/{inc_id}/timeline").json()
        assert timeline
        assert_matches(timeline, "/api/v1/incidents/{id}/timeline")


def test_event_responses_match_contract(client, hmac_secret):
    accepted = send(client, hmac_secret, "incident.detected", "inc-contract-ev",
                    data={"breached_thresholds": ["x"]})
    assert_matches(accepted.json(), "/api/v1/events", "post", "202")
    for resp, code in [
        (send(client, hmac_secret, "recovery.verified", "inc-contract-ev", data={"verdict": "PASS"},
              source=EVALUATOR), "409"),
        (send(client, hmac_secret, "rollback.completed", "inc-contract-ev", data={}), "422"),
        (client.post("/api/v1/events", content=b"{}"), "401"),
    ]:
        assert resp.status_code == int(code)
        assert_matches(resp.json(), "/api/v1/events", "post", code)


def test_not_found_errors_match_contract(client):
    for path, template in [("/api/v1/incidents/inc-nope", "/api/v1/incidents/{id}"),
                           ("/api/v1/incidents/inc-nope/timeline", "/api/v1/incidents/{id}/timeline"),
                           ("/api/v1/releases/rel-nope", "/api/v1/releases/{id}")]:
        resp = client.get(path)
        assert resp.status_code == 404
        assert_matches(resp.json(), template, "get", "404")


def test_webhook_responses_match_contract(client, hmac_secret):
    from app.config import settings

    drive_to(client, hmac_secret, "inc-contract-mr", "INVESTIGATING")
    headers = {"X-Gitlab-Token": settings.gitlab_webhook_secret}
    mr = {"object_kind": "merge_request", "object_attributes": {
        "iid": 5, "action": "open", "source_branch": "duo/fix/inc-contract-mr", "last_commit": {"id": FIX_SHA}}}
    for payload in (mr, {"object_kind": "pipeline", "object_attributes": {"id": 1, "status": "success"}}):
        resp = client.post("/api/v1/webhooks/gitlab", json=payload, headers=headers)
        assert resp.status_code == 200
        assert_matches(resp.json(), "/api/v1/webhooks/gitlab", "post", "200")
    bad = client.post("/api/v1/webhooks/gitlab", json=mr, headers={"X-Gitlab-Token": "nope"})
    assert bad.status_code == 401
    assert_matches(bad.json(), "/api/v1/webhooks/gitlab", "post", "401")
