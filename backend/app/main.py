from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routes.events import router as events_router
from app.routes.health import router as health_router
from app.routes.incidents import router as incidents_router
from app.routes.releases import router as releases_router
from app.routes.state import router as state_router
from app.routes.status import router as status_router
from app.routes.webhooks import router as webhooks_router


app = FastAPI(
    title=settings.service_name,
    description="Sentinel Backend API for deployment safety, CI event ingestion, and recovery state tracking.",
    version=settings.version,
)

# CORS setup for Mission Control UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom validation exception handler to ensure standard {error: {code, message, retryable}} contract
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(exc),
                "retryable": False,
            }
        },
    )


# Register API v1 routes
app.include_router(health_router)
app.include_router(events_router)
app.include_router(webhooks_router)
app.include_router(status_router)
app.include_router(incidents_router)
app.include_router(releases_router)
app.include_router(state_router)



@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.service_name,
        "version": settings.version,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/api/v1/healthz",
        "status": "/api/v1/status",
    }
