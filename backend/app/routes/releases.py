from typing import List, Optional
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])

RELEASES_DB = {
    "rel-stable-initial": {
        "id": "rel-stable-initial",
        "commit_sha": "c9aaa1fac0a16d44677e19b431ec4e79bf4da53d",
        "version": "1.0.0",
        "image_digest": "sha256:4b227777d4dd1fc61c6f884f48641d02b4d121d3fd3a4830c5b7b7f541d15c4e",
        "revision_name": "target-app-00001-init",
        "pipeline_id": "1",
        "status": "STABLE",
        "known_good": True,
        "created_at": "2026-10-18T00:00:00Z",
    }
}

@router.get("")
async def list_releases(limit: int = 20, status: Optional[str] = None):
    releases = list(RELEASES_DB.values())
    if status:
        releases = [r for r in releases if r.get("status") == status]
    return releases[:limit]

@router.get("/{release_id}")
async def get_release(release_id: str):
    if release_id not in RELEASES_DB:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RELEASE_NOT_FOUND",
                    "message": f"Release {release_id} not found.",
                    "retryable": False
                }
            }
        )
    return RELEASES_DB[release_id]
