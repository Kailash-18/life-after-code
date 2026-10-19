"""
Unit tests for Sentinel Open Policy Agent (OPA) / Rego Validator.
Validates zero-trust container security context, resource limits, WAF bindings, and blast radius policies.
"""

from __future__ import annotations

import pytest

from sentinel.scripts.opa_validator import RegoPolicyEngine, generate_compliant_production_manifest


def test_rego_validator_compliant_manifest():
    engine = RegoPolicyEngine()
    manifest = generate_compliant_production_manifest()
    report = engine.evaluate(manifest)

    assert report["allow"] is True
    assert report["compliance_score"] == 100.0
    assert report["violations_count"] == 0
    assert report["status"] == "APPROVED"


def test_rego_validator_detects_root_execution():
    engine = RegoPolicyEngine()
    manifest = generate_compliant_production_manifest()
    manifest["containers"][0]["security_context"]["run_as_root"] = True

    report = engine.evaluate(manifest)
    assert report["allow"] is False
    assert any("Root execution is strictly prohibited" in v for v in report["violations"])


def test_rego_validator_detects_excessive_canary_traffic():
    engine = RegoPolicyEngine()
    manifest = generate_compliant_production_manifest()
    manifest["deployment"]["canary_initial_traffic"] = 25  # Exceeds 10% maximum blast radius

    report = engine.evaluate(manifest)
    assert report["allow"] is False
    assert any("exceeds maximum blast radius tolerance" in v for v in report["violations"])


def test_rego_validator_detects_missing_waf():
    engine = RegoPolicyEngine()
    manifest = generate_compliant_production_manifest()
    manifest["network"]["cloud_armor_waf_enabled"] = False

    report = engine.evaluate(manifest)
    assert report["allow"] is False
    assert any("missing Google Cloud Armor Layer 7 WAF" in v for v in report["violations"])


def test_rego_validator_detects_direct_recreate_strategy():
    engine = RegoPolicyEngine()
    manifest = generate_compliant_production_manifest()
    manifest["deployment"]["strategy"] = "direct_recreate"

    report = engine.evaluate(manifest)
    assert report["allow"] is False
    assert any("direct_recreate" in v for v in report["violations"])
