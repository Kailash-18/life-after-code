from app.config import settings
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
    }
