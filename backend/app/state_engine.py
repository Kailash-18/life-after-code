"""
Project Sentinel State Engine.
Enforces the 11-step recovery loop state machine and authoritative source validation.
Core principle: AI proposes; deterministic gates decide.
Integrated with the persistence layer (SentinelRepository).
"""

from typing import Any

from fastapi import HTTPException, status

from app.models.entities import (
    GateKind,
    GateResult,
    GateVerdict,
    Incident,
    IncidentStatus,
    RecoveryAttempt,
    RecoveryState,
    TestKind,
    TestOutcome,
    TestResult,
)
from app.persistence.factory import get_repository

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

class _IncidentsStoreProxy(dict):
    """Dynamic dict proxy backed by SentinelRepository for backward compatibility."""

    def __getitem__(self, key: str):
        inc = get_repository().get_incident(key)
        if inc is not None:
            return inc.model_dump()
        return super().__getitem__(key)

    def __contains__(self, key: object):
        if isinstance(key, str) and get_repository().get_incident(key) is not None:
            return True
        return super().__contains__(key)

    def get(self, key: str, default=None):
        inc = get_repository().get_incident(key)
        if inc is not None:
            return inc.model_dump()
        return super().get(key, default)

    def values(self):
        repo_incs = get_repository().list_incidents()
        if repo_incs:
            return [inc.model_dump() for inc in repo_incs]
        return super().values()


INCIDENTS_STORE: dict[str, dict[str, Any]] = _IncidentsStoreProxy()


def _sync_to_legacy_dict(incident: Incident) -> dict[str, Any]:
    """Sync an Incident domain model to the legacy dict representation."""
    d = incident.model_dump()
    dict.__setitem__(INCIDENTS_STORE, incident.id, d)
    return d



def get_or_create_incident(
    incident_id: str, release_id: str | None = None, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    repo = get_repository()
    existing = repo.get_incident(incident_id)
    if existing:
        return _sync_to_legacy_dict(existing)

    # Create new incident
    rel_id = release_id or "rel-unknown"
    breached = (data.get("breached_thresholds") if data else []) or []
    if isinstance(breached, list) and breached and isinstance(breached[0], dict):
        import json

        breached = [json.dumps(b) for b in breached]

    new_inc = Incident(
        id=incident_id,
        release_id=rel_id,
        status=IncidentStatus.DETECTED,
        detected_at=data.get("detected_at") if data and data.get("detected_at") else None or "",
        breached_thresholds=breached,
        evidence_bundle_ref=data.get("evidence_bundle_ref") if data else None,
        evidence_sha256=data.get("evidence_sha256") if data else None,
        recovery_attempts=[
            RecoveryAttempt(
                id=f"att-{incident_id}-1",
                incident_id=incident_id,
                attempt_no=1,
                state=RecoveryState.DETECTED,
                test_results=[],
                gate_results=[],
            )
        ],
    )
    repo.save_incident(new_inc)
    return _sync_to_legacy_dict(new_inc)


def process_event_state_transition(event: dict[str, Any]) -> dict[str, Any] | None:
    """
    Evaluates an ingested CI event against authoritative source rules
    and enforces state machine progression without skipping states.
    Persists updates via SentinelRepository.
    """
    repo = get_repository()
    event_type = event.get("type")
    source = event.get("source", "")
    incident_id = event.get("incident_id")
    data = event.get("data", {}) or {}

    if not incident_id and event_type == "incident.detected":
        incident_id = data.get("incident_id") or f"inc-{event.get('job_id')}"
        event["incident_id"] = incident_id

    if not incident_id:
        return None

    # Fetch incident from persistence layer
    inc_model = repo.get_incident(incident_id)
    if not inc_model:
        get_or_create_incident(
            incident_id, release_id=event.get("release_id"), data=data
        )
        inc_model = repo.get_incident(incident_id)

    if not inc_model:
        return None

    current_status = inc_model.status.value
    target_status = None

    # Map events to target status and check authoritative sources
    if event_type == "incident.detected":
        target_status = "DETECTED"
        if data.get("breached_thresholds"):
            inc_model.breached_thresholds = data["breached_thresholds"]
        if event.get("artifact_url"):
            inc_model.evidence_bundle_ref = event.get("artifact_url")
            inc_model.evidence_sha256 = data.get("evidence_sha256")

    elif event_type == "rollback.completed":
        # Authoritative: Rollback job + post-rollback probe
        probe_ok = data.get("post_rollback_probe_ok", True)
        target_status = "ROLLED_BACK" if probe_ok else "ROLLBACK_FAILED"

    elif event_type == "evidence.collected":
        target_status = "EVIDENCE_COLLECTED"
        if event.get("artifact_url"):
            inc_model.evidence_bundle_ref = event.get("artifact_url")
        if data.get("evidence_sha256"):
            inc_model.evidence_sha256 = data.get("evidence_sha256")

    elif event_type == "flow.started":
        target_status = "INVESTIGATING"
        if data.get("flow_session_id") and inc_model.recovery_attempts:
            inc_model.recovery_attempts[-1].flow_session_id = data["flow_session_id"]

    elif event_type == "repair.proposed":
        target_status = "REPAIR_PROPOSED"
        if inc_model.recovery_attempts:
            att = inc_model.recovery_attempts[-1]
            att.mr_iid = data.get("mr_iid")
            att.fix_sha = data.get("fix_sha")

    elif event_type in ("regression_proof.verdict", "integrity_gate.verdict"):
        verdict = data.get("verdict", "").upper()
        if verdict in ("FAIL", "FAILED"):
            target_status = "VERIFICATION_FAILED"
        else:
            target_status = "VERIFYING"
        if inc_model.recovery_attempts:
            att = inc_model.recovery_attempts[-1]
            if event_type == "integrity_gate.verdict":
                gr_verdict = GateVerdict.PASS if verdict == "PASS" else GateVerdict.FAIL
                att.gate_results.append(
                    GateResult(
                        id=f"gte-{event.get('job_id')}",
                        attempt_id=att.id,
                        gate=GateKind.INTEGRITY,
                        verdict=gr_verdict,
                        findings=data.get("findings", []),
                        report_ref=event.get("artifact_url"),
                    )
                )
            else:
                tr_outcome = TestOutcome.PASSED if verdict == "PASS" else TestOutcome.FAILED
                att.test_results.append(
                    TestResult(
                        id=f"tst-{event.get('job_id')}",
                        attempt_id=att.id,
                        kind=TestKind.REGRESSION_ON_FIX,
                        sha=event.get("commit_sha", ""),
                        outcome=tr_outcome,
                    )
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
        repo.save_incident(inc_model)
        return _sync_to_legacy_dict(inc_model)

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

    # Transition state and persist
    inc_model.status = IncidentStatus(target_status)
    if inc_model.recovery_attempts:
        inc_model.recovery_attempts[-1].state = (
            RecoveryState(target_status)
            if target_status in RecoveryState._value2member_map_
            else RecoveryState.FAILED
        )
        if target_status in TERMINAL_FAILURE_STATES:
            inc_model.recovery_attempts[-1].failure_reason = data.get(
                "reason", f"Failed with {target_status}"
            )

    repo.save_incident(inc_model)
    return _sync_to_legacy_dict(inc_model)
