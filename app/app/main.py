from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.metrics import metrics_middleware, get_metrics_response
from app.routes.health import router as health_router
from app.routes.orders import router as orders_router

app = FastAPI(
    title="Project Sentinel Target App",
    description="Demo target microservice under test for automated deployment safety and recovery.",
    version=settings.version,
)

# Prometheus instrumentation middleware
app.add_middleware(BaseHTTPMiddleware, dispatch=metrics_middleware)

# Health & Metrics
app.include_router(health_router)
app.add_route("/metrics", get_metrics_response, methods=["GET"], include_in_schema=False)

# Domain routes
app.include_router(orders_router)

@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.service_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/healthz",
        "metrics": "/metrics",
    }
