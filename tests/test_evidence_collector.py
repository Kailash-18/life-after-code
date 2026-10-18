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
