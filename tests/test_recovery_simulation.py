"""
Test the complete 11-step End-to-End Recovery Simulation against the Sentinel Backend.
Verifies that all states from DETECTED to RECOVERED are traversed with authoritative source checks.
"""

import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
backend_dir = PROJECT_ROOT / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from sentinel.scripts.emit_event import emit_event
from sentinel.scripts.run_recovery_simulation import simulate_full_recovery_loop

client = TestClient(app)


def test_full_recovery_simulation_loop():
    # Mock urllib.request.urlopen in emit_event to route directly to our FastAPI TestClient!
    def mock_urlopen(req, timeout=10):
        url = req.full_url
        method = req.get_method()
        headers = dict(req.headers)
        if hasattr(req, "header_items"):
            for k, v in req.header_items():
                headers[k] = v
        data = req.data
        
        path = url.split("http://localhost:8000")[-1]
        
        response = client.request(
            method=method,
            url=path,
            content=data,
            headers=headers,
        )
        if response.status_code not in (200, 202):
            print(f"DEBUG {method} {path} -> {response.status_code}: {response.text}")
        
        class MockResponse:
            def __init__(self, r):
                self.status = r.status_code
                self._content = r.content
            def read(self):
                return self._content
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
                
        return MockResponse(response)

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = simulate_full_recovery_loop(
            backend_url="http://localhost:8000",
            candidate_app_url="http://localhost:8080",
            stable_app_url="http://localhost:8080",
            delay_between_steps=0.01,
        )

        assert result["status"] == "RECOVERED"
        incident_id = result["incident_id"]

        # Verify backend recorded incident and reached RECOVERED state
        resp = client.get(f"/api/v1/incidents/{incident_id}")
        assert resp.status_code == 200
        inc_data = resp.json()
        assert inc_data["status"] == "RECOVERED"
        assert len(inc_data["recovery_attempts"]) >= 1
        assert inc_data["recovery_attempts"][-1]["state"] == "RECOVERED"

        # Verify timeline has all events recorded
        timeline_resp = client.get(f"/api/v1/incidents/{incident_id}/timeline")
        assert timeline_resp.status_code == 200
        events = timeline_resp.json()
        event_types = [e["type"] for e in events]
        assert "incident.detected" in event_types
        assert "rollback.completed" in event_types
        assert "evidence.collected" in event_types
        assert "flow.started" in event_types
        assert "repair.proposed" in event_types
        assert "regression_proof.verdict" in event_types
        assert "integrity_gate.verdict" in event_types
        assert "merge.completed" in event_types
        assert "redeploy.completed" in event_types
        assert "recovery.verified" in event_types
