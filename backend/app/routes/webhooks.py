from typing import Any

from app.config import settings
from fastapi import APIRouter, Header, HTTPException, status

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/gitlab")
async def gitlab_webhook(
    payload: dict[str, Any],
    x_gitlab_token: str | None = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event: str | None = Header(None, alias="X-Gitlab-Event"),
):
    # Verify token
    if not x_gitlab_token or x_gitlab_token != settings.gitlab_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED_WEBHOOK",
                    "message": "Invalid or missing X-Gitlab-Token header.",
                    "retryable": False,
                }
            },
        )

    event_type = x_gitlab_event or payload.get("object_kind", "unknown")

    # In skeleton, acknowledge webhook
    return {
        "status": "processed",
        "event_type": event_type,
    }
