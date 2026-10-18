import pytest
from sentinel.scripts.evaluator import calculate_percentile, load_policy

def test_calculate_percentile():
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p50 = calculate_percentile(values, 50.0)
    p95 = calculate_percentile(values, 95.0)
    assert p50 == 55.0
    assert p95 == 95.5

def test_load_policy():
    policy = load_policy()
    assert policy["version"] == "1.0"
    assert "thresholds" in policy
    assert policy["thresholds"]["error_rate_max"] == 0.02
    assert policy["thresholds"]["p95_latency_ms_max"] == 300.0
    assert "rollout" in policy
    assert len(policy["rollout"]["stages"]) >= 4

def test_deployment_strategies_options_and_recommendation():
    policy = load_policy()
    assert "deployment_strategies" in policy
    strat_cfg = policy["deployment_strategies"]
    assert strat_cfg["recommended"] == "canary_progressive"
    assert "rationale" in strat_cfg
    
    options = strat_cfg["options"]
    option_ids = [opt["id"] for opt in options]
    assert "canary_progressive" in option_ids
    assert "blue_green" in option_ids
    assert "shadow_traffic" in option_ids
    assert "rolling_update" in option_ids
    assert "direct_recreate" in option_ids

    # Verify only the recommended strategy has recommended: True
    recommended_opts = [opt for opt in options if opt.get("recommended") is True]
    assert len(recommended_opts) == 1
    assert recommended_opts[0]["id"] == "canary_progressive"


def test_evaluator_markdown_report_includes_deployment_options(tmp_path):
    from sentinel.scripts.evaluator import generate_markdown_report
    report = {
        "timestamp": "2026-10-19T01:00:00Z",
        "verdict": "FAIL",
        "traffic_percent": 10,
        "revision_name": "cand-rev-01",
        "candidate": {"error_rate": 0.08, "p95_ms": 320.0, "sample_size": 20, "health_endpoint_ok": True},
        "stable": {"error_rate": 0.0, "p95_ms": 25.0, "sample_size": 20, "health_endpoint_ok": True},
        "thresholds": {"error_rate_max": 0.02, "p95_latency_ms_max": 300.0},
        "breached_thresholds": ["Candidate error rate 8.00% exceeds max permitted 2.00%"],
    }
    out_file = tmp_path / "test-report.md"
    generate_markdown_report(report, out_file)
    content = out_file.read_text(encoding="utf-8")
    assert "Breached Policy Thresholds" in content
    assert "Post-Incident Redeployment Strategies & Authoritative Recommendation" in content
    assert "Progressive Canary (Tag-Isolated)" in content
    assert "Blue/Green" in content
    assert "Shadow / Traffic Mirroring" in content
    assert "Rolling Instance Replacement" in content
    assert "Direct Recreate (In-Place)" in content
    assert "⭐ RECOMMENDED (Best Choice)" in content


