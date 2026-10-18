import hashlib
import hmac
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure app package is importable
backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.config import settings
from app.main import app
from app.persistence.factory import get_repository
from app.routes.events import PROCESSED_JOB_EVENTS, RECORDED_EVENTS
from app.state_engine import INCIDENTS_STORE


def generate_signature(secret: str, body_bytes: bytes) -> str:
    hex_digest = hmac.new(
        secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()
    return f"sha256={hex_digest}"


@pytest.fixture(autouse=True)
def clean_backend_state():
    repo = get_repository()
    repo.clear()
    PROCESSED_JOB_EVENTS.clear()
    RECORDED_EVENTS.clear()
    INCIDENTS_STORE.clear()
    yield
    repo.clear()
    PROCESSED_JOB_EVENTS.clear()
    RECORDED_EVENTS.clear()
    INCIDENTS_STORE.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def hmac_secret():
    return settings.hmac_secret
