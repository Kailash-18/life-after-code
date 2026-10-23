"""
Harness for generated regression tests (tests/regressions/test_inc_<id>.py).

Makes the demo target app importable from the repository root and provides a
`client` fixture, so a regression test can be as small as:

    def test_premium_tier_any_casing(client):
        r = client.post("/api/v1/orders", json={...})
        assert r.status_code == 201

This file exists BEFORE any repair MR. The Integrity Gate blocks repair MRs that edit it.
"""

import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@pytest.fixture
def client():
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
