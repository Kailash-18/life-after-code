"""
Payload hygiene for everything the backend stores (Task R7).

Two layers:
1. Key-based redaction: values under keys that look sensitive (password, token, ...)
   are replaced with "[REDACTED]" before storage.
2. Value-based secret scan: after redaction, every remaining string is scanned for
   credential patterns (GitLab/GitHub/AWS/GCP tokens, private keys, the backend's own
   shared secrets). CI events containing one are rejected outright; GitLab webhook
   payloads (which we do not control) have matching values masked instead.

Error messages never echo the matched value.
"""

import re
from typing import Any

from app.config import settings

REDACTED = "[REDACTED]"

SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|auth|bearer|private[_-]?key|credential)"
)

# Named so findings can say *what* was found without revealing the value.
SECRET_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gitlab_token", re.compile(r"\bgl(?:pat|ptt|dt|rt|cbt|soat|ft|imt|agent|oas)-[0-9A-Za-z_\-]{20,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{30,}")),
    ("github_pat", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{40,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\s\S]{20,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[0-9A-Za-z\-]{10,}")),
    ("anthropic_or_openai_key", re.compile(r"\bsk-(?:ant-)?[0-9A-Za-z_\-]{24,}")),
    ("bearer_header", re.compile(r"(?i)\bbearer\s+[0-9A-Za-z_\-\.=]{20,}")),
    ("gcp_service_account_key", re.compile(r'"private_key_id"\s*:\s*"[0-9a-f]{20,}"')),
]


def redact_sensitive_keys(val: Any) -> Any:
    """Recursively replace values stored under sensitive-looking keys."""
    if isinstance(val, dict):
        cleaned: dict[str, Any] = {}
        for k, v in val.items():
            if SENSITIVE_KEY_PATTERN.search(str(k)):
                cleaned[k] = REDACTED
            else:
                cleaned[k] = redact_sensitive_keys(v)
        return cleaned
    if isinstance(val, list):
        return [redact_sensitive_keys(item) for item in val]
    return val


def _own_secrets() -> list[str]:
    """The backend's own shared secrets must never appear inside a stored payload."""
    return [s for s in (settings.hmac_secret, settings.gitlab_webhook_secret) if s and len(s) >= 8]


def find_secret_values(val: Any, path: str = "") -> list[dict[str, str]]:
    """Return findings as [{path, kind}] for every string that looks like a credential."""
    findings: list[dict[str, str]] = []
    if isinstance(val, dict):
        for k, v in val.items():
            findings.extend(find_secret_values(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(val, list):
        for i, item in enumerate(val):
            findings.extend(find_secret_values(item, f"{path}[{i}]"))
    elif isinstance(val, str):
        if val == REDACTED:
            return findings
        for kind, pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(val):
                findings.append({"path": path or "root", "kind": kind})
                break
        else:
            for own in _own_secrets():
                if own in val:
                    findings.append({"path": path or "root", "kind": "sentinel_shared_secret"})
                    break
    return findings


def mask_secret_values(val: Any) -> Any:
    """Recursively replace any string that matches a secret pattern (used for webhooks)."""
    if isinstance(val, dict):
        return {k: mask_secret_values(v) for k, v in val.items()}
    if isinstance(val, list):
        return [mask_secret_values(item) for item in val]
    if isinstance(val, str) and find_secret_values(val):
        return REDACTED
    return val


def sanitize_for_storage(val: Any) -> Any:
    """Key redaction followed by value masking. Safe default for untrusted payloads."""
    return mask_secret_values(redact_sensitive_keys(val))
