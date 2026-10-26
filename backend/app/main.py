from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_startup()
    yield


app = FastAPI(
    title=settings.service_name,
    description="Sentinel Backend API for deployment safety, CI event ingestion, and recovery state tracking.",
    version=settings.version,
    lifespan=lifespan,
)


# CORS setup for Mission Control UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # The dashboard only reads. Browsers may not POST: writes come from CI (HMAC) only.
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS", "HEAD"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-Requested-With"],
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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Contract §A8: errors are {error: {code, message, retryable}}.
    `detail` is kept as a deprecated alias for older clients/tests."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        error = exc.detail["error"]
    else:
        error = {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "retryable": False}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error, "detail": {"error": error}},
        headers=getattr(exc, "headers", None),
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
