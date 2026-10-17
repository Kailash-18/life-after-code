import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

@pytest.fixture
def client():
    # Ensure baseline healthy state during tests
    settings.fault_injection_mode = False
    with TestClient(app) as test_client:
        yield test_client
