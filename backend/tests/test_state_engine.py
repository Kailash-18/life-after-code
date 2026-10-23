"""
Task R4: the recovery state machine only moves on authoritative evidence (§A5, §A6).
"""

from tests.helpers import (
    BROKEN_SHA,
    EVIDENCE_SHA,
    EVIDENCE_URL,
    FIX_SHA,
    PROOF_PASS,
    drive_to,
    ok,
    send,
)

EVALUATOR = "sentinel/scripts/evaluator.py"


def _status(client, inc_id):
    return client.get(f"/api/v1/incidents/{inc_id}").json()["status"]


def test_recovery_lifecycle_happy_path(client, hmac_secret):
    inc_id = "inc-lifecycle-01"
    drive_to(client, hmac_secret, inc_id, "RECOVERED")
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    att = inc["recovery_attempts"][-1]
    assert inc["status"] == "RECOVERED"
    assert inc["evidence_bundle_ref"] == EVIDENCE_URL
    assert inc["evidence_sha256"] == EVIDENCE_SHA
    assert att["flow_session_id"] == "duo-session-001"
    assert att["mr_iid"] == 12 and att["fix_sha"] == FIX_SHA
    kinds = {(t["kind"], t["outcome"]) for t in att["test_results"]}
    assert ("regression_on_broken", "FAILED") in kinds
    assert ("regression_on_fix", "PASSED") in kinds
    assert att["gate_results"][-1]["verdict"] == "pass"


def test_recovered_cites_the_evaluator_job(client, hmac_secret):
    inc_id = "inc-cite-01"
    drive_to(client, hmac_secret, inc_id, "REDEPLOYING")
    ok(
        send(
            client, hmac_secret, "recovery.verified", inc_id,
            data={"verdict": "PASS", "traffic_percent": 100, "error_rate": 0.0, "p95_ms": 30.0},
            source=EVALUATOR, commit_sha=FIX_SHA, job_id=777001,
        )
    )
    timeline = client.get(f"/api/v1/incidents/{inc_id}/timeline").json()
    final = [e for e in timeline if e["type"] == "recovery.verified"][-1]
    assert final["source"] == EVALUATOR and final["source_job_id"] == "777001"
    rel = client.get(f"/api/v1/releases/rel-{FIX_SHA[:12]}").json()
    assert rel["status"] == "STABLE" and rel["known_good"] is True
    assert any(d["evaluator_job_id"] == "777001" for d in rel["deployments"])


def test_cannot_skip_states_to_recovered(client, hmac_secret):
    inc_id = "inc-skip-01"
    drive_to(client, hmac_secret, inc_id, "DETECTED")
    r = send(client, hmac_secret, "recovery.verified", inc_id, data={"verdict": "PASS"}, source=EVALUATOR)
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert _status(client, inc_id) == "DETECTED"


def test_every_skip_is_rejected(client, hmac_secret):
    """From DETECTED, each later step (other than the next one) must be refused."""
    inc_id = "inc-skip-all"
    drive_to(client, hmac_secret, inc_id, "DETECTED")
    for etype, data, extra in [
        ("evidence.collected", {"evidence_sha256": EVIDENCE_SHA}, {"artifact_url": EVIDENCE_URL}),
        ("flow.started", {"flow_session_id": "s"}, {}),
        ("repair.proposed", {"mr_iid": 1, "fix_sha": FIX_SHA}, {}),
    ]:
        r = send(client, hmac_secret, etype, inc_id, data=data, **extra)
        assert r.status_code == 409, etype
    assert _status(client, inc_id) == "DETECTED"


def test_unauthoritative_source_cannot_declare_recovery(client, hmac_secret):
    inc_id = "inc-unauth-01"
    drive_to(client, hmac_secret, inc_id, "REDEPLOYING")
    r = send(client, hmac_secret, "recovery.verified", inc_id, data={"verdict": "PASS"},
             source="gitlab/duo/agent", commit_sha=FIX_SHA)
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "UNAUTHORITATIVE_SOURCE"
    assert _status(client, inc_id) == "REDEPLOYING"


def test_recovery_must_evaluate_the_fix_release(client, hmac_secret):
    inc_id = "inc-wrong-rel-01"
    drive_to(client, hmac_secret, inc_id, "REDEPLOYING")
    r = send(client, hmac_secret, "recovery.verified", inc_id, data={"verdict": "PASS"},
             source=EVALUATOR, commit_sha=BROKEN_SHA)
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "WRONG_RELEASE"
    assert _status(client, inc_id) == "REDEPLOYING"


def test_recovery_requires_full_traffic_when_reported(client, hmac_secret):
    inc_id = "inc-partial-01"
    drive_to(client, hmac_secret, inc_id, "REDEPLOYING")
    r = send(client, hmac_secret, "recovery.verified", inc_id,
             data={"verdict": "PASS", "traffic_percent": 50}, source=EVALUATOR, commit_sha=FIX_SHA)
    assert r.status_code == 422
    assert _status(client, inc_id) == "REDEPLOYING"


def test_evaluator_fail_transitions_to_redeploy_unhealthy(client, hmac_secret):
    inc_id = "inc-fail-eval-01"
    drive_to(client, hmac_secret, inc_id, "REDEPLOYING")
    ok(send(client, hmac_secret, "recovery.verified", inc_id,
            data={"verdict": "FAIL", "reason": "error rate 0.06 > 0.02"}, source=EVALUATOR, commit_sha=FIX_SHA))
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["status"] == "REDEPLOY_UNHEALTHY"
    assert "0.06" in inc["recovery_attempts"][-1]["failure_reason"]


def test_merge_without_gate_evidence_escalates(client, hmac_secret):
    """A merge reported before regression proof + integrity pass is never treated as MERGED."""
    inc_id = "inc-merge-early"
    drive_to(client, hmac_secret, inc_id, "REPAIR_PROPOSED")
    ok(send(client, hmac_secret, "integrity_gate.verdict", inc_id, data={"verdict": "PASS"}))
    ok(send(client, hmac_secret, "merge.completed", inc_id))
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["status"] == "ESCALATED"
    assert "regression proof" in inc["recovery_attempts"][-1]["failure_reason"]


def test_regression_pass_without_both_runs_is_refused(client, hmac_secret):
    inc_id = "inc-proof-thin"
    drive_to(client, hmac_secret, inc_id, "REPAIR_PROPOSED")
    r = send(client, hmac_secret, "regression_proof.verdict", inc_id, data={"verdict": "PASS"})
    assert r.status_code == 422
    assert _status(client, inc_id) == "REPAIR_PROPOSED"


def test_regression_proof_with_import_error_is_not_proof(client, hmac_secret):
    inc_id = "inc-proof-import"
    drive_to(client, hmac_secret, inc_id, "REPAIR_PROPOSED")
    data = dict(PROOF_PASS, broken_run={"outcome": "failed", "failure_type": "ImportError"})
    r = send(client, hmac_secret, "regression_proof.verdict", inc_id, data=data)
    assert r.status_code == 422


def test_forced_verification_failure_ends_in_verification_failed(client, hmac_secret):
    """Acceptance #13: a failing gate ends the attempt with evidence; nothing reports success."""
    inc_id = "inc-verif-fail"
    drive_to(client, hmac_secret, inc_id, "REPAIR_PROPOSED")
    ok(send(client, hmac_secret, "integrity_gate.verdict", inc_id,
            data={"verdict": "FAIL", "findings": ["IG-02 added pytest.mark.skip"], "reason": "Integrity Gate blocked"},
            artifact_url="https://gitlab.com/sentinel/demo/-/jobs/55/artifacts/integrity.json"))
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["status"] == "VERIFICATION_FAILED"
    gate = inc["recovery_attempts"][-1]["gate_results"][-1]
    assert gate["verdict"] == "fail" and gate["report_ref"].endswith("integrity.json")
    # Terminal: a later merge or recovery claim cannot resurrect it.
    r = send(client, hmac_secret, "recovery.verified", inc_id, data={"verdict": "PASS"},
             source=EVALUATOR, commit_sha=FIX_SHA)
    assert r.status_code == 409


def test_rollback_requires_probe_result(client, hmac_secret):
    inc_id = "inc-probe"
    drive_to(client, hmac_secret, inc_id, "DETECTED")
    r = send(client, hmac_secret, "rollback.completed", inc_id, data={})
    assert r.status_code == 422
    ok(send(client, hmac_secret, "rollback.completed", inc_id, data={"post_rollback_probe_ok": False}))
    assert _status(client, inc_id) == "ROLLBACK_FAILED"


def test_detection_requires_measured_thresholds(client, hmac_secret):
    r = send(client, hmac_secret, "incident.detected", "inc-nomeasure", data={}, source=EVALUATOR)
    assert r.status_code == 422
    assert client.get("/api/v1/incidents/inc-nomeasure").status_code == 404


def test_evidence_requires_url_and_hash(client, hmac_secret):
    inc_id = "inc-evidence"
    drive_to(client, hmac_secret, inc_id, "ROLLED_BACK")
    r = send(client, hmac_secret, "evidence.collected", inc_id, data={"evidence_sha256": EVIDENCE_SHA})
    assert r.status_code == 422
    assert _status(client, inc_id) == "ROLLED_BACK"


def test_unknown_incident_is_retryable_and_not_swallowed(client, hmac_secret):
    """Out-of-order delivery: CI may retry the same job/type after the incident exists."""
    r = send(client, hmac_secret, "rollback.completed", "inc-late", data={"post_rollback_probe_ok": True}, job_id=5555)
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["retryable"] is True
    ok(send(client, hmac_secret, "incident.detected", "inc-late", data={"breached_thresholds": ["p95 > 300ms"]}))
    body = ok(send(client, hmac_secret, "rollback.completed", "inc-late",
                   data={"post_rollback_probe_ok": True}, job_id=5555))
    assert "note" not in body
    assert body["incident_status"] == "ROLLED_BACK"


def test_rejected_events_are_kept_in_the_ledger(client, hmac_secret):
    inc_id = "inc-ledger"
    drive_to(client, hmac_secret, inc_id, "DETECTED")
    send(client, hmac_secret, "recovery.verified", inc_id, data={"verdict": "PASS"}, source=EVALUATOR)
    timeline = client.get(f"/api/v1/incidents/{inc_id}/timeline").json()
    rejected = [e for e in timeline if e["rejected"]]
    assert len(rejected) == 1 and rejected[0]["type"] == "recovery.verified"
    assert rejected[0]["summary"].startswith("REJECTED INVALID_STATE_TRANSITION")


def test_detected_event_without_incident_id_appears_in_timeline(client, hmac_secret):
    body = ok(send(client, hmac_secret, "incident.detected", None,
                   data={"breached_thresholds": ["error_rate > 0.02"]}, job_id=4242))
    inc_id = body["incident_id"]
    assert inc_id == "inc-4242"
    timeline = client.get(f"/api/v1/incidents/{inc_id}/timeline").json()
    assert [e["type"] for e in timeline] == ["incident.detected"]


def test_deploy_of_another_commit_is_informational(client, hmac_secret):
    """Re-running the faulty release's deploy while the incident is open moves nothing."""
    inc_id = "inc-deploy-other"
    drive_to(client, hmac_secret, inc_id, "DETECTED")
    ok(send(client, hmac_secret, "deploy.canary_started", inc_id, data={"traffic_percent": 10}))
    assert _status(client, inc_id) == "DETECTED"
    types = [e["type"] for e in client.get(f"/api/v1/incidents/{inc_id}/timeline").json()]
    assert "deploy.canary_started" in types


def test_deploy_of_fix_before_merge_is_rejected(client, hmac_secret):
    inc_id = "inc-deploy-early"
    drive_to(client, hmac_secret, inc_id, "REPAIR_PROPOSED")
    r = send(client, hmac_secret, "deploy.canary_started", inc_id, data={"traffic_percent": 10}, commit_sha=FIX_SHA)
    assert r.status_code == 409
    assert _status(client, inc_id) == "REPAIR_PROPOSED"


def test_stale_fail_for_broken_commit_does_not_fail_the_redeploy(client, hmac_secret):
    inc_id = "inc-stale-fail"
    drive_to(client, hmac_secret, inc_id, "REDEPLOYING")
    ok(send(client, hmac_secret, "evaluator.verdict", inc_id, source=EVALUATOR, commit_sha=BROKEN_SHA,
            data={"verdict": "FAIL", "target": "candidate", "traffic_percent": 10}))
    assert _status(client, inc_id) == "REDEPLOYING"
    ok(send(client, hmac_secret, "evaluator.verdict", inc_id, source=EVALUATOR, commit_sha=FIX_SHA,
            data={"verdict": "FAIL", "target": "candidate", "traffic_percent": 10, "reason": "fix still failing"}))
    assert _status(client, inc_id) == "REDEPLOY_UNHEALTHY"
