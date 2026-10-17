from fastapi import APIRouter
from app.config import settings

router = APIRouter(tags=["health"])

@router.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
        "fault_injection_active": settings.fault_injection_mode,
    }
