from app.routes.events import RECORDED_EVENTS
from app.state_engine import INCIDENTS_STORE
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("")
async def list_incidents(status: str | None = None):
    results = list(INCIDENTS_STORE.values())
    if status:
        results = [inc for inc in results if inc.get("status") == status]
    return results


@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    if incident_id not in INCIDENTS_STORE:
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
    return INCIDENTS_STORE[incident_id]


@router.get("/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str):
    # Returns strictly chronological events matching this incident
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
