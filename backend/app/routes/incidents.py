from app.persistence.factory import get_repository
from app.state_engine import expire_overdue_attempts
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _not_found(incident_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": {
                "code": "INCIDENT_NOT_FOUND",
                "message": f"Incident {incident_id} does not exist.",
                "retryable": False,
            }
        },
    )


@router.get("")
async def list_incidents(status: str | None = None):
    expire_overdue_attempts()
    return [inc.model_dump() for inc in get_repository().list_incidents(status=status)]


@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    expire_overdue_attempts()
    inc = get_repository().get_incident(incident_id)
    if inc is None:
        raise _not_found(incident_id)
    body = inc.model_dump()
    # AI output is never proof: label it explicitly for the UI.
    for att in body.get("recovery_attempts", []):
        if att.get("analysis") is not None:
            att["analysis"]["advisory"] = True
    return body


@router.get("/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str):
    """Ordered ledger events for the incident, each citing its source job and evidence link."""
    repo = get_repository()
    if repo.get_incident(incident_id) is None:
        raise _not_found(incident_id)
    events = repo.list_events_for_incident(incident_id)
    return [
        {
            "id": e.id,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "incident_id": incident_id,
            "type": e.type,
            "source": e.source,
            "source_job_id": e.source_job_id,
            "at": e.at,
            "summary": e.summary,
            "rejected": bool(isinstance(e.data, dict) and e.data.get("_rejected")),
            "evidence_url": e.artifact_url,
            "artifact_url": e.artifact_url,
            "payload_ref": e.payload_ref,
            "data": e.data,
        }
        for e in events
    ]
