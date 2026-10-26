"""
Unit tests for Sentinel Autonomous Incident Postmortem Generator (Tier 2 Feature 8).
Verifies markdown generation, 5-whys root cause analysis, timeline timestamps,
cryptographic SHA-256 evidence hashing, and artifact outputs.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from sentinel.scripts.postmortem_generator import (
    generate_postmortem_bundle,
    generate_postmortem_markdown,
)


def test_postmortem_markdown_content():
    md = generate_postmortem_markdown(
        incident_id="inc-test-99",
        broken_release="1.5.0",
        recovered_release="1.5.1",
        trust_score=98,
        human_interventions=0,
    )

    assert "[POSTMORTEM]" in md
    assert "inc-test-99" in md
    assert "Zero Human In-the-Loop" in md
    assert "Time to Contain (TTC)" in md
    assert "Time to Recover (TTR)" in md
    assert "Root Cause Analysis (5 Whys)" in md
    assert "Cryptographic Verification" in md
    assert "sha256:" in md


def test_postmortem_bundle_and_artifact_files(tmp_path: Path):
    bundle = generate_postmortem_bundle(
        incident_id="inc-bundle-01",
        output_dir=tmp_path,
    )

    assert bundle["incident_id"] == "inc-bundle-01"
    assert bundle["sha256"] is not None
    assert len(bundle["sha256"]) == 64

    md_file = tmp_path / "postmortem-inc-bundle-01.md"
    json_file = tmp_path / "postmortem-inc-bundle-01.json"
    assert md_file.exists()
    assert json_file.exists()
    assert "[POSTMORTEM]" in md_file.read_text(encoding="utf-8")
