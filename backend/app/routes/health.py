from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["health"])

@router.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
    }
