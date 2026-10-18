"""
Unit tests for Sentinel Sigstore Cosign Verifier.
Validates keyless provenance verification, Fulcio certificate matching, and Rekor transparency logs.
"""

from __future__ import annotations

import pytest

from sentinel.scripts.cosign_verifier import SigstoreCosignVerifier, run_supply_chain_verification_gate


def test_cosign_verifier_valid_signature():
    image_uri = "us-central1-docker.pkg.dev/project-sentinel/sentinel/target-app:v1.2.0"
    digest = "e4f8b91c2d3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c"

    res = SigstoreCosignVerifier.verify_image_signature(image_uri, digest, simulate_tampering=False)
    assert res["verified"] is True
    assert res["status"] == "CRYPTOGRAPHICALLY_VERIFIED"
    assert res["sigstore_verification"]["fulcio_certificate_valid"] is True
    assert res["sigstore_verification"]["rekor_transparency_log_verified"] is True
    assert len(res["violations"]) == 0


def test_cosign_verifier_detects_tampering():
    image_uri = "us-central1-docker.pkg.dev/project-sentinel/sentinel/target-app:v1.2.0"
    digest = "e4f8b91c2d3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c"

    res = SigstoreCosignVerifier.verify_image_signature(image_uri, digest, simulate_tampering=True)
    assert res["verified"] is False
    assert res["status"] == "TAMPERING_DETECTED_REJECT"
    assert len(res["violations"]) > 0


def test_run_supply_chain_verification_gate_wrapper(tmp_path):
    report_file = tmp_path / "cosign-report.json"
    res = run_supply_chain_verification_gate(
        image_uri="us-central1-docker.pkg.dev/project-sentinel/sentinel/target-app:v1.2.0",
        commit_sha="e4f8b91c2d3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c",
        simulate_tampering=False,
        output_path=str(report_file),
    )

    assert res["verified"] is True
    assert report_file.exists()
