"""
Investigation flow dispatch (Task R5).

When an incident reaches EVIDENCE_COLLECTED the backend starts the Duo investigation
flow exactly once per recovery attempt. All dispatch goes through `dispatch_flow()`
so the route proven by spike S1 can be swapped in one place:

  disabled   (default) backend does not start flows; a CI job starts it and emits
             `flow.started` (fallback route 2 / Duo CLI route 3).
  gitlab_api POST {GITLAB_API_URL}/ai/duo_workflows/workflows   (UNVERIFIED until S1:
             token type and custom-flow `workflow_definition` value are unknown)

The flow receives only the incident id and the evidence bundle URL + hash. Never secrets.
Runs as a FastAPI background task, so HTTP requests never wait on GitLab.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from app.config import settings
from app.models.entities import EventRecord, IncidentStatus
from app.persistence.factory import get_repository
from app.state_engine import STATE_LOCK, _apply_transition, process_event_state_transition

logger = logging.getLogger("sentinel.flow_dispatch")

DISPATCH_SOURCE = "sentinel/backend/flow_dispatcher"


@dataclass
class DispatchResult:
    ok: bool
    session_id: str | None = None
    error: str | None = None


def build_goal(incident_id: str, evidence_url: str | None, evidence_sha256: str | None) -> str:
    # Plain text only: no secrets, no Jinja-style double braces (they crash flows, see §A12).
    return (
        f"Investigate Sentinel incident {incident_id}. "
        f"Evidence bundle: {evidence_url} (sha256 {evidence_sha256}). "
        f"Write sentinel/incidents/{incident_id}/analysis.json and open a merge request "
        f"from branch duo/fix/{incident_id} with the fix and a regression test under tests/regressions/."
    )


def _dispatch_gitlab_api(goal: str) -> DispatchResult:
    if not (settings.gitlab_project_id and settings.gitlab_flow_token and settings.gitlab_flow_definition):
        return DispatchResult(ok=False, error="gitlab_api dispatch is not configured")
    url = settings.gitlab_api_url.rstrip("/") + "/ai/duo_workflows/workflows"
    body = {
        "project_id": settings.gitlab_project_id,
        "goal": goal,
        "workflow_definition": settings.gitlab_flow_definition,
        "start_workflow": True,
    }
    try:
        resp = httpx.post(
            url,
            json=body,
            headers={"PRIVATE-TOKEN": settings.gitlab_flow_token},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        return DispatchResult(ok=False, error=f"GitLab request failed: {type(exc).__name__}")
    if resp.status_code >= 300:
        # Never log the token; response text is truncated.
        return DispatchResult(ok=False, error=f"GitLab returned HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        payload = resp.json()
    except ValueError:
        return DispatchResult(ok=False, error="GitLab returned a non-JSON response")
    session_id = payload.get("id") or payload.get("workflow_id")
    if session_id is None:
        return DispatchResult(ok=False, error="GitLab response had no workflow id")
    return DispatchResult(ok=True, session_id=str(session_id))


def dispatch_flow(goal: str) -> DispatchResult | None:
    """Start the flow using the configured route. Returns None when dispatch is disabled."""
    mode = settings.flow_dispatch_mode.lower()
    if mode == "disabled":
        return None
    if mode == "gitlab_api":
        return _dispatch_gitlab_api(goal)
    return DispatchResult(ok=False, error=f"Unknown SENTINEL_FLOW_DISPATCH_MODE '{mode}'")


def _record(incident_id: str, etype: str, job_id: str, data: dict, summary: str) -> None:
    get_repository().save_event(
        EventRecord(
            id=f"evt-dispatch-{incident_id}-{etype.split('.')[-1]}-{job_id}",
            entity_type="Incident",
            entity_id=incident_id,
            type=etype,
            source=DISPATCH_SOURCE,
            source_job_id=job_id,
            at=datetime.now(UTC).isoformat(),
            data=data,
            summary=summary,
        )
    )


def maybe_dispatch(incident_id: str) -> None:
    """Start the investigation flow once per attempt. Safe to call repeatedly."""
    if settings.flow_dispatch_mode.lower() == "disabled":
        return
    repo = get_repository()
    inc = repo.get_incident(incident_id)
    if inc is None or inc.status != IncidentStatus.EVIDENCE_COLLECTED:
        return
    attempt_no = inc.recovery_attempts[-1].attempt_no if inc.recovery_attempts else 1
    if not repo.check_and_set_idempotency(f"dispatch:{incident_id}:{attempt_no}"):
        return  # already dispatched for this attempt

    result = dispatch_flow(build_goal(incident_id, inc.evidence_bundle_ref, inc.evidence_sha256))
    if result is None:
        return
    if result.ok:
        event = {
            "type": "flow.started",
            "source": DISPATCH_SOURCE,
            "incident_id": incident_id,
            "job_id": result.session_id,
            "data": {"flow_session_id": result.session_id},
        }
        try:
            process_event_state_transition(event)
        except HTTPException as exc:  # state moved underneath us; record, don't crash
            logger.warning("flow.started not applied for %s: %s", incident_id, exc)
            return
        _record(incident_id, "flow.started", result.session_id, {"flow_session_id": result.session_id},
                "Backend started the investigation flow.")
    else:
        logger.error("Flow dispatch failed for %s: %s", incident_id, result.error)
        try:
            # EVIDENCE_COLLECTED -> INVESTIGATION_FAILED
            with STATE_LOCK:
                inc = repo.get_incident(incident_id)
                _apply_transition(inc, "INVESTIGATION_FAILED", f"Flow dispatch failed: {result.error}")
                repo.save_incident(inc)
        except HTTPException as exc:
            logger.warning("Could not record dispatch failure for %s: %s", incident_id, exc)
            return
        _record(incident_id, "flow.dispatch_failed", f"dispatch-{attempt_no}", {"reason": result.error},
                "Backend could not start the investigation flow.")
