import hmac
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Header, HTTPException, status
from pydantic import BaseModel, Field
from app.config import settings

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# Memory storage for idempotency cache and events in initial skeleton
PROCESSED_JOB_EVENTS = set()
RECORDED_EVENTS = []

class CiEventPayload(BaseModel):
    type: str
    source: str
    pipeline_id: str
    job_id: str
    commit_sha: str
    release_id: Optional[str] = None
    incident_id: Optional[str] = None
    artifact_url: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    sent_at: str

def verify_hmac_signature(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    if not signature_header:
        return False
    
    # Expected format: "sha256=<hex>"
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    
    provided_hex = signature_header[len(prefix):]
    expected_hex = hmac.new(
        settings.hmac_secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(provided_hex, expected_hex)

@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_ci_event(
    request: Request,
    x_sentinel_signature: Optional[str] = Header(None, alias="X-Sentinel-Signature"),
    x_sentinel_timestamp: Optional[str] = Header(None, alias="X-Sentinel-Timestamp"),
):
    body_bytes = await request.body()
    
    # 1. Access Control: Verify HMAC-SHA256
    if not verify_hmac_signature(body_bytes, x_sentinel_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_SIGNATURE",
                    "message": "HMAC-SHA256 signature verification failed or missing.",
                    "retryable": False
                }
            }
        )
    
    # 2. Parse and validate JSON
    try:
        payload = CiEventPayload.model_validate_json(body_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "MALFORMED_EVENT",
                    "message": f"Event payload failed schema validation: {str(e)}",
                    "retryable": False
                }
            }
        )
    
    # 3. Idempotency check: (job_id, type)
    idempotency_key = f"{payload.job_id}:{payload.type}"
    if idempotency_key in PROCESSED_JOB_EVENTS:
        # Idempotent response: return 202 without re-advancing state
        return {
            "status": "accepted",
            "event_id": f"evt-duplicate-{payload.job_id}",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "note": "Duplicate event acknowledged idempotently."
        }
    
    PROCESSED_JOB_EVENTS.add(idempotency_key)
    
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    
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
    RECORDED_EVENTS.append(event_record)
    
    return {
        "status": "accepted",
        "event_id": event_id,
        "received_at": now_iso
    }
