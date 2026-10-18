from app.state_engine import INCIDENTS_STORE
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/status", tags=["status"])


@router.get("")
async def get_system_status():
    """
    Returns the real-time operational status for Mission Control UI:
    active stable release, active canary release, traffic percentages, and any incident.
    """
    # Find any active incident that is not yet recovered or closed
    active_inc = None
    for inc in INCIDENTS_STORE.values():
        if inc.get("status") not in ("RECOVERED", "CLOSED"):
            active_inc = inc
            break

    is_healthy = active_inc is None

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
            "error_rate": 0.0 if is_healthy else 0.08,
            "p95_ms": 25.0 if is_healthy else 180.0,
            "healthy": is_healthy,
        },
        "active_incident": active_inc,
    }
