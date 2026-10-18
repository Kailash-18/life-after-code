import json
from datetime import UTC, datetime

from app.state_engine import INCIDENTS_STORE

from tests.conftest import generate_signature


def send_signed_event(
    client, hmac_secret, event_type, source, job_id, incident_id, data=None
):
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "type": event_type,
        "source": source,
        "pipeline_id": "999",
        "job_id": str(job_id),
        "commit_sha": "c9aaa1f",
        "incident_id": incident_id,
        "sent_at": now_iso,
        "data": data or {},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = generate_signature(hmac_secret, body_bytes)
    headers = {
        "X-Sentinel-Signature": sig,
        "X-Sentinel-Timestamp": now_iso,
        "Content-Type": "application/json",
    }
    return client.post("/api/v1/events", content=body_bytes, headers=headers)


def test_recovery_lifecycle_happy_path(client, hmac_secret):
    inc_id = "inc-lifecycle-test-01"

    # 1. incident.detected -> DETECTED
    r = send_signed_event(
        client,
        hmac_secret,
        "incident.detected",
        "sentinel/scripts/evaluator.py",
        101,
        inc_id,
        {"breached_thresholds": ["error_rate > 0.02"]},
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "DETECTED"

    # 2. rollback.completed -> ROLLED_BACK
    r = send_signed_event(
        client,
        hmac_secret,
        "rollback.completed",
        "sentinel/ci/rollback",
        102,
        inc_id,
        {"post_rollback_probe_ok": True},
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "ROLLED_BACK"

    # 3. evidence.collected -> EVIDENCE_COLLECTED
    r = send_signed_event(
        client,
        hmac_secret,
        "evidence.collected",
        "sentinel/scripts/evidence.py",
        103,
        inc_id,
        {
            "evidence_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        },
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "EVIDENCE_COLLECTED"

    # 4. flow.started -> INVESTIGATING
    r = send_signed_event(
        client,
        hmac_secret,
        "flow.started",
        "sentinel/backend/flow_dispatcher",
        104,
        inc_id,
        {"flow_session_id": "duo-session-001"},
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "INVESTIGATING"

    # 5. repair.proposed -> REPAIR_PROPOSED
    r = send_signed_event(
        client,
        hmac_secret,
        "repair.proposed",
        "gitlab/duo/flow",
        105,
        inc_id,
        {"mr_iid": 12, "fix_sha": "d91e4f2"},
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "REPAIR_PROPOSED"

    # 6. regression_proof.verdict / integrity_gate.verdict -> VERIFYING
    r = send_signed_event(
        client,
        hmac_secret,
        "integrity_gate.verdict",
        "sentinel/scripts/integrity_gate.py",
        106,
        inc_id,
        {"verdict": "PASS"},
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "VERIFYING"

    # 7. merge.completed -> MERGED
    r = send_signed_event(
        client, hmac_secret, "merge.completed", "gitlab-ci/auto_merge", 107, inc_id
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "MERGED"

    # 8. deploy.canary_started -> REDEPLOYING
    r = send_signed_event(
        client, hmac_secret, "deploy.canary_started", "sentinel/ci/deploy", 108, inc_id
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "REDEPLOYING"

    # 9. recovery.verified from authoritative evaluator PASS -> RECOVERED
    r = send_signed_event(
        client,
        hmac_secret,
        "recovery.verified",
        "sentinel/scripts/evaluator.py",
        109,
        inc_id,
        {"verdict": "PASS", "target": "candidate"},
    )
    assert r.status_code == 202
    assert INCIDENTS_STORE[inc_id]["status"] == "RECOVERED"


def test_cannot_skip_states_to_recovered(client, hmac_secret):
    inc_id = "inc-skip-test-01"

    # Step 1: Create incident in DETECTED state
    send_signed_event(
        client,
        hmac_secret,
        "incident.detected",
        "sentinel/scripts/evaluator.py",
        201,
        inc_id,
    )
    assert INCIDENTS_STORE[inc_id]["status"] == "DETECTED"

    # Attempt to jump straight from DETECTED to RECOVERED -> must be rejected with 409
    r = send_signed_event(
        client,
        hmac_secret,
        "recovery.verified",
        "sentinel/scripts/evaluator.py",
        202,
        inc_id,
        {"verdict": "PASS"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert INCIDENTS_STORE[inc_id]["status"] == "DETECTED"


def test_unauthoritative_source_cannot_declare_recovery(client, hmac_secret):
    inc_id = "inc-unauth-test-01"

    # Bring state to REDEPLOYING
    send_signed_event(
        client,
        hmac_secret,
        "incident.detected",
        "sentinel/scripts/evaluator.py",
        301,
        inc_id,
    )
    send_signed_event(
        client, hmac_secret, "rollback.completed", "sentinel/ci/rollback", 302, inc_id
    )
    send_signed_event(
        client,
        hmac_secret,
        "evidence.collected",
        "sentinel/scripts/evidence.py",
        303,
        inc_id,
    )
    send_signed_event(
        client,
        hmac_secret,
        "flow.started",
        "sentinel/backend/flow_dispatcher",
        304,
        inc_id,
    )
    send_signed_event(
        client, hmac_secret, "repair.proposed", "gitlab/duo/flow", 305, inc_id
    )
    send_signed_event(
        client,
        hmac_secret,
        "integrity_gate.verdict",
        "sentinel/scripts/integrity_gate.py",
        306,
        inc_id,
        {"verdict": "PASS"},
    )
    send_signed_event(
        client, hmac_secret, "merge.completed", "gitlab-ci/auto_merge", 307, inc_id
    )
    send_signed_event(
        client, hmac_secret, "deploy.canary_started", "sentinel/ci/deploy", 308, inc_id
    )
    assert INCIDENTS_STORE[inc_id]["status"] == "REDEPLOYING"

    # AI flow or non-evaluator source attempts to declare recovery
    r = send_signed_event(
        client,
        hmac_secret,
        "recovery.verified",
        "gitlab/duo/agent",
        309,
        inc_id,
        {"verdict": "PASS"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "UNAUTHORITATIVE_SOURCE"
    assert INCIDENTS_STORE[inc_id]["status"] == "REDEPLOYING"


def test_evaluator_fail_transitions_to_redeploy_unhealthy(client, hmac_secret):
    inc_id = "inc-fail-eval-01"

    # Bring state to REDEPLOYING
    send_signed_event(
        client,
        hmac_secret,
        "incident.detected",
        "sentinel/scripts/evaluator.py",
        401,
        inc_id,
    )
    send_signed_event(
        client, hmac_secret, "rollback.completed", "sentinel/ci/rollback", 402, inc_id
    )
    send_signed_event(
        client,
        hmac_secret,
        "evidence.collected",
        "sentinel/scripts/evidence.py",
        403,
        inc_id,
    )
    send_signed_event(
        client,
        hmac_secret,
        "flow.started",
        "sentinel/backend/flow_dispatcher",
        404,
        inc_id,
    )
    send_signed_event(
        client, hmac_secret, "repair.proposed", "gitlab/duo/flow", 405, inc_id
    )
    send_signed_event(
        client,
        hmac_secret,
        "integrity_gate.verdict",
        "sentinel/scripts/integrity_gate.py",
        406,
        inc_id,
        {"verdict": "PASS"},
    )
    send_signed_event(
        client, hmac_secret, "merge.completed", "gitlab-ci/auto_merge", 407, inc_id
    )
    send_signed_event(
        client, hmac_secret, "deploy.canary_started", "sentinel/ci/deploy", 408, inc_id
    )
    assert INCIDENTS_STORE[inc_id]["status"] == "REDEPLOYING"

    # Evaluator reports FAIL on fix
    r = send_signed_event(
        client,
        hmac_secret,
        "recovery.verified",
        "sentinel/scripts/evaluator.py",
        409,
        inc_id,
        {"verdict": "FAIL", "reason": "Candidate error rate still 5%"},
    )
    assert r.status_code == 202
    assert (
        INCIDENTS_STORE[inc_id]["status"] == "REDEPLOYY_UNHEALTHY"
        or INCIDENTS_STORE[inc_id]["status"] == "REDEPLOY_UNHEALTHY"
    )
