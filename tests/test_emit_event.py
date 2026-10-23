import json
import pytest
from sentinel.scripts.emit_event import sign_payload, load_event_schema

def test_load_event_schema():
    schema = load_event_schema()
    assert schema["title"] == "SentinelCiEvent"
    assert "type" in schema["properties"]
    assert "evaluator.verdict" in schema["properties"]["type"]["enum"]
    assert "recovery.verified" in schema["properties"]["type"]["enum"]

def test_sign_payload():
    secret = "test-secret-123"
    body = b'{"hello":"sentinel"}'
    sig = sign_payload(secret, body)
    assert sig.startswith("sha256=")
    assert len(sig) == 64 + 7
