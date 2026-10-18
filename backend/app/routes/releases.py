from app.models.entities import Release, ReleaseStatus
from app.persistence.factory import get_repository
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])

INITIAL_RELEASE = {
    "id": "rel-stable-initial",
    "commit_sha": "c9aaa1fac0a16d44677e19b431ec4e79bf4da53d",
    "version": "1.0.0",
    "image_digest": "sha256:4b227777d4dd1fc61c6f884f48641d02b4d121d3fd3a4830c5b7b7f541d15c4e",
    "revision_name": "target-app-00001-init",
    "pipeline_id": "1",
    "status": ReleaseStatus.STABLE,
    "known_good": True,
    "created_at": "2026-10-18T00:00:00Z",
}

RELEASES_DB = {"rel-stable-initial": dict(INITIAL_RELEASE, status="STABLE")}


def _ensure_initial_release() -> None:
    repo = get_repository()
    if not repo.get_release("rel-stable-initial"):
        repo.save_release(Release(**INITIAL_RELEASE))


@router.get("")
async def list_releases(limit: int = 20, status: str | None = None):
    _ensure_initial_release()
    repo = get_repository()
    releases = repo.list_releases(limit=limit, status=status)
    if releases:
        return [r.model_dump() for r in releases]

    # Fallback
    res = list(RELEASES_DB.values())
    if status:
        res = [r for r in res if r.get("status") == status]
    return res[:limit]


@router.get("/{release_id}")
async def get_release(release_id: str):
    _ensure_initial_release()
    repo = get_repository()
    rel = repo.get_release(release_id)
    if rel:
        return rel.model_dump()

    if release_id in RELEASES_DB:
        return RELEASES_DB[release_id]

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
