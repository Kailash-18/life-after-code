"""
GitLab Webhook Ingestion Route (Task R3).

- Authenticated with X-Gitlab-Token (constant-time compare).
- Idempotent per (object_kind, entity id, status/action).
- Payloads are sanitized (sensitive keys + secret-looking values masked) before storage.
- Repair MRs on branches `duo/fix/<incident_id>` drive the incident state machine,
  because GitLab (not the AI) is authoritative for "MR opened" and "MR merged":
    action=open   -> repair.proposed (mr_iid, fix_sha = MR head commit)
    action=merge  -> merge.completed (still subject to the gate-evidence checks)
- Always answers 2xx once authenticated: GitLab disables hooks that keep failing,
  so state-machine rejections are recorded in the ledger instead of returned as errors.
"""

import hmac
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.analysis_ingest import ingest_analysis
from app.config import settings
from app.models.entities import EventRecord
from app.persistence.factory import get_repository
from app.security import sanitize_for_storage
from app.state_engine import process_event_state_transition
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

REPAIR_BRANCH = re.compile(r"^duo/fix/([A-Za-z0-9_-]+)$")


def incident_for_branch(branch: str | None) -> str | None:
    """Map `duo/fix/<id>` to an existing incident id (tolerates a doubled `inc-` prefix)."""
    if not branch:
        return None
    m = REPAIR_BRANCH.match(branch)
    if not m:
        return None
    raw = m.group(1)
    candidates = [raw, f"inc-{raw}"]
    if raw.startswith("inc-inc-"):
        candidates.insert(0, raw[4:])
    repo = get_repository()
    for cand in candidates:
        if repo.get_incident(cand) is not None:
            return cand
    return None


def _apply_mr_event(attrs: dict[str, Any], entity_id: str) -> tuple[str | None, dict[str, Any] | None]:
    """Returns (incident_id, outcome) where outcome describes what the state machine did."""
    incident_id = incident_for_branch(attrs.get("source_branch"))
    if not incident_id:
        return None, None
    action = attrs.get("action")
    if action == "open":
        event_type = "repair.proposed"
        data = {"mr_iid": attrs.get("iid"), "fix_sha": (attrs.get("last_commit") or {}).get("id")}
    elif action == "merge":
        event_type = "merge.completed"
        data = {"mr_iid": attrs.get("iid")}
    else:
        return incident_id, None
    event = {
        "type": event_type,
        "source": "gitlab/webhook",
        "incident_id": incident_id,
        "job_id": f"mr-{entity_id}-{action}",
        "commit_sha": (attrs.get("last_commit") or {}).get("id", ""),
        "data": data,
    }
    try:
        inc = process_event_state_transition(event)
        return incident_id, {"applied": event_type, "incident_status": inc.get("status") if inc else None}
    except HTTPException as exc:
        detail = exc.detail.get("error", {}) if isinstance(exc.detail, dict) else {}
        return incident_id, {"rejected": event_type, "code": detail.get("code"), "message": detail.get("message")}


@router.post("/gitlab")
async def gitlab_webhook(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    x_gitlab_token: str | None = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event: str | None = Header(None, alias="X-Gitlab-Event"),
):
    if not x_gitlab_token or not hmac.compare_digest(
        x_gitlab_token.encode("utf-8"), settings.gitlab_webhook_secret.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED_WEBHOOK",
                    "message": "Invalid or missing X-Gitlab-Token header.",
                    "retryable": False,
                }
            },
        )

    object_kind = payload.get("object_kind") or "unknown"
    event_type = x_gitlab_event or object_kind
    repo = get_repository()

    entity_id = "unknown"
    entity_type = "GitLab"
    status_or_action = "received"
    attrs = payload.get("object_attributes", {}) or {}

    if object_kind == "pipeline":
        entity_id = str(attrs.get("id") or payload.get("id") or "0")
        entity_type = "Pipeline"
        status_or_action = attrs.get("status") or "unknown"
    elif object_kind == "build":
        entity_id = str(payload.get("build_id") or payload.get("id") or "0")
        entity_type = "Job"
        status_or_action = payload.get("build_status") or "unknown"
    elif object_kind == "merge_request":
        entity_id = str(attrs.get("iid") or attrs.get("id") or "0")
        entity_type = "MergeRequest"
        status_or_action = attrs.get("action") or attrs.get("state") or "unknown"

    idempotency_key = f"gitlab:{object_kind}:{entity_id}:{status_or_action}"
    if not repo.check_and_set_idempotency(idempotency_key):
        return {
            "status": "processed",
            "event_type": event_type,
            "note": "Duplicate webhook event acknowledged idempotently.",
        }

    incident_id, outcome = (None, None)
    if object_kind == "merge_request":
        incident_id, outcome = _apply_mr_event(attrs, entity_id)
        head_sha = (attrs.get("last_commit") or {}).get("id")
        if outcome and outcome.get("incident_status") == "REPAIR_PROPOSED" and head_sha:
            background_tasks.add_task(ingest_analysis, incident_id, head_sha)

    sanitized_payload = sanitize_for_storage(payload)
    if incident_id:
        sanitized_payload["incident_id"] = incident_id
    if outcome:
        sanitized_payload["_state_machine"] = outcome

    event_id = f"evt-gl-{uuid.uuid4().hex[:12]}"
    summary = f"GitLab {object_kind} {status_or_action} event"
    if outcome and outcome.get("rejected"):
        summary = f"REJECTED {outcome.get('code')}: {outcome.get('message')}"
    repo.save_event(
        EventRecord(
            id=event_id,
            entity_type="Incident" if incident_id else entity_type,
            entity_id=incident_id or entity_id,
            type=f"gitlab.{object_kind}.{status_or_action}",
            source="gitlab/webhook",
            source_job_id=entity_id,
            at=datetime.now(UTC).isoformat(),
            data=sanitized_payload,
            summary=summary,
        )
    )

    response: dict[str, Any] = {"status": "processed", "event_type": event_type, "event_id": event_id}
    if outcome:
        response["incident_id"] = incident_id
        response["state_machine"] = outcome
    return response
