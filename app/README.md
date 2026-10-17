# Sentinel Demo Target App (`app/`)

Lightweight FastAPI orders microservice deployed as the target workload under test for Project Sentinel.

## Endpoints
* `GET /healthz` — Rapid liveness probe reporting service status and version.
* `GET /metrics` — Prometheus metrics (latency histogram, error rates, request counts) scraped by Sentinel's Health Evaluator (`sentinel/scripts/evaluator.py`).
* `POST /api/v1/orders` — Places a new order, calculates tier discounts.
* `GET /api/v1/orders` — Lists placed orders.
* `GET /api/v1/orders/{id}` — Retrieves order detail.

## Reproducible Fault Mechanism
To demonstrate Sentinel's automated canary detection, rollback, and repair loop, this app supports two ways of triggering a reproducible fault:

1. **Commit-based Fault (Real Hackathon Scenario):**
   In `app/app/routes/orders.py`, the `calculate_discount` function has a bug deliberately introduced by a commit (e.g., dividing by zero or raising an unhandled exception when computing discounts for orders).
2. **Environment Toggle (`FAULT_INJECTION_MODE=true`):**
   Setting this environment variable in the Cloud Run candidate revision simulates the faulty commit immediately, causing `POST /api/v1/orders` to fail with HTTP 500 while `/healthz` remains superficially active.

## Running Locally
```bash
cd app
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Running Tests
```bash
pytest --junitxml=junit.xml --cov=app
```
