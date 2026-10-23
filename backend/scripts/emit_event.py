#!/usr/bin/env python3
"""
Send one HMAC-signed Sentinel event from a GitLab CI job. Python stdlib only.

    python backend/scripts/emit_event.py --type evaluator.verdict \
        --data '{"verdict": "FAIL", "target": "candidate", "traffic_percent": 10,
                 "error_rate": 0.26, "p95_ms": 210.0, "sample_size": 300}'

    # Regression-proof / Integrity Gate reports are converted for you:
    python backend/scripts/emit_event.py --type regression_proof.verdict \
        --incident-id "$INCIDENT_ID" --from-regression-proof proof.json --artifact-url "$JOB_URL"
    python backend/scripts/emit_event.py --type integrity_gate.verdict \
        --incident-id "$INCIDENT_ID" --from-integrity-gate integrity.json

Environment (GitLab sets the CI_* ones):
    SENTINEL_API_URL       backend base URL
    SENTINEL_HMAC_SECRET   protected + masked CI variable (never printed)
    CI_PIPELINE_ID, CI_JOB_ID, CI_COMMIT_SHA, CI_JOB_NAME

Retries (with a fresh signature and timestamp each time) on network errors, HTTP 5xx and
retryable rejections such as UNKNOWN_INCIDENT. Safe: the backend de-duplicates on
(job_id, type, traffic_percent).

Exit codes: 0 accepted | 2 rejected by the backend | 3 retries exhausted | 4 bad usage.
A rejection fails the job on purpose: the pipeline must not look green when Sentinel
refused to record a step. Use --warn-only for best-effort events.
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

EXIT_OK, EXIT_REJECTED, EXIT_EXHAUSTED, EXIT_USAGE = 0, 2, 3, 4


def regression_proof_data(report: dict) -> dict:
    """Map sentinel/scripts/regression_proof.py JSON to event data (drops raw logs)."""

    def run(r: dict) -> dict:
        out = {"outcome": r.get("outcome", "error"), "failure_type": r.get("failure_type") or None}
        if isinstance(r.get("exit_code"), int):
            out["exit_code"] = r["exit_code"]
        return out

    data = {
        "verdict": "PASS" if report.get("verdict") == "PROVEN" else "FAIL",
        "broken_sha": report.get("broken_sha"),
        "fix_sha": report.get("fix_sha"),
        "broken_run": run(report.get("broken_run") or {}),
        "fix_run": run(report.get("fix_run") or {}),
    }
    if report.get("rejection_reason"):
        data["reason"] = str(report["rejection_reason"])[:500]
    if not report.get("fix_run"):
        data.pop("fix_run")
    return {k: v for k, v in data.items() if v is not None}


def integrity_gate_data(report: dict) -> dict:
    """Map sentinel/scripts/integrity_gate.py JSON to event data."""
    findings = [
        f"{f.get('severity', '?')} {f.get('rule_id', '?')} {f.get('file', '')}: {f.get('message', '')}"[:300]
        for f in report.get("findings", [])
    ]
    data = {"verdict": "PASS" if report.get("verdict") == "PASS" else "FAIL", "findings": findings}
    blocking = [f for f in report.get("findings", []) if f.get("severity") == "BLOCKING"]
    if blocking:
        data["reason"] = f"Integrity Gate: {len(blocking)} blocking finding(s)"
    return data


def build_event(args, env) -> dict:
    data: dict = {}
    if args.data:
        data.update(json.loads(args.data))
    if args.data_file:
        with open(args.data_file, encoding="utf-8") as f:
            data.update(json.load(f))
    if args.from_regression_proof:
        with open(args.from_regression_proof, encoding="utf-8") as f:
            data.update(regression_proof_data(json.load(f)))
    if args.from_integrity_gate:
        with open(args.from_integrity_gate, encoding="utf-8") as f:
            data.update(integrity_gate_data(json.load(f)))

    event = {
        "type": args.type,
        "source": args.source or f"gitlab-ci/{env.get('CI_JOB_NAME', 'job')}",
        "pipeline_id": str(args.pipeline_id or env.get("CI_PIPELINE_ID", "")),
        "job_id": str(args.job_id or env.get("CI_JOB_ID", "")),
        "commit_sha": args.commit_sha or env.get("CI_COMMIT_SHA", ""),
        "data": data,
    }
    for key in ("release_id", "incident_id", "artifact_url"):
        value = getattr(args, key)
        if value:
            event[key] = value
    return event


def sign_and_send(api: str, secret: str, event: dict, timeout: float = 15.0) -> tuple[int, dict]:
    now = datetime.now(UTC).isoformat()
    event = dict(event, sent_at=now)
    body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        api.rstrip("/") + "/api/v1/events",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Sentinel-Signature": signature,
            "X-Sentinel-Timestamp": now,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"{}")
        except ValueError:
            payload = {}
        return e.code, payload


def _error(payload: dict) -> dict:
    return payload.get("error") or (payload.get("detail") or {}).get("error") or {}


def emit(api: str, secret: str, event: dict, attempts: int = 5, backoff: float = 2.0, sleep=time.sleep) -> int:
    last = "no attempt made"
    for attempt in range(1, attempts + 1):
        try:
            code, payload = sign_and_send(api, secret, event)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            code, payload, last = 0, {}, f"network error: {exc}"
        if 200 <= code < 300:
            print(json.dumps({"accepted": True, "http": code, **payload}))
            return EXIT_OK
        err = _error(payload)
        retryable = code == 0 or code >= 500 or code == 429 or bool(err.get("retryable"))
        if code:
            last = f"HTTP {code} {err.get('code', '')}: {err.get('message', '')}".strip()
        if not retryable:
            print(json.dumps({"accepted": False, "http": code, "error": err}), file=sys.stderr)
            return EXIT_REJECTED
        if attempt < attempts:
            delay = backoff * (2 ** (attempt - 1))
            print(f"[emit_event] attempt {attempt} failed ({last}); retrying in {delay:.0f}s", file=sys.stderr)
            sleep(delay)
    print(f"[emit_event] giving up after {attempts} attempts: {last}", file=sys.stderr)
    return EXIT_EXHAUSTED


def parse_args(argv):
    p = argparse.ArgumentParser(description="Send a signed Sentinel CI event.")
    p.add_argument("--type", required=True, help="event type, e.g. evaluator.verdict")
    p.add_argument("--source", help="defaults to gitlab-ci/$CI_JOB_NAME; evaluator jobs must contain 'evaluator'")
    p.add_argument("--incident-id")
    p.add_argument("--release-id")
    p.add_argument("--artifact-url")
    p.add_argument("--commit-sha", help="defaults to $CI_COMMIT_SHA")
    p.add_argument("--pipeline-id", help="defaults to $CI_PIPELINE_ID")
    p.add_argument("--job-id", help="defaults to $CI_JOB_ID")
    p.add_argument("--data", help="JSON object for event.data")
    p.add_argument("--data-file", help="file with a JSON object merged into event.data")
    p.add_argument("--from-regression-proof", help="regression_proof.py --output-json report")
    p.add_argument("--from-integrity-gate", help="integrity_gate.py --output-json report")
    p.add_argument("--attempts", type=int, default=5)
    p.add_argument("--warn-only", action="store_true", help="exit 0 even if the event is not recorded")
    p.add_argument("--dry-run", action="store_true", help="print the unsigned event and exit")
    return p.parse_args(argv)


def main(argv=None, env=None) -> int:
    env = os.environ if env is None else env
    args = parse_args(argv)
    try:
        event = build_event(args, env)
    except (OSError, ValueError) as exc:
        print(f"[emit_event] could not build event: {exc}", file=sys.stderr)
        return EXIT_USAGE
    missing = [k for k in ("pipeline_id", "job_id", "commit_sha") if not event[k]]
    if missing:
        print(f"[emit_event] missing {missing}: run inside GitLab CI or pass the flags", file=sys.stderr)
        return EXIT_USAGE
    if args.dry_run:
        print(json.dumps(event, indent=2))
        return EXIT_OK
    api, secret = env.get("SENTINEL_API_URL"), env.get("SENTINEL_HMAC_SECRET")
    if not api or not secret:
        print("[emit_event] SENTINEL_API_URL and SENTINEL_HMAC_SECRET must be set", file=sys.stderr)
        return EXIT_USAGE
    code = emit(api, secret, event, attempts=max(1, args.attempts))
    return EXIT_OK if args.warn_only else code


if __name__ == "__main__":
    sys.exit(main())
