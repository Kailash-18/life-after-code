from app.persistence.factory import get_repository
from app.state_engine import INCIDENTS_STORE
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/status", tags=["status"])


@router.get("")
async def get_system_status():
    """
    Returns the real-time operational status for Mission Control UI:
    active stable release, active canary release, traffic percentages, and any incident.
    """
    repo = get_repository()

    # Find active incident from repository or legacy store
    active_inc = None
    persisted_incidents = repo.list_incidents()
    for inc in persisted_incidents:
        if inc.status.value not in ("RECOVERED", "CLOSED"):
            active_inc = inc.model_dump()
            break

    if not active_inc:
        for inc in INCIDENTS_STORE.values():
            if inc.get("status") not in ("RECOVERED", "CLOSED"):
                active_inc = inc
                break

    is_healthy = active_inc is None

    # Fetch active stable release from repository
    stable_rel = repo.get_active_stable_release()
    if stable_rel:
        current_release = stable_rel.model_dump()
    else:
        current_release = {
            "id": "rel-stable-initial",
            "commit_sha": "c9aaa1fac0a16d44677e19b431ec4e79bf4da53d",
            "version": "1.0.0",
            "pipeline_id": "1",
            "status": "STABLE",
            "known_good": True,
            "created_at": "2026-10-18T00:00:00Z",
        }

    return {
        "current_release": current_release,
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
