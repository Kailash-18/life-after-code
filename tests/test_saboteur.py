"""
Unit tests for the Saboteur Adversarial Agent (sentinel/scripts/saboteur.py).
"""

from sentinel.scripts.saboteur import ATTACK_CATALOG, SaboteurEngine


def test_saboteur_catalog_completeness():
    engine = SaboteurEngine()
    assert len(engine.attacks) >= 7
    strategy_ids = {a.strategy_id for a in engine.attacks}
    assert "CHEAT_SKIP_INJECTION" in strategy_ids
    assert "CHEAT_ASSERT_WEAKENED" in strategy_ids
    assert "CHEAT_EXPECTATION_MUTATION" in strategy_ids
    assert "CHEAT_TEST_DELETION" in strategy_ids
    assert "CHEAT_HARNESS_ESCAPE_ENV" in strategy_ids
    assert "CHEAT_EQ_OVERRIDE" in strategy_ids
    assert "CHEAT_PROTECTED_CONFIG_TAMPER" in strategy_ids


def test_integrity_gate_intercepts_every_sabotage_attack():
    engine = SaboteurEngine()
    summary = engine.run_all_attacks()
    assert summary["all_blocked"] is True
    assert summary["deterrence_rate_percent"] == 100.0
    assert summary["evaded_count"] == 0
    assert summary["caught_count"] == len(summary["results"])

    for r in summary["results"]:
        assert r["blocked"] is True
        assert r["gate_verdict"] == "FAIL"
        assert r["blocking_findings_count"] > 0
