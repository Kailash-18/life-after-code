"""
Unit tests for Sentinel Cryptographic Supply Chain Attestation Engine (SLSA Level 3).
Validates in-toto build provenance predicates, CycloneDX SBOM generation, and HMAC-SHA256 signatures.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import pytest

from sentinel.scripts.supply_chain_attestation import (
    calculate_file_sha256,
    generate_slsa_provenance,
    generate_sbom_summary,
    attest_build_artifact,
)


def test_calculate_file_sha256(tmp_path: Path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("Sentinel Cryptographic Attestation Test", encoding="utf-8")
    digest = calculate_file_sha256(test_file)
    expected = hashlib.sha256(b"Sentinel Cryptographic Attestation Test").hexdigest()
    assert digest == expected

    missing = tmp_path / "does_not_exist.txt"
    assert calculate_file_sha256(missing) == "0" * 64


def test_generate_slsa_provenance():
    image_uri = "us-central1-docker.pkg.dev/project-sentinel/sentinel/target-app:v1.2.3"
    commit_sha = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    pred = generate_slsa_provenance(image_uri, commit_sha)

    assert pred["_type"] == "https://in-toto.io/Statement/v0.1"
    assert pred["predicateType"] == "https://slsa.dev/provenance/v0.2"
    assert len(pred["subject"]) == 1
    assert "sha256" in pred["subject"][0]["digest"]
    assert pred["predicate"]["invocation"]["configSource"]["digest"]["sha1"] == commit_sha
    assert pred["predicate"]["metadata"]["reproducible"] is True


def test_generate_sbom_summary():
    sbom = generate_sbom_summary(["app", "sentinel"])
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["components_count"] >= 2
    assert len(sbom["sbom_sha256"]) == 64
    names = [c["name"] for c in sbom["components"]]
    assert "sentinel-target-app" in names
    assert "fastapi" in names


def test_attest_build_artifact_signature_and_file(tmp_path: Path):
    image_uri = "us-central1-docker.pkg.dev/project-sentinel/sentinel/target-app:test"
    commit_sha = "abcdef0123456789abcdef0123456789abcdef01"
    secret = "test-secret-key-for-unit-tests"

    attestation = attest_build_artifact(
        image_uri=image_uri,
        commit_sha=commit_sha,
        secret=secret,
        output_dir=tmp_path,
    )

    assert attestation["slsa_level"] == "SLSA_BUILD_LEVEL_3"
    assert attestation["security_policy_satisfied"] is True
    assert attestation["signature"].startswith("sha256=")

    # Verify cryptographic signature authenticity
    envelope_bytes = json.dumps(attestation["payload"], separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), envelope_bytes, hashlib.sha256).hexdigest()
    assert attestation["signature"] == f"sha256={expected_sig}"

    # Verify file saved on disk
    saved_file = tmp_path / f"attestation-{commit_sha[:8]}.json"
    assert saved_file.exists()
    content = json.loads(saved_file.read_text(encoding="utf-8"))
    assert content["attestation_sha256"] == attestation["attestation_sha256"]
