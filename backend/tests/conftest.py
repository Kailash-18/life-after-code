import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure app package is importable
backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from app.main import app
from app.config import settings

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def hmac_secret():
    return settings.hmac_secret
