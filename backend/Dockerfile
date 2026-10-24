# Build from the REPOSITORY ROOT so the event contract ships inside the image:
#   docker build -f backend/Dockerfile -t sentinel-backend .
# The service refuses to start in production without docs/contracts/event.schema.json.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    SENTINEL_ENV=production \
    SENTINEL_EVENT_SCHEMA_PATH=/workspace/contracts/event.schema.json \
    SENTINEL_SQLITE_PATH=/tmp/sentinel.db \
    SENTINEL_STATE_CACHE_DIR=/tmp/sentinel-state

WORKDIR /workspace

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY docs/contracts/event.schema.json docs/contracts/analysis.schema.json ./contracts/

RUN useradd --create-home --uid 10001 sentinel
USER sentinel

EXPOSE 8000

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
