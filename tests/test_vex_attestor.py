"""
Unit tests for Sentinel CycloneDX VEX Attestor.
Validates VEX format, vulnerability status assertions, and SHA-256 generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.vex_attestor import (
    CycloneDxVexAttestor,
    run_vex_audit,
)


def test_vex_attestor_generates_valid_format():
    attestor = CycloneDxVexAttestor(product_name="sentinel-target-app")
    vex = attestor.generate_vex_document()

    assert vex["bomFormat"] == "CycloneDX"
    assert vex["specVersion"] == "1.5"
    assert vex["verdict"] == "VEX_CERTIFIED_CLEAN"
    assert len(vex["vulnerabilities"]) >= 2
    assert "vex_sha256" in vex


def test_run_vex_audit_artifact(tmp_path: Path):
    report = run_vex_audit(output_dir=tmp_path)
    assert report["verdict"] == "VEX_CERTIFIED_CLEAN"
    out_file = tmp_path / "cyclonedx-vex-attestation.json"
    assert out_file.exists()
    alias_file = tmp_path / "cyclonedx-vex-report.json"
    assert alias_file.exists()
