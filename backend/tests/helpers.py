"""Shared helpers for driving signed CI events through the real HTTP endpoint."""

import itertools
import json
from datetime import UTC, datetime

from tests.conftest import generate_signature

BROKEN_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
FIX_SHA = "f00dfeed1234567890abcdef1234567890abcdef"
EVIDENCE_SHA = "ab" * 32
EVIDENCE_URL = "https://gitlab.com/sentinel/demo/-/jobs/103/artifacts/evidence.tar.gz"

_job_ids = itertools.count(10_000)


def send(
    client,
    secret,
    event_type,
    incident_id=None,
    data=None,
    source="sentinel/ci/job",
    commit_sha=BROKEN_SHA,
    artifact_url=None,
    release_id=None,
    job_id=None,
):
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "type": event_type,
        "source": source,
        "pipeline_id": "999",
        "job_id": str(job_id if job_id is not None else next(_job_ids)),
        "commit_sha": commit_sha,
        "sent_at": now_iso,
        "data": data or {},
    }
    if incident_id:
        payload["incident_id"] = incident_id
    if artifact_url:
        payload["artifact_url"] = artifact_url
    if release_id:
        payload["release_id"] = release_id
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-Sentinel-Signature": generate_signature(secret, body),
        "X-Sentinel-Timestamp": now_iso,
        "Content-Type": "application/json",
    }
    return client.post("/api/v1/events", content=body, headers=headers)


def ok(resp):
    assert resp.status_code == 202, resp.text
    return resp.json()


PROOF_PASS = {
    "verdict": "PASS",
    "broken_sha": BROKEN_SHA,
    "fix_sha": FIX_SHA,
    "broken_run": {"outcome": "failed", "failure_type": "AssertionError"},
    "fix_run": {"outcome": "passed"},
}

# Ordered steps of the happy path; drive_to() replays them up to a target state.
HAPPY_PATH = [
    ("DETECTED", "incident.detected", {"breached_thresholds": ["error_rate 0.08 > 0.02"]}, {"source": "sentinel/scripts/evaluator.py"}),
    ("ROLLED_BACK", "rollback.completed", {"post_rollback_probe_ok": True}, {}),
    ("EVIDENCE_COLLECTED", "evidence.collected", {"evidence_sha256": EVIDENCE_SHA}, {"artifact_url": EVIDENCE_URL}),
    ("INVESTIGATING", "flow.started", {"flow_session_id": "duo-session-001"}, {}),
    ("REPAIR_PROPOSED", "repair.proposed", {"mr_iid": 12, "fix_sha": FIX_SHA}, {}),
    ("VERIFYING", "regression_proof.verdict", PROOF_PASS, {"commit_sha": FIX_SHA}),
    ("VERIFYING", "integrity_gate.verdict", {"verdict": "PASS", "findings": []}, {"commit_sha": FIX_SHA}),
    ("MERGED", "merge.completed", {}, {"commit_sha": FIX_SHA}),
    ("REDEPLOYING", "deploy.canary_started", {"traffic_percent": 10}, {"commit_sha": FIX_SHA}),
    (
        "RECOVERED",
        "recovery.verified",
        {"verdict": "PASS", "target": "candidate", "traffic_percent": 100, "error_rate": 0.001, "p95_ms": 40.0, "sample_size": 500},
        {"source": "sentinel/scripts/evaluator.py", "commit_sha": FIX_SHA},
    ),
]


def drive_to(client, secret, incident_id, target_state):
    """Replay the happy path until the incident reaches target_state (inclusive)."""
    reached = False
    for state, etype, data, extra in HAPPY_PATH:
        if reached and state != target_state:
            break
        body = ok(send(client, secret, etype, incident_id, data=data, **extra))
        assert body["incident_status"] == state, (etype, body)
        if state == target_state:
            reached = True
    assert reached, f"target {target_state} not in happy path"
