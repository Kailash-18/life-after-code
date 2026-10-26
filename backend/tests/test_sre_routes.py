"""
Unit test suite for SRE Platform Telemetry Routes (/api/v1/sre/*).
Validates:
- /api/v1/sre/health: Composite SRE health, Mann-Whitney U test, error budget burn rate
- /api/v1/sre/opa: OPA Rego policy evaluation and Zero-Trust guardrail scoring
- /api/v1/sre/opa/validate: Custom manifest admission evaluation
- /api/v1/sre/ebpf: L4/L7 eBPF latency decomposition and socket metrics
- /api/v1/sre/dr: Multi-region disaster recovery RTO and RPO metrics
- /api/v1/sre/drift: EWMA and CUSUM adaptive drift monitoring
"""

from __future__ import annotations

from tests.helpers import FIX_SHA, ok, send


def test_sre_health_without_measurement_is_no_data(client):
    data = client.get("/api/v1/sre/health?slo_target=0.999").json()
    assert data["status"] == "NO_DATA"
    assert data["health_score"] is None and data["error_budget"] is None
    drift = client.get("/api/v1/sre/drift").json()
    assert drift["status"] == "NO_DATA" and drift["current_ewma"] is None


def test_sre_composite_health_endpoint(client, hmac_secret):
    ok(send(client, hmac_secret, "evaluator.verdict", commit_sha=FIX_SHA, source="sentinel/scripts/evaluator.py",
            job_id=9301, data={"verdict": "PASS", "target": "candidate", "traffic_percent": 10,
                               "error_rate": 0.004, "p95_ms": 41.5, "sample_size": 300}))
    res = client.get("/api/v1/sre/health?slo_target=0.999")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] in ("PASS", "WARN", "FAIL")
    assert data["data_source"]["kind"] == "derived"
    assert "burn_rate" in data["error_budget"]
    assert "alert_tier" in data["error_budget"]
    assert "p_value" in data["hypothesis_testing"]
    assert "is_significant" in data["hypothesis_testing"]
    assert "median" in data["latency_iqr"]


def test_sre_panels_say_where_numbers_come_from(client):
    assert client.get("/api/v1/sre/opa").json()["data_source"]["kind"] == "reference"
    assert client.get("/api/v1/sre/ebpf").json()["data_source"]["kind"] == "simulated"
    assert client.get("/api/v1/sre/dr").json()["data_source"]["kind"] == "simulated"


def test_sre_opa_compliance_nominal(client):
    res = client.get("/api/v1/sre/opa")
    assert res.status_code == 200
    data = res.json()

    assert data["allow"] is True
    assert data["compliance_score"] == 100.0
    assert data["status"] == "APPROVED"
    assert data["violations_count"] == 0
    assert data["policy_package"] == "sentinel.security.guardrails"


def test_sre_opa_validate_custom_manifest(client):
    violating_manifest = {
        "service": "insecure-app",
        "containers": [
            {
                "name": "insecure",
                "resources": {"limits": {}},  # Missing limits
                "security_context": {"run_as_root": True},  # Prohibited root
            }
        ],
        "deployment": {"strategy": "direct_recreate", "canary_initial_traffic": 50},  # Exceeds 10%
    }
    res = client.post("/api/v1/sre/opa/validate", json={"manifest": violating_manifest})
    assert res.status_code == 200
    data = res.json()

    assert data["allow"] is False
    assert data["status"] == "REJECTED_BY_POLICY_GATE"
    assert data["violations_count"] > 0
    assert any("Root execution" in v for v in data["violations"])


def test_sre_ebpf_telemetry_endpoint(client):
    res = client.get("/api/v1/sre/ebpf?samples=3")
    assert res.status_code == 200
    data = res.json()

    assert data["samples_collected"] == 3
    assert "mean_transport_health_score" in data
    assert "status" in data
    assert "latency_decomposition_averages_ms" in data
    decomp = data["latency_decomposition_averages_ms"]
    assert "dns_resolution" in decomp
    assert "tcp_handshake" in decomp
    assert "tls_handshake" in decomp
    assert "server_ttfb" in decomp
    assert "kernel_socket_aggregates" in data


def test_sre_disaster_recovery_endpoint(client):
    res = client.get("/api/v1/sre/dr")
    assert res.status_code == 200
    data = res.json()

    assert data["primary_region"] == "us-central1"
    assert data["secondary_region"] == "us-east1"
    assert data["rto_seconds"] <= 5.0
    assert data["rpo_seconds"] == 0.0
    assert data["status"] == "OPTIMAL"


def test_sre_adaptive_drift_endpoint(client):
    res = client.get("/api/v1/sre/drift?observed_latency=32.4")
    assert res.status_code == 200
    data = res.json()

    assert "current_ewma" in data
    assert "cusum_high_statistic" in data
    assert "cusum_low_statistic" in data
    assert "decision_threshold_h" in data
    assert "drift_detected" in data
    assert "status" in data
