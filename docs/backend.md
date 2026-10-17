# Sentinel Backend API Documentation

The Sentinel API Backend ingests CI/CD stage events, maintains deployment state, verifies recovery progress against deterministic gates, and provides real-time telemetry to the Mission Control UI.

## Environment Variables

| Variable | Description | Default | Required in Production |
|---|---|---|---|
| `SENTINEL_ENV` | Environment name (`development`, `staging`, `production`) | `development` | Yes |
| `PORT` | HTTP port to listen on (Google Cloud Run binds to `$PORT`) | `8000` | No |
| `SENTINEL_HMAC_SECRET` | Shared secret key for verifying HMAC-SHA256 signatures from CI jobs | `sentinel-dev-secret-key-change-in-prod` | **Yes (Masked CI Var)** |
| `GITLAB_WEBHOOK_SECRET` | Secret token configured in GitLab project webhook settings (`X-Gitlab-Token`) | `sentinel-gitlab-token-change-in-prod` | **Yes** |
| `CORS_ORIGINS` | Comma-separated list of allowed web frontend origins | `http://localhost:3000,http://localhost:5173` | Yes |

## API Contracts
* OpenAPI 3.1.0 specification: [`docs/contracts/openapi.yaml`](file:///c:/Users/KRISHNA%20SINGH/OneDrive/Desktop/Major%20projects/Life%20after%20Code/life-after-code/docs/contracts/openapi.yaml)
* Stage Event Schema: [`docs/contracts/event.schema.json`](file:///c:/Users/KRISHNA%20SINGH/OneDrive/Desktop/Major%20projects/Life%20after%20Code/life-after-code/docs/contracts/event.schema.json)

## Event Ingestion & HMAC Authentication
CI jobs emit signed events to `POST /api/v1/events` using the shared secret.

### Request Headers
* `X-Sentinel-Signature`: `sha256=<hex_digest>` where `<hex_digest> = HMAC_SHA256(secret, raw_body_bytes)`
* `X-Sentinel-Timestamp`: ISO-8601 UTC timestamp of emission.

### Idempotency
To handle pipeline retries without corrupting recovery state transitions, the backend de-duplicates events keyed on `(job_id, type)`. Duplicate events receive an idempotent `202 Accepted` acknowledgement.

## Running Locally

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Interactive API documentation will be available at:
* Swagger UI: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`
* OpenAPI JSON: `http://localhost:8000/openapi.json`

## Running Tests
```bash
cd backend
pytest -v
```

## Running with Docker
```bash
docker build -t sentinel-backend:latest .
docker run -p 8000:8000 -e SENTINEL_HMAC_SECRET="your-secret" sentinel-backend:latest
```
