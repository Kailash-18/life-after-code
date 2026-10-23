"""
GET /api/v1/status: what Mission Control shows in its header.

Every number comes from a recorded CI/evaluator event. When nothing has been
measured yet the fields are null ("unknown"), never a made-up healthy value.
"""

from fastapi import APIRouter

from app.models.entities import IncidentStatus, ReleaseStatus
from app.persistence.factory import get_repository
from app.state_engine import expire_overdue_attempts

router = APIRouter(prefix="/api/v1/status", tags=["status"])

RESOLVED_STATES = {IncidentStatus.RECOVERED.value}


def _latest_release_with_status(status: ReleaseStatus):
    rels = get_repository().list_releases(limit=1, status=status.value)
    return rels[0] if rels else None


@router.get("")
async def get_system_status():
    expire_overdue_attempts()
    repo = get_repository()

    active_incident = None
    for inc in repo.list_incidents():
        if inc.status.value not in RESOLVED_STATES:
            active_incident = inc.model_dump()
            break

    stable = repo.get_active_stable_release()
    candidate = _latest_release_with_status(ReleaseStatus.CANARY)

    candidate_percent = 0
    candidate_dep = None
    if candidate is not None:
        deps = repo.list_deployments_for_release(candidate.id)
        if deps:
            candidate_dep = deps[0]
            candidate_percent = candidate_dep.traffic_percent

    sample = None
    if candidate_dep is not None:
        sample = repo.get_latest_health_sample(candidate_dep.id)
    if sample is None:
        sample = repo.get_latest_health_sample()

    if sample is None:
        system_health = {
            "error_rate": None,
            "p95_ms": None,
            "healthy": None,
            "target": None,
            "sample_size": None,
            "measured_at": None,
            "source": "no evaluator measurement recorded yet",
        }
    else:
        system_health = {
            "error_rate": sample.error_rate,
            "p95_ms": sample.p95_ms,
            "healthy": sample.health_ok and active_incident is None,
            "target": sample.target,
            "sample_size": sample.sample_size,
            "measured_at": sample.measured_at,
            "source": f"evaluator sample {sample.id}",
        }

    return {
        "current_release": stable.model_dump() if stable else None,
        "candidate_release": candidate.model_dump() if candidate else None,
        "traffic_split": {
            "stable_percent": 100 - candidate_percent,
            "candidate_percent": candidate_percent,
        },
        "system_health": system_health,
        "active_incident": active_incident,
    }
