"""
Project Sentinel Event Ingestion Route (Tasks R3, R7, R8).

POST /api/v1/events is the only way CI writes to the backend:
1. HMAC-SHA256 over the raw body (X-Sentinel-Signature: sha256=<hex>)   -> 401
2. Timestamp freshness, header and signed body `sent_at` (+-300 s)       -> 401
3. JSON + JSON Schema contract (docs/contracts/event.schema.json)       -> 400
4. Secret scan: sensitive keys redacted, secret-looking values rejected -> 422
5. Idempotency on (job_id, type[, traffic_percent]): duplicates acknowledged, not re-applied
6. Release/deploy/health bookkeeping, then incident state machine        -> 409/422
7. Every accepted *or rejected* event is written to the event ledger
8. Flow dispatch (if enabled) runs as a background task, never inline
"""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
from app.analysis_ingest import ingest_analysis
from app.config import settings
from app.flow_dispatch import maybe_dispatch
from app.models.entities import EventRecord
from app.persistence.factory import get_repository
from app.release_tracker import process_release_event
from app.security import find_secret_values, redact_sensitive_keys
from app.state_engine import expire_overdue_attempts, process_event_state_transition
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("sentinel.events")

router = APIRouter(prefix="/api/v1/events", tags=["events"])

MAX_EVENT_BYTES = 256 * 1024  # events carry references, not artifacts

# Process-local mirrors kept for backward compatibility with older tests.
PROCESSED_JOB_EVENTS: set[str] = set()
RECORDED_EVENTS: list[dict[str, Any]] = []

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_CANDIDATES = [
    _BACKEND_ROOT / "contracts" / "event.schema.json",  # copied into the Docker image
    _BACKEND_ROOT.parent / "docs" / "contracts" / "event.schema.json",  # repo checkout
]

_VALIDATOR: jsonschema.Draft202012Validator | None = None


def resolve_schema_path() -> Path:
    candidates = ([Path(settings.event_schema_path)] if settings.event_schema_path else []) + SCHEMA_CANDIDATES
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError(
        "Event contract not found. Set SENTINEL_EVENT_SCHEMA_PATH or ship "
        "docs/contracts/event.schema.json with the service. Refusing to accept unvalidated events."
    )


def get_contract_validator() -> jsonschema.Draft202012Validator:
    """Loads and caches the Draft 2020-12 validator. Fails closed if the schema is missing."""
    global _VALIDATOR
    if _VALIDATOR is None:
        with open(resolve_schema_path(), encoding="utf-8") as f:
            schema_data = json.load(f)
        _VALIDATOR = jsonschema.Draft202012Validator(
            schema_data, format_checker=jsonschema.FormatChecker()
        )
    return _VALIDATOR


def redact_sensitive_data(val: Any) -> Any:
    """Backward-compatible alias: key-based redaction."""
    return redact_sensitive_keys(val)


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


def _error(http_status: int, code: str, message: str, retryable: bool = False) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message, "retryable": retryable}},
    )


def verify_hmac_signature(body_bytes: bytes, signature_header: str | None) -> bool:
    """Constant-time HMAC-SHA256 signature verification."""
    if not signature_header:
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    provided_hex = signature_header[len(prefix):]
    expected_hex = hmac.new(
        settings.hmac_secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(provided_hex, expected_hex)


def parse_and_validate_timestamp(ts_str: str | None, max_age_seconds: int = 300) -> datetime:
    """Rejects missing, unparseable, stale or future timestamps (+-max_age_seconds)."""
    if not ts_str:
        raise _error(status.HTTP_401_UNAUTHORIZED, "MISSING_TIMESTAMP", "X-Sentinel-Timestamp header is required.")
    try:
        try:
            event_dt = datetime.fromtimestamp(float(ts_str), tz=UTC)
        except ValueError:
            event_dt = datetime.fromisoformat(ts_str)
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_TIMESTAMP",
            f"Timestamp format '{ts_str[:40]}' is invalid. Provide ISO-8601 or epoch seconds.",
        )
    delta = abs((datetime.now(UTC) - event_dt).total_seconds())
    if delta > max_age_seconds:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "TIMESTAMP_EXPIRED",
            f"Event timestamp is outside the allowable tolerance window ({int(delta)}s > {max_age_seconds}s). Replay rejected.",
        )
    return event_dt


async def require_ci_signature(
    request: Request,
    x_sentinel_signature: str | None = Header(None, alias="X-Sentinel-Signature"),
    x_sentinel_timestamp: str | None = Header(None, alias="X-Sentinel-Timestamp"),
) -> None:
    """
    Dependency for every non-event write endpoint (e.g. /api/v1/state/*): same scheme as
    /events. HMAC over the raw body, fresh X-Sentinel-Timestamp, and a signed, fresh
    `sent_at` inside the JSON body (so a captured request cannot be replayed later).
    """
    body = await request.body()
    if len(body) > MAX_EVENT_BYTES:
        raise _error(413, "PAYLOAD_TOO_LARGE", f"Body exceeds {MAX_EVENT_BYTES} bytes.")
    if not verify_hmac_signature(body, x_sentinel_signature):
        raise _error(
            status.HTTP_401_UNAUTHORIZED, "INVALID_SIGNATURE", "HMAC-SHA256 signature verification failed or missing."
        )
    parse_and_validate_timestamp(x_sentinel_timestamp, max_age_seconds=300)
    try:
        sent_at = json.loads(body.decode("utf-8") or "{}").get("sent_at")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        sent_at = None
    if not sent_at:
        raise _error(status.HTTP_401_UNAUTHORIZED, "MISSING_TIMESTAMP", "Signed body must contain sent_at.")
    parse_and_validate_timestamp(str(sent_at), max_age_seconds=300)


def _ledger(record: dict[str, Any], rejection: dict[str, Any] | None = None) -> None:
    incident_id = record.get("incident_id")
    data = dict(record["data"])
    if incident_id:
        data.setdefault("incident_id", incident_id)
    summary = None
    if rejection:
        data["_rejected"] = rejection
        summary = f"REJECTED {rejection.get('code')}: {rejection.get('message')}"
    get_repository().save_event(
        EventRecord(
            id=record["id"],
            entity_type="Incident" if incident_id else "Release",
            entity_id=incident_id or record.get("release_id") or f"rel-{record['commit_sha'][:12]}",
            type=record["type"],
            source=record["source"],
            source_job_id=record["job_id"],
            at=record["received_at"],
            data=data,
            artifact_url=record.get("artifact_url"),
            summary=summary,
        )
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_ci_event(
    request: Request,
    background_tasks: BackgroundTasks,
    x_sentinel_signature: str | None = Header(None, alias="X-Sentinel-Signature"),
    x_sentinel_timestamp: str | None = Header(None, alias="X-Sentinel-Timestamp"),
):
    body_bytes = await request.body()
    if len(body_bytes) > MAX_EVENT_BYTES:
        raise _error(413, "PAYLOAD_TOO_LARGE", f"Event body exceeds {MAX_EVENT_BYTES} bytes; send evidence as an artifact_url.")

    # 1. Access control: only CI holds the HMAC secret.
    if not verify_hmac_signature(body_bytes, x_sentinel_signature):
        raise _error(
            status.HTTP_401_UNAUTHORIZED, "INVALID_SIGNATURE", "HMAC-SHA256 signature verification failed or missing."
        )

    # 2. Replay protection on the header timestamp.
    parse_and_validate_timestamp(x_sentinel_timestamp, max_age_seconds=300)

    # 3. JSON + schema contract.
    try:
        raw_payload = json.loads(body_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise _error(status.HTTP_400_BAD_REQUEST, "MALFORMED_EVENT", f"Malformed JSON payload: {e!s}")

    errors = list(get_contract_validator().iter_errors(raw_payload))
    if errors:
        first_err = errors[0]
        field = ".".join(str(p) for p in first_err.path) or "root"
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "MALFORMED_EVENT",
            f"Schema contract violation at '{field}': {first_err.message[:300]}",
        )

    try:
        payload = CiEventPayload.model_validate(raw_payload)
    except ValidationError as e:
        raise _error(status.HTTP_400_BAD_REQUEST, "MALFORMED_EVENT", f"Payload structure invalid: {e!s}") from e

    # The signed body timestamp must be fresh too (header alone is not signed).
    parse_and_validate_timestamp(payload.sent_at, max_age_seconds=300)

    # 4. Secret hygiene: redact sensitive keys, reject credential-looking values.
    sanitized_data = redact_sensitive_keys(payload.data)
    findings = find_secret_values(
        {"data": sanitized_data, "artifact_url": payload.artifact_url, "source": payload.source}
    )
    if findings:
        where = ", ".join(f"{f['path']} ({f['kind']})" for f in findings[:5])
        raise _error(
            422,
            "SECRET_DETECTED",
            f"Event rejected: credential-like value found at {where}. Secrets must never be sent to Sentinel.",
        )

    # 5. Idempotency on (job_id, type).
    repo = get_repository()
    idempotency_key = f"{payload.job_id}:{payload.type}"
    # One deploy/evaluate job may step traffic 10 -> 50 -> 100 %: each step is a distinct fact.
    if isinstance(payload.data.get("traffic_percent"), int):
        idempotency_key += f":{payload.data['traffic_percent']}"
    if not repo.check_and_set_idempotency(idempotency_key):
        PROCESSED_JOB_EVENTS.add(idempotency_key)
        return {
            "status": "accepted",
            "event_id": f"evt-duplicate-{payload.job_id}",
            "received_at": datetime.now(UTC).isoformat(),
            "note": "Duplicate event acknowledged idempotently.",
        }
    PROCESSED_JOB_EVENTS.add(idempotency_key)

    event_record: dict[str, Any] = {
        "id": f"evt-{uuid.uuid4().hex[:12]}",
        "type": payload.type,
        "source": payload.source,
        "pipeline_id": payload.pipeline_id,
        "job_id": payload.job_id,
        "commit_sha": payload.commit_sha,
        "release_id": payload.release_id,
        "incident_id": payload.incident_id,
        "artifact_url": payload.artifact_url,
        "data": sanitized_data,
        "received_at": datetime.now(UTC).isoformat(),
    }

    try:
        expire_overdue_attempts()
        # 6a. Facts about releases, traffic and health (authoritative CI measurements).
        process_release_event(event_record)
        # 6b. Incident state machine (may assign incident_id for incident.detected).
        incident = process_event_state_transition(event_record)
    except HTTPException as exc:
        detail = exc.detail.get("error", {}) if isinstance(exc.detail, dict) else {}
        if detail.get("retryable"):
            # Out-of-order delivery: let CI retry instead of swallowing it as a duplicate.
            repo.release_idempotency(idempotency_key)
            PROCESSED_JOB_EVENTS.discard(idempotency_key)
        else:
            _ledger(event_record, rejection=detail)
        raise
    except (sqlite3.Error, OSError) as exc:
        repo.release_idempotency(idempotency_key)
        PROCESSED_JOB_EVENTS.discard(idempotency_key)
        logger.error("Storage failure processing event %s: %s", event_record["id"], exc)
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "STORAGE_ERROR", "Internal storage failure persisting event.", True
        ) from exc

    # 7. Ledger (incident.detected may have been assigned an id above).
    try:
        _ledger(event_record)
    except (sqlite3.Error, RuntimeError, ValueError, OSError) as exc:
        logger.error("Failed to persist event %s: %s", event_record["id"], exc)
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "STORAGE_ERROR", "Internal storage failure persisting event.", True
        ) from exc
    RECORDED_EVENTS.append(event_record)

    # 8. Start the investigation flow after the response is sent.
    if incident and incident.get("status") == "EVIDENCE_COLLECTED":
        background_tasks.add_task(maybe_dispatch, incident["id"])
    if incident and payload.type == "repair.proposed" and sanitized_data.get("fix_sha"):
        background_tasks.add_task(ingest_analysis, incident["id"], str(sanitized_data["fix_sha"]))

    return {
        "status": "accepted",
        "event_id": event_record["id"],
        "received_at": event_record["received_at"],
        "incident_id": event_record.get("incident_id"),
        "incident_status": incident.get("status") if incident else None,
    }


@router.get("", response_model=list[dict[str, Any]])
async def list_events(
    limit: int = 100,
    offset: int = 0,
    type: str | None = None,
    incident_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch global chronological event ledger for Mission Control and audit logging."""
    repo = get_repository()
    events = repo.list_all_events(limit=limit, offset=offset, event_type=type, incident_id=incident_id)
    return [
        {
            "id": e.id,
            "type": e.type,
            "source": e.source,
            "source_job_id": e.source_job_id,
            "job": str(e.source_job_id) if e.source_job_id is not None else None,
            "pipeline_id": str(e.data.get("pipeline_id")) if e.data.get("pipeline_id") else None,
            "commit_sha": e.data.get("commit_sha"),
            "release_id": e.data.get("release_id"),
            "incident_id": e.entity_id if e.entity_type == "incident" else e.data.get("incident_id"),
            "at": e.at,
            "summary": e.summary,
            "evidence_url": e.artifact_url,
            "data": e.data,
            "rejected": e.data.get("rejected"),
        }
        for e in events
    ]


# Resolve the schema at import time in production so a bad image fails fast.
if os.getenv("SENTINEL_ENV", "development").lower() == "production":
    get_contract_validator()
