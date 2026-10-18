from app.persistence.factory import get_repository
from app.routes.events import RECORDED_EVENTS
from app.state_engine import INCIDENTS_STORE
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("")
async def list_incidents(status: str | None = None):
    repo = get_repository()
    persisted = repo.list_incidents(status=status)
    if persisted:
        return [inc.model_dump() for inc in persisted]

    # Legacy store fallback
    results = list(INCIDENTS_STORE.values())
    if status:
        results = [inc for inc in results if inc.get("status") == status]
    return results


@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    repo = get_repository()
    inc = repo.get_incident(incident_id)
    if inc:
        return inc.model_dump()

    if incident_id in INCIDENTS_STORE:
        return INCIDENTS_STORE[incident_id]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": {
                "code": "INCIDENT_NOT_FOUND",
                "message": f"Incident {incident_id} does not exist.",
                "retryable": False,
            }
        },
    )


@router.get("/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str):
    repo = get_repository()
    events = repo.list_events_for_incident(incident_id)
    if events:
        return [
            {
                "id": e.id,
                "type": e.type,
                "source": e.source,
                "source_job_id": e.source_job_id,
                "at": e.at,
                "incident_id": incident_id,
                "data": e.data,
                "artifact_url": e.artifact_url,
            }
            for e in events
        ]

    # Returns strictly chronological events matching this incident from memory log
    timeline = [
        evt
        for evt in RECORDED_EVENTS
        if evt.get("incident_id") == incident_id
        or (
            evt.get("type") == "incident.detected"
            and evt.get("incident_id") == incident_id
        )
    ]
    return timeline
