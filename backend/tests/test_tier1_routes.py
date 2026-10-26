"""
Unit tests for Project Sentinel Tier 1 SRE API Routes:
- /api/v1/sre/saboteur
- /api/v1/sre/candidates
- /api/v1/sre/trust-score
- /api/v1/sre/holdout
"""

from fastapi.testclient import TestClient

from app.main import app


def test_saboteur_arena_all_blocked():
    client = TestClient(app)
    response = client.get("/api/v1/sre/saboteur")
    assert response.status_code == 200
    data = response.json()
    assert data["total_attacks"] >= 7
    assert data["caught_count"] == data["total_attacks"]
    assert data["evaded_count"] == 0
    assert data["deterrence_rate_percent"] == 100.0
    assert data["all_blocked"] is True
    assert data["verdict"] == "INTEGRITY_GATE_IMPERVIOUS"


def test_saboteur_arena_single_strategy():
    client = TestClient(app)
    response = client.get("/api/v1/sre/saboteur?strategy=CHEAT_SKIP_INJECTION")
    assert response.status_code == 200
    data = response.json()
    assert data["total_attacks"] == 1
    assert data["caught_count"] == 1
    assert data["all_blocked"] is True
    res = data["results"][0]
    assert res["strategy_id"] == "CHEAT_SKIP_INJECTION"
    assert res["blocked"] is True


def test_candidate_fixes_evaluation():
    client = TestClient(app)
    response = client.get("/api/v1/sre/candidates")
    assert response.status_code == 200
    data = response.json()
    assert data["total_candidates"] == 3
    assert data["selected_candidate_id"] == "cand-003-sound"
    assert data["winner"]["status"] == "SELECTED"
    assert data["winner"]["trust_score"] >= 90

    # Ensure rejects have explicit reasons
    rejects = [c for c in data["candidates"] if c["status"] == "REJECTED"]
    assert len(rejects) == 2
    for r in rejects:
        assert r["rejection_reason"] is not None
        assert len(r["rejection_reason"]) > 0


def test_trust_score_calculation():
    client = TestClient(app)
    # Exemplary clean fix
    resp = client.get("/api/v1/sre/trust-score?blocking_findings=0&regression_proven=true&holdout_passed=true")
    assert resp.status_code == 200
    d = resp.json()
    assert d["trust_score"] >= 95
    assert d["rating"] == "EXEMPLARY"
    assert "AI can explain but never set" in d["governance_rule"]

    # Dangerous cheat with blocking findings
    resp_bad = client.get("/api/v1/sre/trust-score?blocking_findings=2&regression_proven=false")
    assert resp_bad.status_code == 200
    d_bad = resp_bad.json()
    assert d_bad["trust_score"] == 0 or d_bad["trust_score"] < 40
    assert d_bad["rating"] == "DANGEROUS"


def test_holdout_gate_execution():
    client = TestClient(app)
    response = client.get("/api/v1/sre/holdout")
    assert response.status_code == 200
    data = response.json()
    assert data["gate"] == "holdout_tests"
    assert data["verdict"] == "PASS"
    assert data["invariants_tested"] >= 5
    assert data["invariants_passed"] >= 5
    assert data["invariants_failed"] == 0
