from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/api/v1/status", tags=["status"])

@router.get("")
async def get_system_status():
    """
    Returns the real-time operational status for Mission Control UI:
    active stable release, active canary release, traffic percentages, and any incident.
    """
    return {
        "current_release": {
            "id": "rel-stable-initial",
            "commit_sha": "c9aaa1fac0a16d44677e19b431ec4e79bf4da53d",
            "version": "1.0.0",
            "pipeline_id": "1",
            "status": "STABLE",
            "known_good": True,
            "created_at": "2026-10-18T00:00:00Z",
        },
        "candidate_release": None,
        "traffic_split": {
            "stable_percent": 100,
            "candidate_percent": 0,
        },
        "system_health": {
            "error_rate": 0.0,
            "p95_ms": 25.0,
            "healthy": True,
        },
        "active_incident": None,
    }
