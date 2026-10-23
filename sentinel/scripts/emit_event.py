#!/usr/bin/env python3
"""
Project Sentinel — Authoritative CI Event Emitter (Task K11)
Emits cryptographically signed (HMAC-SHA256) lifecycle and gate events to the Sentinel Backend API.
Enforces docs/contracts/event.schema.json before dispatching.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

import jsonschema

DEFAULT_BACKEND_URL = os.environ.get("SENTINEL_BACKEND_URL", "http://localhost:8000")
DEFAULT_HMAC_SECRET = os.environ.get(
    "SENTINEL_HMAC_SECRET", "sentinel-dev-secret-key-change-in-prod"
)
SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "contracts" / "event.schema.json"


def get_git_commit_sha() -> str:
    env_sha = os.environ.get("CI_COMMIT_SHA")
    if env_sha:
        return env_sha
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
        return out.strip()
    except Exception:
        return "0000000000000000000000000000000000000000"


def load_event_schema() -> dict[str, Any]:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Contract schema missing at {SCHEMA_PATH}")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def sign_payload(secret: str, body_bytes: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def emit_event(
    event_type: str,
    source: str,
    pipeline_id: str | None = None,
    job_id: str | None = None,
    commit_sha: str | None = None,
    release_id: str | None = None,
    incident_id: str | None = None,
    artifact_url: str | None = None,
    data: dict[str, Any] | None = None,
    backend_url: str | None = None,
    secret: str | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    backend = (backend_url or DEFAULT_BACKEND_URL).rstrip("/")
    key = secret or DEFAULT_HMAC_SECRET
    pipe_id = pipeline_id or os.environ.get("CI_PIPELINE_ID") or str(int(time.time()))
    jb_id = job_id or os.environ.get("CI_JOB_ID") or f"{int(time.time() * 1000) % 100000000}"
    sha = commit_sha or get_git_commit_sha()
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload: dict[str, Any] = {
        "type": event_type,
        "source": source,
        "pipeline_id": str(pipe_id),
        "job_id": str(jb_id),
        "commit_sha": sha,
        "sent_at": now_iso,
        "data": data or {},
    }

    if release_id:
        payload["release_id"] = release_id
    if incident_id:
        payload["incident_id"] = incident_id
    if artifact_url:
        payload["artifact_url"] = artifact_url

    # 1. Strict Contract Validation against JSON Schema
    schema = load_event_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(payload))
    if errors:
        msg = "; ".join(f"{e.path}: {e.message}" for e in errors)
        raise ValueError(f"Event failed contract schema validation: {msg}")

    body_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = sign_payload(key, body_bytes)

    headers = {
        "Content-Type": "application/json",
        "X-Sentinel-Signature": signature,
        "X-Sentinel-Timestamp": now_iso,
    }

    target_endpoint = f"{backend}/api/v1/events"
    req = urllib.request.Request(
        target_endpoint,
        data=body_bytes,
        headers=headers,
        method="POST",
    )

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status_code = resp.status
                resp_data = json.loads(resp.read().decode("utf-8"))
                return {
                    "status_code": status_code,
                    "response": resp_data,
                    "event": payload,
                }
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {e.code}: {err_body}")
            if e.code in (400, 401, 409):
                # Non-retryable client errors
                raise last_error
        except Exception as e:
            last_error = e

        if attempt < max_retries:
            time.sleep(0.5 * (2 ** (attempt - 1)))

    raise RuntimeError(f"Failed to emit event to {target_endpoint} after {max_retries} attempts: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit signed CI/CD events to Sentinel backend")
    parser.add_argument("--type", required=True, help="Lifecycle event type (e.g. deploy.canary_started)")
    parser.add_argument("--source", required=True, help="Originating script or CI stage name")
    parser.add_argument("--pipeline-id", help="GitLab CI Pipeline ID")
    parser.add_argument("--job-id", help="GitLab CI Job ID")
    parser.add_argument("--commit-sha", help="Git commit SHA")
    parser.add_argument("--release-id", help="Sentinel release identifier (rel-*)")
    parser.add_argument("--incident-id", help="Sentinel incident identifier (inc-*)")
    parser.add_argument("--artifact-url", help="URL to evidence bundle or report")
    parser.add_argument("--data", help="JSON string or file path containing event data")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL, help="Sentinel backend API base URL")
    parser.add_argument("--secret", default=DEFAULT_HMAC_SECRET, help="Shared HMAC secret")

    args = parser.parse_args()

    event_data: dict[str, Any] = {}
    if args.data:
        if os.path.exists(args.data):
            with open(args.data, encoding="utf-8") as f:
                event_data = json.load(f)
        else:
            event_data = json.loads(args.data)

    try:
        res = emit_event(
            event_type=args.type,
            source=args.source,
            pipeline_id=args.pipeline_id,
            job_id=args.job_id,
            commit_sha=args.commit_sha,
            release_id=args.release_id,
            incident_id=args.incident_id,
            artifact_url=args.artifact_url,
            data=event_data,
            backend_url=args.backend_url,
            secret=args.secret,
        )
        print(f"==> Event {args.type} emitted successfully! Response: {json.dumps(res['response'])}")
    except Exception as e:
        print(f"ERROR: Event emission failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
