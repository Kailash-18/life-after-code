"""
Project Sentinel State Engine (Task R4).

Enforces the recovery-attempt state machine (§A6) and the source-of-truth rules (§A5).
Core principle: AI proposes; deterministic gates decide. The backend records truth;
it never creates it, so every forward transition requires the evidence named in §A5:

  DETECTED            incident.detected with measured breached thresholds
  ROLLED_BACK         rollback.completed with post_rollback_probe_ok == true
  EVIDENCE_COLLECTED  evidence.collected with artifact_url + evidence_sha256
  INVESTIGATING       flow.started with flow_session_id (deadline starts)
  REPAIR_PROPOSED     repair.proposed / GitLab MR webhook with mr_iid + fix_sha
  VERIFYING           regression_proof / integrity_gate verdicts being recorded
  MERGED              merge.completed AND regression proven both ways AND integrity PASS
                      (a merge without that evidence is recorded as ESCALATED)
  REDEPLOYING         deploy.canary_started / redeploy.completed
  RECOVERED           recovery.verified from the evaluator, PASS, for the fix SHA,
                      at 100% traffic when reported; the evaluator job id is recorded
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.config import settings
from app.models.entities import (
    EventRecord,
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


# Event types that can move an incident. Others (rollback.started, pipeline.started, ...)
# are recorded in the ledger but never change incident state.
STATE_EVENT_TYPES = {
    "incident.detected",
    "rollback.completed",
    "evidence.collected",
    "flow.started",
    "flow.completed",
    "repair.proposed",
    "regression_proof.verdict",
    "integrity_gate.verdict",
    "merge.completed",
    "deploy.canary_started",
    "redeploy.completed",
    "evaluator.verdict",
    "recovery.verified",
}


class _IncidentsStoreProxy(dict):
    """Read-through dict view of persisted incidents (kept for backward compatibility)."""

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


def _reject(code: str, message: str, http_status: int = status.HTTP_409_CONFLICT, retryable: bool = False):
    raise HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message, "retryable": retryable}},
    )


def _insufficient(message: str):
    _reject("INSUFFICIENT_EVIDENCE", message, 422)


def _sha_matches(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    return a.startswith(b) or b.startswith(a)


def _now() -> datetime:
    return datetime.now(UTC)


def _new_incident(incident_id: str, event: dict[str, Any], data: dict[str, Any]) -> Incident:
    breached = data.get("breached_thresholds") or []
    return Incident(
        id=incident_id,
        release_id=event.get("release_id") or f"rel-{event.get('commit_sha', 'unknown')[:12]}",
        status=IncidentStatus.DETECTED,
        detected_at=_now().isoformat(),
        breached_thresholds=[str(b) for b in breached],
        evidence_bundle_ref=event.get("artifact_url"),
        evidence_sha256=data.get("evidence_sha256"),
        recovery_attempts=[
            RecoveryAttempt(
                id=f"att-{incident_id}-1",
                incident_id=incident_id,
                attempt_no=1,
                state=RecoveryState.DETECTED,
            )
        ],
    )


def get_or_create_incident(
    incident_id: str, release_id: str | None = None, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    repo = get_repository()
    existing = repo.get_incident(incident_id)
    if existing:
        return existing.model_dump()
    inc = _new_incident(incident_id, {"release_id": release_id, "commit_sha": "unknown"}, data or {})
    repo.save_incident(inc)
    return inc.model_dump()


def _apply_transition(inc: Incident, target: str, reason: str | None = None) -> None:
    current = inc.status.value
    if target == current:
        return
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if target not in allowed:
        _reject(
            "INVALID_STATE_TRANSITION",
            f"Illegal state transition from {current} to {target}. Allowed next states: {allowed}.",
        )
    inc.status = IncidentStatus(target)
    if inc.recovery_attempts:
        att = inc.recovery_attempts[-1]
        att.state = (
            RecoveryState(target)
            if target in RecoveryState._value2member_map_
            else RecoveryState.FAILED
        )
        if target in TERMINAL_FAILURE_STATES:
            att.failure_reason = reason or f"Failed with {target}"


def _attempt(inc: Incident) -> RecoveryAttempt:
    if not inc.recovery_attempts:
        inc.recovery_attempts.append(
            RecoveryAttempt(id=f"att-{inc.id}-1", incident_id=inc.id, attempt_no=1)
        )
    return inc.recovery_attempts[-1]


def regression_proven(att: RecoveryAttempt) -> bool:
    broken_ok = any(
        t.kind == TestKind.REGRESSION_ON_BROKEN
        and t.outcome == TestOutcome.FAILED
        and t.failure_type == "AssertionError"
        for t in att.test_results
    )
    fix_ok = any(
        t.kind == TestKind.REGRESSION_ON_FIX and t.outcome == TestOutcome.PASSED
        for t in att.test_results
    )
    return broken_ok and fix_ok


def integrity_passed(att: RecoveryAttempt) -> bool:
    integrity = [g for g in att.gate_results if g.gate == GateKind.INTEGRITY]
    return bool(integrity) and integrity[-1].verdict == GateVerdict.PASS


def _record_regression_proof(att: RecoveryAttempt, event: dict[str, Any], data: dict[str, Any], verdict: str) -> None:
    broken = data.get("broken_run") or {}
    fix = data.get("fix_run") or {}
    job = event.get("job_id")
    junit = event.get("artifact_url")

    def outcome(run: dict[str, Any]) -> TestOutcome | None:
        o = str(run.get("outcome", "")).lower()
        return {"passed": TestOutcome.PASSED, "failed": TestOutcome.FAILED, "error": TestOutcome.ERROR}.get(o)

    if outcome(broken):
        att.test_results.append(
            TestResult(
                id=f"tst-{job}-broken",
                attempt_id=att.id,
                kind=TestKind.REGRESSION_ON_BROKEN,
                sha=str(data.get("broken_sha", "")),
                outcome=outcome(broken),
                failure_type=broken.get("failure_type"),
                junit_ref=junit,
            )
        )
    if outcome(fix):
        att.test_results.append(
            TestResult(
                id=f"tst-{job}-fix",
                attempt_id=att.id,
                kind=TestKind.REGRESSION_ON_FIX,
                sha=str(data.get("fix_sha") or event.get("commit_sha", "")),
                outcome=outcome(fix),
                failure_type=fix.get("failure_type"),
                junit_ref=junit,
            )
        )
    if verdict == "PASS" and not regression_proven(att):
        _insufficient(
            "regression_proof PASS requires data.broken_run {outcome: failed, failure_type: AssertionError} "
            "and data.fix_run {outcome: passed}."
        )


def process_event_state_transition(event: dict[str, Any]) -> dict[str, Any] | None:
    """
    Apply one authenticated CI event to its incident. Raises HTTPException (409/422)
    when the event would skip a state or lacks the evidence its transition requires;
    in that case nothing is persisted for the incident.
    """
    repo = get_repository()
    event_type = event.get("type")
    source = str(event.get("source", ""))
    incident_id = event.get("incident_id")
    data = event.get("data", {}) or {}

    if not incident_id and event_type == "incident.detected":
        incident_id = data.get("incident_id") or f"inc-{event.get('job_id')}"
        event["incident_id"] = incident_id

    if not incident_id:
        return None

    inc = repo.get_incident(incident_id)
    if event_type not in STATE_EVENT_TYPES:
        return inc.model_dump() if inc else None
    if inc is None:
        if event_type != "incident.detected":
            _reject(
                "UNKNOWN_INCIDENT",
                f"Incident {incident_id} has not been opened by an incident.detected event yet.",
                retryable=True,
            )
        if not data.get("breached_thresholds"):
            _insufficient("incident.detected requires measured data.breached_thresholds.")
        inc = _new_incident(incident_id, event, data)
        repo.save_incident(inc)
        return inc.model_dump()

    att = _attempt(inc)
    previous_status = inc.status.value

    if event_type == "incident.detected":
        _apply_transition(inc, "DETECTED")

    elif event_type == "rollback.completed":
        probe = data.get("post_rollback_probe_ok")
        if probe is True:
            _apply_transition(inc, "ROLLED_BACK")
        elif probe is False:
            _apply_transition(inc, "ROLLBACK_FAILED", data.get("reason") or "Post-rollback probe failed.")
        else:
            _insufficient("rollback.completed requires data.post_rollback_probe_ok (true/false).")

    elif event_type == "evidence.collected":
        if not event.get("artifact_url") or not data.get("evidence_sha256"):
            _insufficient("evidence.collected requires artifact_url and data.evidence_sha256.")
        inc.evidence_bundle_ref = event["artifact_url"]
        inc.evidence_sha256 = data["evidence_sha256"]
        _apply_transition(inc, "EVIDENCE_COLLECTED")

    elif event_type == "flow.started":
        if not data.get("flow_session_id"):
            _insufficient("flow.started requires data.flow_session_id.")
        _apply_transition(inc, "INVESTIGATING")
        att.flow_session_id = str(data["flow_session_id"])
        att.deadline_at = (_now() + timedelta(minutes=settings.flow_timeout_minutes)).isoformat()

    elif event_type == "flow.completed":
        if str(data.get("verdict", "")).upper() == "FAIL":
            _apply_transition(
                inc, "INVESTIGATION_FAILED", data.get("reason") or "Investigation flow reported failure."
            )

    elif event_type == "repair.proposed":
        if not data.get("mr_iid") or not data.get("fix_sha"):
            _insufficient("repair.proposed requires data.mr_iid and data.fix_sha.")
        _apply_transition(inc, "REPAIR_PROPOSED")
        att.mr_iid = int(data["mr_iid"])
        att.fix_sha = str(data["fix_sha"])

    elif event_type in ("regression_proof.verdict", "integrity_gate.verdict"):
        verdict = str(data.get("verdict", "")).upper()
        if verdict not in ("PASS", "FAIL"):
            _insufficient(f"{event_type} requires data.verdict PASS or FAIL.")
        if inc.status.value not in ("REPAIR_PROPOSED", "VERIFYING"):
            _reject(
                "INVALID_STATE_TRANSITION",
                f"Gate verdicts are only accepted in REPAIR_PROPOSED/VERIFYING, not {inc.status.value}.",
            )
        if event_type == "integrity_gate.verdict":
            att.gate_results.append(
                GateResult(
                    id=f"gte-{event.get('job_id')}",
                    attempt_id=att.id,
                    gate=GateKind.INTEGRITY,
                    verdict=GateVerdict.PASS if verdict == "PASS" else GateVerdict.FAIL,
                    findings=[str(f) for f in data.get("findings", [])],
                    report_ref=event.get("artifact_url"),
                )
            )
        else:
            _record_regression_proof(att, event, data, verdict)
        if verdict == "FAIL":
            _apply_transition(
                inc, "VERIFICATION_FAILED", data.get("reason") or f"{event_type} reported FAIL."
            )
        else:
            _apply_transition(inc, "VERIFYING")

    elif event_type == "merge.completed":
        if inc.status.value == "VERIFYING" and regression_proven(att) and integrity_passed(att):
            _apply_transition(inc, "MERGED")
        else:
            missing = []
            if not regression_proven(att):
                missing.append("regression proof (fails on broken, passes on fix)")
            if not integrity_passed(att):
                missing.append("Integrity Gate PASS")
            if inc.status.value != "VERIFYING":
                missing.append(f"VERIFYING state (was {inc.status.value})")
            _apply_transition(
                inc, "ESCALATED", "Merge reported without required gate evidence: " + ", ".join(missing)
            )

    elif event_type in ("deploy.canary_started", "redeploy.completed"):
        _apply_transition(inc, "REDEPLOYING")

    elif event_type == "evaluator.verdict":
        if inc.status.value == "REDEPLOYING" and str(data.get("verdict", "")).upper() == "FAIL":
            _apply_transition(
                inc, "REDEPLOY_UNHEALTHY", data.get("reason") or "Evaluator failed the fix release canary."
            )

    elif event_type == "recovery.verified":
        if "evaluator" not in source.lower():
            _reject(
                "UNAUTHORITATIVE_SOURCE",
                f"Source '{source}' is not authoritative for declaring recovery. "
                "Only the post-deploy evaluator may verify recovery.",
                status.HTTP_400_BAD_REQUEST,
            )
        verdict = str(data.get("verdict", "")).upper()
        if verdict == "PASS":
            if "RECOVERED" not in ALLOWED_TRANSITIONS.get(inc.status.value, []):
                _apply_transition(inc, "RECOVERED")  # raises INVALID_STATE_TRANSITION
            if not _sha_matches(event.get("commit_sha"), att.fix_sha):
                _reject(
                    "WRONG_RELEASE",
                    "recovery.verified must evaluate the fix release "
                    f"(fix_sha={att.fix_sha!r}, event commit_sha={event.get('commit_sha')!r}).",
                )
            pct = data.get("traffic_percent")
            if pct is not None and pct != 100:
                _insufficient(f"Recovery requires a passing evaluation at 100% traffic, got {pct}%.")
            _apply_transition(inc, "RECOVERED")
        elif verdict == "FAIL":
            _apply_transition(
                inc, "REDEPLOY_UNHEALTHY", data.get("reason") or "Post-redeploy evaluation failed."
            )
        else:
            _insufficient("recovery.verified requires data.verdict PASS or FAIL.")

    repo.save_incident(inc)
    _snapshot_state(event_type, incident_id, f"{previous_status} -> {inc.status.value}")
    return inc.model_dump()


def _snapshot_state(event_type: str | None, incident_id: str, transition: str) -> None:
    """Best-effort state snapshot (Kailash's S3 state store). Never blocks or fails ingestion."""
    try:
        from app.s3_state_store import s3_state_store

        s3_state_store.snapshot_state(
            INCIDENTS_STORE,
            extra_metadata={"last_event_type": event_type, "incident_id": incident_id, "transition": transition},
        )
    except Exception as exc:  # noqa: BLE001 - snapshots are optional; ingestion must not fail
        logging.getLogger("sentinel.state_engine").warning("State snapshot skipped: %s", exc)


def expire_overdue_attempts() -> list[str]:
    """
    Move INVESTIGATING incidents whose flow deadline has passed to TIMED_OUT.
    Called on reads and writes (Cloud Run has no background scheduler).
    Returns the ids of incidents that timed out.
    """
    repo = get_repository()
    expired: list[str] = []
    now = _now()
    for inc in repo.list_incidents(status=IncidentStatus.INVESTIGATING.value):
        att = inc.recovery_attempts[-1] if inc.recovery_attempts else None
        if not att or not att.deadline_at:
            continue
        try:
            deadline = datetime.fromisoformat(att.deadline_at)
        except ValueError:
            continue
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if deadline > now:
            continue
        _apply_transition(
            inc,
            "TIMED_OUT",
            f"Investigation flow {att.flow_session_id} did not propose a repair before {att.deadline_at}.",
        )
        repo.save_incident(inc)
        repo.save_event(
            EventRecord(
                id=f"evt-timeout-{inc.id}-{att.attempt_no}",
                entity_type="Incident",
                entity_id=inc.id,
                type="flow.timed_out",
                source="sentinel/backend/deadline",
                source_job_id=str(att.flow_session_id or ""),
                at=now.isoformat(),
                data={"deadline_at": att.deadline_at},
                summary="Investigation deadline passed without a repair proposal.",
            )
        )
        expired.append(inc.id)
    return expired
