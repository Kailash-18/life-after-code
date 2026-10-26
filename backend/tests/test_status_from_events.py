"""
Task R6: /status and /releases show only what CI and the evaluator measured.
"""

from tests.helpers import BROKEN_SHA, FIX_SHA, ok, send

EVALUATOR = "sentinel/scripts/evaluator.py"


def test_status_is_unknown_before_any_measurement(client):
    body = client.get("/api/v1/status").json()
    assert body["current_release"] is None
    assert body["candidate_release"] is None
    assert body["traffic_split"] == {"stable_percent": 100, "candidate_percent": 0}
    assert body["system_health"]["healthy"] is None
    assert body["system_health"]["error_rate"] is None
    assert body["active_incident"] is None


def test_healthy_rollout_becomes_known_good_stable(client, hmac_secret):
    ok(send(client, hmac_secret, "pipeline.started", commit_sha=FIX_SHA, data={"version": "1.1.0"}))
    ok(send(client, hmac_secret, "deploy.canary_started", commit_sha=FIX_SHA,
            data={"traffic_percent": 10, "revision_name": "target-app-00002-abc"}))

    mid = client.get("/api/v1/status").json()
    assert mid["candidate_release"]["revision_name"] == "target-app-00002-abc"
    assert mid["traffic_split"] == {"stable_percent": 90, "candidate_percent": 10}

    ok(send(client, hmac_secret, "evaluator.verdict", commit_sha=FIX_SHA, source=EVALUATOR, job_id=9100,
            data={"verdict": "PASS", "target": "candidate", "traffic_percent": 10,
                  "error_rate": 0.004, "p95_ms": 41.5, "sample_size": 300}))
    health = client.get("/api/v1/status").json()["system_health"]
    assert health["error_rate"] == 0.004 and health["p95_ms"] == 41.5
    assert health["healthy"] is True and health["sample_size"] == 300

    ok(send(client, hmac_secret, "deploy.canary_started", commit_sha=FIX_SHA, data={"traffic_percent": 100}))
    ok(send(client, hmac_secret, "evaluator.verdict", commit_sha=FIX_SHA, source=EVALUATOR, job_id=9101,
            data={"verdict": "PASS", "target": "candidate", "traffic_percent": 100,
                  "error_rate": 0.002, "p95_ms": 39.0, "sample_size": 600}))
    final = client.get("/api/v1/status").json()
    assert final["current_release"]["id"] == f"rel-{FIX_SHA[:12]}"
    assert final["current_release"]["known_good"] is True
    assert final["candidate_release"] is None
    assert final["traffic_split"]["stable_percent"] == 100

    rel = client.get(f"/api/v1/releases/rel-{FIX_SHA[:12]}").json()
    assert rel["version"] == "1.1.0"
    assert {d["traffic_percent"] for d in rel["deployments"]} == {10, 100}


def test_faulty_canary_reports_measured_regression(client, hmac_secret):
    ok(send(client, hmac_secret, "deploy.canary_started", commit_sha=BROKEN_SHA, data={"traffic_percent": 10}))
    ok(send(client, hmac_secret, "evaluator.verdict", commit_sha=BROKEN_SHA, source=EVALUATOR,
            data={"verdict": "FAIL", "target": "candidate", "traffic_percent": 10,
                  "error_rate": 0.31, "p95_ms": 220.0, "sample_size": 200}))
    ok(send(client, hmac_secret, "incident.detected", "inc-status-01", source=EVALUATOR, commit_sha=BROKEN_SHA,
            data={"breached_thresholds": ["error_rate 0.31 > 0.02"]}))
    body = client.get("/api/v1/status").json()
    assert body["system_health"]["error_rate"] == 0.31
    assert body["system_health"]["healthy"] is False
    assert body["active_incident"]["id"] == "inc-status-01"
    assert client.get(f"/api/v1/releases/rel-{BROKEN_SHA[:12]}").json()["status"] == "FAILED"


def test_releases_unknown_id_404(client):
    r = client.get("/api/v1/releases/rel-nope")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "RELEASE_NOT_FOUND"


def test_one_job_can_step_traffic(client, hmac_secret):
    """A single deploy job stepping 10 -> 50 -> 100 % must not be de-duplicated."""
    for pct in (10, 50, 100):
        body = ok(send(client, hmac_secret, "deploy.canary_started", commit_sha=FIX_SHA, job_id=4100,
                       data={"traffic_percent": pct}))
        assert "note" not in body
        ok(send(client, hmac_secret, "evaluator.verdict", commit_sha=FIX_SHA, job_id=4101, source=EVALUATOR,
                data={"verdict": "PASS", "target": "candidate", "traffic_percent": pct,
                      "error_rate": 0.001, "p95_ms": 30.0, "sample_size": 100}))
    rel = client.get(f"/api/v1/releases/rel-{FIX_SHA[:12]}").json()
    assert {d["traffic_percent"] for d in rel["deployments"]} == {10, 50, 100}
    assert rel["status"] == "STABLE"
    # A true retry of the same step is still a duplicate.
    again = ok(send(client, hmac_secret, "deploy.canary_started", commit_sha=FIX_SHA, job_id=4100,
                    data={"traffic_percent": 50}))
    assert "Duplicate" in again["note"]


def test_placeholder_release_id_does_not_split_the_release(client, hmac_secret):
    """canary_deploy.py sends release_id=rel-candidate-001 for every release; the evaluator sends none.
    Both must land on the same release (the commit), and /status must settle after 100 %."""
    for pct in (10, 50, 100):
        ok(send(client, hmac_secret, "deploy.canary_started", commit_sha=FIX_SHA, release_id="rel-candidate-001",
                data={"traffic_percent": pct, "revision_name": "target-app-00009"}))
        ok(send(client, hmac_secret, "evaluator.verdict", commit_sha=FIX_SHA, source=EVALUATOR,
                data={"verdict": "PASS", "target": "candidate", "traffic_percent": pct,
                      "error_rate": 0.0, "p95_ms": 9.0, "sample_size": 100}))
    releases = client.get("/api/v1/releases").json()
    assert [r["id"] for r in releases] == [f"rel-{FIX_SHA[:12]}"]
    status = client.get("/api/v1/status").json()
    assert status["current_release"]["revision_name"] == "target-app-00009"
    assert status["candidate_release"] is None
    assert status["traffic_split"] == {"stable_percent": 100, "candidate_percent": 0}

    # Next faulty release with the same placeholder: it is a separate release, rolled back.
    ok(send(client, hmac_secret, "deploy.canary_started", commit_sha=BROKEN_SHA, release_id="rel-candidate-001",
            data={"traffic_percent": 10}))
    assert client.get("/api/v1/status").json()["traffic_split"] == {"stable_percent": 90, "candidate_percent": 10}
    ok(send(client, hmac_secret, "evaluator.verdict", commit_sha=BROKEN_SHA, source=EVALUATOR,
            data={"verdict": "FAIL", "target": "candidate", "traffic_percent": 10, "error_rate": 0.2,
                  "p95_ms": 9.0, "sample_size": 100, "breached_thresholds": ["error_rate"]}))
    ok(send(client, hmac_secret, "rollback.completed", commit_sha=BROKEN_SHA, data={"post_rollback_probe_ok": True}))
    status = client.get("/api/v1/status").json()
    assert status["current_release"]["commit_sha"] == FIX_SHA
    assert status["traffic_split"] == {"stable_percent": 100, "candidate_percent": 0}
