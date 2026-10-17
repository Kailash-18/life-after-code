from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from app.routes.events import RECORDED_EVENTS

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

# In-memory storage for incidents in initial skeleton
INCIDENTS_DB = {}

@router.get("")
async def list_incidents(status: Optional[str] = None):
    results = list(INCIDENTS_DB.values())
    if status:
        results = [inc for inc in results if inc.get("status") == status]
    return results

@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    if incident_id not in INCIDENTS_DB:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "INCIDENT_NOT_FOUND",
                    "message": f"Incident {incident_id} does not exist.",
                    "retryable": False
                }
            }
        )
    return INCIDENTS_DB[incident_id]

@router.get("/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str):
    # Returns strictly chronological events matching this incident
    timeline = [
        evt for evt in RECORDED_EVENTS
        if evt.get("incident_id") == incident_id or evt.get("type") == "incident.detected"
    ]
    return timeline
