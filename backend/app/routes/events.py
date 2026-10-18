"""
Project Sentinel Event Ingestion Route.
Implements Task R3: Secure CI event ingestion with HMAC-SHA256 signature verification,
replay protection (300s window), JSON schema validation against docs/contracts/event.schema.json,
atomic idempotency, sensitive data redaction, and persistence via SentinelRepository.
"""

import hashlib
import hmac
import json
import logging
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
from app.config import settings
from app.models.entities import EventRecord
from app.persistence.factory import get_repository
from app.state_engine import process_event_state_transition
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("sentinel.events")

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# Memory fallback storage for tests
PROCESSED_JOB_EVENTS = set()
RECORDED_EVENTS = []

# Path to shared JSON Schema contract
SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "contracts"
    / "event.schema.json"
)

_VALIDATOR: jsonschema.Draft202012Validator | None = None


def get_contract_validator() -> jsonschema.Draft202012Validator | None:
    """Loads and caches the compiled Draft 2020-12 validator for the event schema."""
    global _VALIDATOR
    if _VALIDATOR is None and SCHEMA_PATH.exists():
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema_data = json.load(f)
        _VALIDATOR = jsonschema.Draft202012Validator(schema_data)
    return _VALIDATOR


# Regex patterns for sensitive key/value redaction
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(password|secret|token|api[_-]?key|auth|bearer|private[_-]?key)"
)


def redact_sensitive_data(val: Any) -> Any:
    """Recursively redacts passwords, tokens, and secrets from event data before storage."""
    if isinstance(val, dict):
        cleaned = {}
        for k, v in val.items():
            if SENSITIVE_KEY_PATTERN.search(str(k)):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = redact_sensitive_data(v)
        return cleaned
    elif isinstance(val, list):
        return [redact_sensitive_data(item) for item in val]
    return val


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
    """Constant-time HMAC-SHA256 signature verification."""
    if not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    provided_hex = signature_header[len(prefix) :]
    expected_hex = hmac.new(
        settings.hmac_secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(provided_hex, expected_hex)


def parse_and_validate_timestamp(ts_str: str | None, max_age_seconds: int = 300) -> datetime:
    """
    Validates that a timestamp is parseable and within the ±max_age_seconds tolerance window.
    Rejects both stale events and events too far in the future.
    """
    if not ts_str:
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
            epoch = float(ts_str)
            event_dt = datetime.fromtimestamp(epoch, tz=UTC)
        except ValueError:
            event_dt = datetime.fromisoformat(ts_str)
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_TIMESTAMP",
                    "message": f"Timestamp format '{ts_str}' is invalid. Provide ISO-8601 or epoch seconds.",
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

    # 1. Access Control: Constant-time HMAC-SHA256 signature verification
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

    # 2. Replay Protection: Validate header timestamp freshness (±300 seconds)
    parse_and_validate_timestamp(x_sentinel_timestamp, max_age_seconds=300)

    # 3. JSON Syntax Check
    try:
        raw_payload = json.loads(body_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MALFORMED_EVENT",
                    "message": f"Malformed JSON payload: {e!s}",
                    "retryable": False,
                }
            },
        )

    # 4. JSON Schema Validation against shared event.schema.json
    validator = get_contract_validator()
    if validator is not None:
        errors = list(validator.iter_errors(raw_payload))
        if errors:
            first_err = errors[0]
            field = ".".join(str(p) for p in first_err.path) or "root"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "MALFORMED_EVENT",
                        "message": f"Schema contract violation at '{field}': {first_err.message}",
                        "retryable": False,
                    }
                },
            )

    # 5. Parse typed payload and validate body sent_at freshness
    try:
        payload = CiEventPayload.model_validate(raw_payload)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MALFORMED_EVENT",
                    "message": f"Payload structure invalid: {e!s}",
                    "retryable": False,
                }
            },
        ) from e

    # Validate body timestamp freshness as well
    parse_and_validate_timestamp(payload.sent_at, max_age_seconds=300)

    # 6. Idempotency Check: Keyed strictly on (source_job_id, type)
    repo = get_repository()
    idempotency_key = f"{payload.job_id}:{payload.type}"

    # Atomic insert check in repository
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

    # Redact sensitive payload contents before storage
    sanitized_data = redact_sensitive_data(payload.data)

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
        "data": sanitized_data,
        "received_at": now_iso,
    }

    # 7. State Machine Evaluation (Task R4)
    process_event_state_transition(event_record)

    # 8. Persistence to Repository Ledger
    entity_type = "Incident" if payload.incident_id else "Release"
    entity_id = payload.incident_id or payload.release_id or payload.pipeline_id
    try:
        repo.save_event(
            EventRecord(
                id=event_id,
                entity_type=entity_type,
                entity_id=entity_id,
                type=payload.type,
                source=payload.source,
                source_job_id=payload.job_id,
                at=now_iso,
                data=sanitized_data,
                artifact_url=payload.artifact_url,
            )
        )
    except (sqlite3.Error, RuntimeError, ValueError, OSError) as exc:
        logger.error(f"Failed to persist event {event_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "STORAGE_ERROR",
                    "message": "Internal storage failure persisting event.",
                    "retryable": True,
                }
            },
        ) from exc

    RECORDED_EVENTS.append(event_record)

    return {"status": "accepted", "event_id": event_id, "received_at": now_iso}
