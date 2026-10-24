from app.persistence.factory import get_repository
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])


@router.get("")
async def list_releases(limit: int = 20, status: str | None = None):
    """Release history recorded from CI events (empty until CI reports a release)."""
    limit = max(1, min(limit, 100))
    return [r.model_dump() for r in get_repository().list_releases(limit=limit, status=status)]


@router.get("/{release_id}")
async def get_release(release_id: str):
    repo = get_repository()
    rel = repo.get_release(release_id)
    if rel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RELEASE_NOT_FOUND",
                    "message": f"Release {release_id} not found.",
                    "retryable": False,
                }
            },
        )
    body = rel.model_dump()
    body["deployments"] = [d.model_dump() for d in repo.list_deployments_for_release(release_id)]
    return body
