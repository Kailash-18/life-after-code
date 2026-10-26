"""
Unit tests for Risk-Adaptive Canary Diff Scorer (Tier 2 Feature 5).
Validates diff risk factors, sensitive subsystem detection, AI authorship penalty,
and progressive canary rollout schedules (1% -> 10% -> 50% -> 100%).
"""

from __future__ import annotations

import pytest
from sentinel.scripts.canary_deploy import (
    get_deployment_strategies_catalog,
    score_diff_risk,
)


def test_score_diff_risk_baseline_low_risk():
    risk = score_diff_risk(
        diff_text="diff --git a/docs/readme.md b/docs/readme.md\n+minor docs edit\n",
        changed_files=["docs/readme.md"],
        author="alice@example.com",
        branch="docs-update",
    )
    assert risk["risk_score"] < 30
    assert risk["risk_tier"] == "LOW_RISK"
    assert risk["adaptive_rollout_steps"][0]["traffic_percent"] == 10
    assert "10% -> 50% -> 100%" in risk["rollout_steps_summary"]


def test_score_diff_risk_sensitive_files():
    risk = score_diff_risk(
        diff_text="diff --git a/app/routes/orders.py b/app/routes/orders.py\n+new auth check\n",
        changed_files=["app/routes/orders.py", "app/auth/tokens.py"],
        author="alice@example.com",
        branch="main",
    )
    assert risk["risk_score"] >= 30
    assert any("Sensitive Core Subsystems Modified" in f["factor"] for f in risk["risk_factors"])


def test_score_diff_risk_dependency_and_blast_radius():
    large_diff = "\n".join([f"+line {i}" for i in range(120)])
    risk = score_diff_risk(
        diff_text=large_diff,
        changed_files=["requirements.txt"],
        author="bob@example.com",
        branch="feat/deps",
    )
    assert any("Dependency / Runtime Bumps" in f["factor"] for f in risk["risk_factors"])
    assert any("Blast Radius" in f["factor"] for f in risk["risk_factors"])


def test_score_diff_risk_ai_authored_repair_candidate():
    risk = score_diff_risk(
        diff_text="diff --git a/app/routes/orders.py b/app/routes/orders.py\n+if count == 0: return 0\n",
        changed_files=["app/routes/orders.py"],
        author="gitlab-duo-flow",
        branch="duo/repair-inc-42",
    )
    assert risk["is_ai_authored"] is True
    assert any("AI-Generated Repair Candidate" in f["factor"] for f in risk["risk_factors"])
    assert risk["risk_tier"] in ("MEDIUM_RISK", "CRITICAL_RISK")


def test_score_diff_risk_critical_schedule():
    large_diff = "\n".join([f"+line {i}" for i in range(250)])
    risk = score_diff_risk(
        diff_text=large_diff,
        changed_files=["app/auth/security.py", "requirements.txt", ".gitlab-ci.yml"],
        author="duo-repair-bot",
        branch="duo/fix",
    )
    assert risk["risk_score"] >= 60
    assert risk["risk_tier"] == "CRITICAL_RISK"
    assert risk["adaptive_rollout_steps"][0]["traffic_percent"] == 1
    assert "1% -> 10% -> 50% -> 100%" in risk["rollout_steps_summary"]

    catalog = get_deployment_strategies_catalog(diff_risk=risk)
    assert catalog["recommended_strategy"] == "risk_adaptive_canary"
    assert catalog["strategies"]["risk_adaptive_canary"]["recommended"] is True
    assert catalog["strategies"]["risk_adaptive_canary"]["risk_tier"] == "CRITICAL_RISK"
