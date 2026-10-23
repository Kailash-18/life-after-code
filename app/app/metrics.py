import logging
import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

logger = logging.getLogger("target_app")

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

ERROR_COUNT = Counter(
    "http_errors_total",
    "Total HTTP server errors (5xx)",
    ["endpoint", "status_code"],
)


async def metrics_middleware(request: Request, call_next):
    # Skip measuring the /metrics and /healthz endpoints themselves to keep synthetic probe metrics pristine
    if request.url.path in ("/metrics", "/healthz"):
        return await call_next(request)

    start_time = time.time()
    endpoint = request.url.path
    status_code = 500

    try:
        response: Response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:  # error boundary: any unhandled bug becomes a 500 response
        status_code = 500
        logger.exception("Unhandled error on %s %s", request.method, endpoint)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    finally:
        duration = time.time() - start_time
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=str(status_code),
        ).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)
        if status_code >= 500:
            ERROR_COUNT.labels(endpoint=endpoint, status_code=str(status_code)).inc()


def get_metrics_response(request: Request = None) -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
