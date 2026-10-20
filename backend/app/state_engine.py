"""
Project Sentinel State Engine.
Enforces the 11-step recovery loop state machine and authoritative source validation.
Core principle: AI proposes; deterministic gates decide.
"""

from typing import Any

from fastapi import HTTPException, status

VALID_LIFECYCLE_STATES = [
    "DETECTED",
    "ROLLED_BACK",
    "EVIDENCE_COLLECTED",
    "INVESTIGATING",
    "REPAIR_PROPOSED",
    "VERIFYING",
    "MERGED",
    "REDEPLOYING",
    "RECOVERED",
]

TERMINAL_FAILURE_STATES = [
    "ROLLBACK_FAILED",
    "INVESTIGATION_FAILED",
    "VERIFICATION_FAILED",
    "REDEPLOY_UNHEALTHY",
    "TIMED_OUT",
    "ESCALATED",
]

ALLOWED_TRANSITIONS = {
    "DETECTED": ["ROLLED_BACK", "ROLLBACK_FAILED", "ESCALATED"],
    "ROLLED_BACK": ["EVIDENCE_COLLECTED", "INVESTIGATION_FAILED", "ESCALATED"],
    "EVIDENCE_COLLECTED": ["INVESTIGATING", "INVESTIGATION_FAILED", "ESCALATED"],
    "INVESTIGATING": [
        "REPAIR_PROPOSED",
        "INVESTIGATION_FAILED",
        "TIMED_OUT",
        "ESCALATED",
    ],
    "REPAIR_PROPOSED": ["VERIFYING", "VERIFICATION_FAILED", "ESCALATED"],
    "VERIFYING": ["MERGED", "VERIFICATION_FAILED", "ESCALATED"],
    "MERGED": ["REDEPLOYING", "ESCALATED"],
    "REDEPLOYING": ["RECOVERED", "REDEPLOY_UNHEALTHY", "ESCALATED"],
}

# In-memory incident and attempt state storage for Sentinel API
INCIDENTS_STORE: dict[str, dict[str, Any]] = {}


def get_or_create_incident(
    incident_id: str, release_id: str | None = None, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    if incident_id not in INCIDENTS_STORE:
        INCIDENTS_STORE[incident_id] = {
            "id": incident_id,
            "release_id": release_id or "rel-unknown",
            "status": "DETECTED",
            "detected_at": data.get("detected_at") if data else None,
            "breached_thresholds": (data.get("breached_thresholds") if data else [])
            or [],
            "evidence_bundle_ref": data.get("evidence_bundle_ref") if data else None,
            "evidence_sha256": data.get("evidence_sha256") if data else None,
            "recovery_attempts": [
                {
                    "id": f"att-{incident_id}-1",
                    "incident_id": incident_id,
                    "attempt_no": 1,
                    "state": "DETECTED",
                    "test_results": [],
                    "gate_results": [],
                }
            ],
        }
    return INCIDENTS_STORE[incident_id]


def process_event_state_transition(event: dict[str, Any]) -> dict[str, Any] | None:
    """
    Evaluates an ingested CI event against authoritative source rules
    and enforces state machine progression without skipping states.
    """
    event_type = event.get("type")
    source = event.get("source", "")
    incident_id = event.get("incident_id")
    data = event.get("data", {}) or {}

    if not incident_id and event_type == "incident.detected":
        incident_id = data.get("incident_id") or f"inc-{event.get('job_id')}"
        event["incident_id"] = incident_id

    if not incident_id:
        # Non-incident event (e.g. general pipeline or deploy without incident)
        return None

    incident = get_or_create_incident(
        incident_id, release_id=event.get("release_id"), data=data
    )
    current_status = incident["status"]
    target_status = None

    # Map events to target status and check authoritative sources
    if event_type == "incident.detected":
        target_status = "DETECTED"
        if data.get("breached_thresholds"):
            incident["breached_thresholds"] = data["breached_thresholds"]
        if event.get("artifact_url"):
            incident["evidence_bundle_ref"] = event.get("artifact_url")
            incident["evidence_sha256"] = data.get("evidence_sha256")

    elif event_type == "rollback.completed":
        # Authoritative: Rollback job + post-rollback probe
        probe_ok = data.get("post_rollback_probe_ok", True)
        target_status = "ROLLED_BACK" if probe_ok else "ROLLBACK_FAILED"

    elif event_type == "evidence.collected":
        target_status = "EVIDENCE_COLLECTED"
        if event.get("artifact_url"):
            incident["evidence_bundle_ref"] = event.get("artifact_url")
        if data.get("evidence_sha256"):
            incident["evidence_sha256"] = data.get("evidence_sha256")

    elif event_type == "flow.started":
        target_status = "INVESTIGATING"
        if data.get("flow_session_id") and incident["recovery_attempts"]:
            incident["recovery_attempts"][-1]["flow_session_id"] = data[
                "flow_session_id"
            ]

    elif event_type == "repair.proposed":
        target_status = "REPAIR_PROPOSED"
        if incident["recovery_attempts"]:
            att = incident["recovery_attempts"][-1]
            att["mr_iid"] = data.get("mr_iid")
            att["fix_sha"] = data.get("fix_sha")

    elif event_type in ("regression_proof.verdict", "integrity_gate.verdict"):
        verdict = data.get("verdict", "").upper()
        if verdict in ("FAIL", "FAILED"):
            target_status = "VERIFICATION_FAILED"
        else:
            target_status = "VERIFYING"
        if incident["recovery_attempts"]:
            att = incident["recovery_attempts"][-1]
            if event_type == "integrity_gate.verdict":
                att["gate_results"].append(
                    {
                        "id": f"gte-{event.get('job_id')}",
                        "attempt_id": att["id"],
                        "gate": "integrity",
                        "verdict": verdict.lower(),
                        "findings": data.get("findings", []),
                        "report_ref": event.get("artifact_url"),
                    }
                )
            else:
                att["test_results"].append(
                    {
                        "id": f"tst-{event.get('job_id')}",
                        "attempt_id": att["id"],
                        "kind": data.get("kind", "regression_on_fix"),
                        "sha": event.get("commit_sha"),
                        "outcome": verdict,
                    }
                )

    elif event_type == "merge.completed":
        target_status = "MERGED"

    elif event_type in ("deploy.canary_started", "redeploy.completed"):
        target_status = "REDEPLOYING"

    elif event_type == "recovery.verified":
        # CRITICAL AUTHORITATIVE CHECK:
        # §A5: Only a post-redeploy evaluator job can declare RECOVERED.
        # AI output or generic CI jobs cannot declare recovery.
        is_evaluator_source = "evaluator" in source.lower()
        verdict = data.get("verdict", "").upper()

        if not is_evaluator_source:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "UNAUTHORITATIVE_SOURCE",
                        "message": f"Source '{source}' is not authoritative for declaring recovery. Only post-deploy evaluator may verify recovery.",
                        "retryable": False,
                    }
                },
            )

        if verdict == "PASS":
            target_status = "RECOVERED"
        else:
            target_status = "REDEPLOY_UNHEALTHY"

    if not target_status or target_status == current_status:
        return incident

    # Enforce state machine transitions: no skipped states
    allowed_next_states = ALLOWED_TRANSITIONS.get(current_status, [])
    if target_status not in allowed_next_states:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "INVALID_STATE_TRANSITION",
                    "message": f"Illegal state transition from {current_status} to {target_status}. Allowed next states: {allowed_next_states}.",
                    "retryable": False,
                }
            },
        )

    # Transition state
    incident["status"] = target_status
    if incident["recovery_attempts"]:
        incident["recovery_attempts"][-1]["state"] = target_status
        if target_status in TERMINAL_FAILURE_STATES:
            incident["recovery_attempts"][-1]["failure_reason"] = data.get(
                "reason", f"Failed with {target_status}"
            )

    # Enterprise S3 State Synchronization
    try:
        from app.s3_state_store import s3_state_store

        s3_state_store.snapshot_state(
            INCIDENTS_STORE,
            extra_metadata={
                "last_event_type": event_type,
                "incident_id": incident_id,
                "transition": f"{current_status} -> {target_status}",
            },
        )
    except Exception:
        pass

    return incident

