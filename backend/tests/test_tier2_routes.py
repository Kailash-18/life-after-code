"""
Unit tests for Project Sentinel Tier 2 SRE & Incident API Routes:
- /api/v1/sre/diff-risk
- /api/v1/sre/shadow-replay
- /api/v1/sre/carbon
- /api/v1/incidents/{incident_id}/postmortem
"""

from fastapi.testclient import TestClient
from app.main import app


def test_canary_diff_risk_endpoint():
    client = TestClient(app)
    response = client.get(
        "/api/v1/sre/diff-risk?author=gitlab-duo-flow&branch=duo/repair-fix&diff_text=diff%20--git%20a/app/routes/orders.py"
    )
    assert response.status_code == 200
    data = response.json()
    assert "recommended_strategy" in data
    assert "diff_risk" in data
    assert data["diff_risk"]["risk_score"] > 0
    assert "adaptive_rollout_steps" in data["diff_risk"]
    assert len(data["diff_risk"]["adaptive_rollout_steps"]) > 0


def test_shadow_traffic_replay_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/sre/shadow-replay?incident_id=inc-test-01&samples=20")
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "PASS"
    assert data["summary"]["total_replayed_requests"] == 20
    assert data["summary"]["baseline_error_rate_pct"] == 100.0
    assert data["summary"]["candidate_error_rate_pct"] == 0.0
    assert data["summary"]["shadow_parity_score_pct"] == 100.0
    assert len(data["replayed_samples"]) > 0


def test_measured_carbon_intensity_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/sre/carbon?cpu_seconds=5.0&requests=200")
    assert response.status_code == 200
    data = response.json()
    assert data["specification"] == "ISO/IEC 21031 (Green Software Foundation SCI)"
    assert data["is_measured"] is True
    assert data["measurement_mode"] == "measured_cloud_run_telemetry"
    assert data["sci_score"] > 0
    assert "measured_telemetry" in data
    assert data["measured_telemetry"]["cpu_seconds"] == 5.0
    assert data["measured_telemetry"]["request_count"] == 200


def test_auto_written_postmortem_endpoint():
    client = TestClient(app)
    response = client.get("/api/v1/incidents/inc-demo-003/postmortem")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "inc-demo-003"
    assert "[POSTMORTEM]" in data["markdown"]
    assert "Zero Human In-the-Loop" in data["markdown"]
    assert "Root Cause Analysis" in data["markdown"]
    assert "sha256" in data
