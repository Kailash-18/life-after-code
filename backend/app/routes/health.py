from app.config import settings
from fastapi import APIRouter, Header

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/healthz")
async def healthz(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    key_supplied = bool(x_api_key or (authorization and authorization.startswith("Bearer ")))
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
        "auth_verified": key_supplied,
    }
