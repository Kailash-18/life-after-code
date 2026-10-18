import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.state_engine import process_event_state_transition
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# Memory storage for idempotency cache and recorded event log
PROCESSED_JOB_EVENTS = set()
RECORDED_EVENTS = []


class CiEventPayload(BaseModel):
    type: str
    source: str
    pipeline_id: str
    job_id: str
    commit_sha: str
    release_id: str | None = None
    incident_id: str | None = None
    artifact_url: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    sent_at: str


def verify_hmac_signature(body_bytes: bytes, signature_header: str | None) -> bool:
    if not signature_header:
        return False

    # Expected format: "sha256=<hex>"
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    provided_hex = signature_header[len(prefix) :]
    expected_hex = hmac.new(
        settings.hmac_secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(provided_hex, expected_hex)


def validate_timestamp_header(
    ts_header: str | None, max_age_seconds: int = 300
) -> datetime:
    if not ts_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "MISSING_TIMESTAMP",
                    "message": "X-Sentinel-Timestamp header is required.",
                    "retryable": False,
                }
            },
        )
    try:
        try:
            epoch = float(ts_header)
            event_dt = datetime.fromtimestamp(epoch, tz=UTC)
        except ValueError:
            event_dt = datetime.fromisoformat(ts_header)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_TIMESTAMP",
                    "message": f"Timestamp format '{ts_header}' is invalid. Provide ISO-8601 or epoch seconds.",
                    "retryable": False,
                }
            },
        )

    now_utc = datetime.now(UTC)
    delta = abs((now_utc - event_dt).total_seconds())
    if delta > max_age_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "TIMESTAMP_EXPIRED",
                    "message": f"Event timestamp is outside the allowable tolerance window ({int(delta)}s > {max_age_seconds}s). Replay rejected.",
                    "retryable": False,
                }
            },
        )
    return event_dt


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_ci_event(
    request: Request,
    x_sentinel_signature: str | None = Header(None, alias="X-Sentinel-Signature"),
    x_sentinel_timestamp: str | None = Header(None, alias="X-Sentinel-Timestamp"),
):
    body_bytes = await request.body()

    # 1. Access Control: Verify HMAC-SHA256 signature
    if not verify_hmac_signature(body_bytes, x_sentinel_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_SIGNATURE",
                    "message": "HMAC-SHA256 signature verification failed or missing.",
                    "retryable": False,
                }
            },
        )

    # 2. Replay Protection: Validate timestamp freshness (max 300 seconds)
    validate_timestamp_header(x_sentinel_timestamp)

    # 3. Parse and validate JSON schema payload
    try:
        payload = CiEventPayload.model_validate_json(body_bytes)
    except (ValidationError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MALFORMED_EVENT",
                    "message": f"Event payload failed schema validation: {e!s}",
                    "retryable": False,
                }
            },
        )

    # 4. Idempotency check: key on (job_id, type)
    from app.models.entities import EventRecord
    from app.persistence.factory import get_repository

    repo = get_repository()
    idempotency_key = f"{payload.job_id}:{payload.type}"

    # Use atomic repository idempotency check
    is_fresh = repo.check_and_set_idempotency(idempotency_key)
    if not is_fresh or idempotency_key in PROCESSED_JOB_EVENTS:
        PROCESSED_JOB_EVENTS.add(idempotency_key)
        return {
            "status": "accepted",
            "event_id": f"evt-duplicate-{payload.job_id}",
            "received_at": datetime.now(UTC).isoformat(),
            "note": "Duplicate event acknowledged idempotently.",
        }

    PROCESSED_JOB_EVENTS.add(idempotency_key)

    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(UTC).isoformat()

    event_record = {
        "id": event_id,
        "type": payload.type,
        "source": payload.source,
        "pipeline_id": payload.pipeline_id,
        "job_id": payload.job_id,
        "commit_sha": payload.commit_sha,
        "release_id": payload.release_id,
        "incident_id": payload.incident_id,
        "artifact_url": payload.artifact_url,
        "data": payload.data,
        "received_at": now_iso,
    }

    # 5. Evaluate state transition and enforce authoritative sources (Task R4)
    process_event_state_transition(event_record)

    # Persist in repository
    entity_type = "Incident" if payload.incident_id else "Release"
    entity_id = payload.incident_id or payload.release_id or payload.pipeline_id
    repo.save_event(
        EventRecord(
            id=event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            type=payload.type,
            source=payload.source,
            source_job_id=payload.job_id,
            at=now_iso,
            data=payload.data,
            artifact_url=payload.artifact_url,
        )
    )

    RECORDED_EVENTS.append(event_record)

    return {"status": "accepted", "event_id": event_id, "received_at": now_iso}

