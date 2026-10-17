from typing import Optional, Dict, Any
from fastapi import APIRouter, Header, HTTPException, status
from app.config import settings

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

@router.post("/gitlab")
async def gitlab_webhook(
    payload: Dict[str, Any],
    x_gitlab_token: Optional[str] = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event: Optional[str] = Header(None, alias="X-Gitlab-Event"),
):
    # Verify token
    if not x_gitlab_token or x_gitlab_token != settings.gitlab_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED_WEBHOOK",
                    "message": "Invalid or missing X-Gitlab-Token header.",
                    "retryable": False
                }
            }
        )
    
    event_type = x_gitlab_event or payload.get("object_kind", "unknown")
    
    # In skeleton, acknowledge webhook
    return {
        "status": "processed",
        "event_type": event_type,
    }
