"""
GitLab System Webhook Ingestion Route.
Implements Task R3: Authenticated GitLab webhook receiver (X-Gitlab-Token),
constant-time verification, idempotent processing, and persistence of pipeline/job/MR events.
"""

import hmac
import uuid
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.models.entities import EventRecord
from app.persistence.factory import get_repository
from app.routes.events import redact_sensitive_data
from fastapi import APIRouter, Header, HTTPException, status

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/gitlab")
async def gitlab_webhook(
    payload: dict[str, Any],
    x_gitlab_token: str | None = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event: str | None = Header(None, alias="X-Gitlab-Event"),
):
    # 1. Constant-time token verification to prevent timing side-channel attacks
    if not x_gitlab_token or not hmac.compare_digest(
        x_gitlab_token, settings.gitlab_webhook_secret
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

    # 2. Extract entity metadata and determine unique idempotency key
    entity_id = "unknown"
    entity_type = "GitLab"
    status_or_action = "received"

    if object_kind == "pipeline":
        attrs = payload.get("object_attributes", {})
        entity_id = str(attrs.get("id") or payload.get("id") or "0")
        entity_type = "Pipeline"
        status_or_action = attrs.get("status") or "unknown"
    elif object_kind == "build":
        entity_id = str(payload.get("build_id") or payload.get("id") or "0")
        entity_type = "Job"
        status_or_action = payload.get("build_status") or "unknown"
    elif object_kind == "merge_request":
        attrs = payload.get("object_attributes", {})
        entity_id = str(attrs.get("iid") or attrs.get("id") or "0")
        entity_type = "MergeRequest"
        status_or_action = attrs.get("action") or attrs.get("state") or "unknown"

    idempotency_key = f"gitlab:{object_kind}:{entity_id}:{status_or_action}"

    # 3. Idempotency check
    is_fresh = repo.check_and_set_idempotency(idempotency_key)
    if not is_fresh:
        return {
            "status": "processed",
            "event_type": event_type,
            "note": "Duplicate webhook event acknowledged idempotently.",
        }

    # 4. Redact and persist webhook event
    event_id = f"evt-gl-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(UTC).isoformat()
    sanitized_payload = redact_sensitive_data(payload)

    repo.save_event(
        EventRecord(
            id=event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            type=f"gitlab.{object_kind}.{status_or_action}",
            source="gitlab/webhook",
            source_job_id=entity_id,
            at=now_iso,
            data=sanitized_payload,
            summary=f"GitLab {object_kind} {status_or_action} event",
        )
    )

    return {
        "status": "processed",
        "event_type": event_type,
        "event_id": event_id,
    }
