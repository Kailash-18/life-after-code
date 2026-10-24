"""
Unit tests for Sentinel Cloud Armor Threat Mitigator.
Validates rate-based ban generation, SQLi signature blocking, and artifact generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.cloud_armor_mitigator import (
    CloudArmorMitigator,
    run_armor_audit,
)


def test_cloud_armor_mitigator_identifies_flood():
    mitigator = CloudArmorMitigator(ban_threshold_rps=100)
    samples = [{"src_ip": "1.2.3.4", "rps": 180, "pattern": "HTTP_FLOOD"}]
    res = mitigator.analyze_threat_vectors(samples)

    assert res["status"] == "THREATS_MITIGATED"
    assert res["threats_detected"] == 1
    assert res["dynamic_rules_generated"][0]["action"] == "rate_based_ban"


def test_cloud_armor_mitigator_identifies_sqli():
    mitigator = CloudArmorMitigator()
    samples = [{"src_ip": "5.6.7.8", "rps": 10, "pattern": "OWASP_SQLI"}]
    res = mitigator.analyze_threat_vectors(samples)

    assert res["status"] == "THREATS_MITIGATED"
    assert res["dynamic_rules_generated"][0]["action"] == "deny(403)"


def test_run_armor_audit_artifact(tmp_path: Path):
    report = run_armor_audit(output_dir=tmp_path)
    assert report["waf_active"] is True
    assert "gcp_security_policy" in report
    assert report["gcp_security_policy"]["type"] == "CLOUD_ARMOR"

    out_file = tmp_path / "cloud-armor-threat-mitigation-report.json"
    assert out_file.exists()
    waf_file = tmp_path / "cloud-armor-waf-report.json"
    assert waf_file.exists()
