import hashlib
import json
import pytest
from sentinel.scripts.evidence_collector import redact_secrets

def test_redact_secrets_cleans_credentials():
    dirty_text = (
        "Config: api_key='sk-1234567890abcdef12345' and token = 'glpat-abcdef12345678901234' "
        "and auth: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.abcdef"
    )
    clean_text, count = redact_secrets(dirty_text)
    assert count >= 2
    assert "sk-1234567890abcdef12345" not in clean_text
    assert "glpat-abcdef12345678901234" not in clean_text
    assert "[REDACTED_BY_SENTINEL_EVIDENCE_GATE]" in clean_text


def test_evidence_bundle_schema_validation(tmp_path):
    import jsonschema
    from pathlib import Path
    from sentinel.scripts.evidence_collector import build_evidence_bundle

    schema_path = Path("docs/contracts/evidence-bundle.schema.json")
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    bundle = build_evidence_bundle(
        incident_id="inc-99999",
        release_id="rel-v1_0_0-abc1234",
        service_name="sentinel-target-app",
        candidate_revision="cand-001",
        output_dir=tmp_path,
        emit_to_backend=False,
        dry_run=True,
    )

    jsonschema.validate(instance=bundle, schema=schema)
    assert bundle["schema_version"] == "1.0"
    assert bundle["incident_id"] == "inc-99999"
    assert "evidence_sha256" in bundle
    assert len(bundle["evidence_sha256"]) == 64

