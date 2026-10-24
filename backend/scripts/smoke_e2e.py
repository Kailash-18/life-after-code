#!/usr/bin/env python3
"""
DEV-ONLY smoke test: drives a running Sentinel backend through the whole recovery loop
over real HTTP with HMAC-signed events, then checks /status, the incident and its timeline.

It sends SYNTHETIC events. Never point it at the production backend used for the demo,
or the dashboard will show this fake incident. Use it against a local or staging instance.

Usage:
    SENTINEL_API_URL=http://localhost:8000 SENTINEL_HMAC_SECRET=... python backend/scripts/smoke_e2e.py
Exit code 0 = every check passed.
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

API = os.environ.get("SENTINEL_API_URL", "http://localhost:8000").rstrip("/")
SECRET = os.environ.get("SENTINEL_HMAC_SECRET", "sentinel-dev-secret-key-change-in-prod")
RUN = str(int(time.time()))
INC = f"inc-smoke-{RUN}"
BROKEN = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
FIX = "f00dfeed" + RUN.rjust(32, "0")
_job = int(RUN) * 100


def _request(method, path, body=None, headers=None):
    req = urllib.request.Request(API + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def send(etype, data=None, incident=INC, sha=BROKEN, source="sentinel/ci/smoke", artifact_url=None):
    global _job
    _job += 1
    now = datetime.now(UTC).isoformat()
    event = {"type": etype, "source": source, "pipeline_id": "1", "job_id": str(_job),
             "commit_sha": sha, "sent_at": now, "data": data or {}}
    if incident:
        event["incident_id"] = incident
    if artifact_url:
        event["artifact_url"] = artifact_url
    body = json.dumps(event).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return _request("POST", "/api/v1/events", body, {
        "Content-Type": "application/json", "X-Sentinel-Signature": sig, "X-Sentinel-Timestamp": now})


failures = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if not cond and detail else ""))
    if not cond:
        failures.append(name)


def step(etype, expect_status, **kw):
    code, body = send(etype, **kw)
    got = body.get("incident_status") if isinstance(body, dict) else None
    check(f"{etype} -> {expect_status}", code == 202 and got == expect_status, f"{code} {body}")


def main():
    code, body = _request("GET", "/api/v1/healthz")
    check("healthz", code == 200 and body.get("status") == "ok", str(body))

    # Security: unsigned and wrongly signed writes are refused.
    code, _ = _request("POST", "/api/v1/events", b"{}", {"Content-Type": "application/json"})
    check("unsigned event rejected (401)", code == 401)

    # Canary of the broken release fails the evaluator.
    send("deploy.canary_started", {"traffic_percent": 10, "revision_name": "smoke-00001"}, incident=None)
    send("evaluator.verdict", {"verdict": "FAIL", "target": "candidate", "traffic_percent": 10,
                               "error_rate": 0.3, "p95_ms": 250.0, "sample_size": 200},
         incident=None, source="sentinel/scripts/evaluator.py")

    step("incident.detected", "DETECTED", data={"breached_thresholds": ["error_rate 0.30 > 0.02"]},
         source="sentinel/scripts/evaluator.py")
    code, _ = send("recovery.verified", {"verdict": "PASS"}, source="sentinel/scripts/evaluator.py")
    check("skip to RECOVERED refused (409)", code == 409)
    step("rollback.completed", "ROLLED_BACK", data={"post_rollback_probe_ok": True})
    step("evidence.collected", "EVIDENCE_COLLECTED", data={"evidence_sha256": "ab" * 32},
         artifact_url="https://gitlab.com/example/-/jobs/1/artifacts/evidence.tar.gz")
    # If the server dispatches flows itself it may already be INVESTIGATING.
    code, inc = _request("GET", f"/api/v1/incidents/{INC}")
    if inc.get("status") == "EVIDENCE_COLLECTED":
        step("flow.started", "INVESTIGATING", data={"flow_session_id": f"smoke-{RUN}"})
    step("repair.proposed", "REPAIR_PROPOSED", data={"mr_iid": 1, "fix_sha": FIX})
    step("regression_proof.verdict", "VERIFYING", sha=FIX, data={
        "verdict": "PASS", "broken_sha": BROKEN, "fix_sha": FIX,
        "broken_run": {"outcome": "failed", "failure_type": "AssertionError"},
        "fix_run": {"outcome": "passed"}})
    step("integrity_gate.verdict", "VERIFYING", sha=FIX, data={"verdict": "PASS", "findings": []})
    step("merge.completed", "MERGED", sha=FIX)
    step("deploy.canary_started", "REDEPLOYING", sha=FIX, data={"traffic_percent": 10})
    code, _ = send("recovery.verified", {"verdict": "PASS"}, sha=FIX, source="gitlab/duo/agent")
    check("AI cannot declare recovery (400)", code == 400)
    step("recovery.verified", "RECOVERED", sha=FIX, source="sentinel/scripts/evaluator.py",
         data={"verdict": "PASS", "target": "candidate", "traffic_percent": 100,
               "error_rate": 0.001, "p95_ms": 35.0, "sample_size": 600})

    code, timeline = _request("GET", f"/api/v1/incidents/{INC}/timeline")
    types = [e["type"] for e in timeline] if code == 200 else []
    check("timeline ordered from detection to recovery",
          types[:1] == ["incident.detected"] and types[-1] == "recovery.verified", str(types))
    check("refused events visible in timeline", sum(1 for e in timeline if e.get("rejected")) >= 1)

    code, status = _request("GET", "/api/v1/status")
    cur = (status or {}).get("current_release") or {}
    check("/status shows fix release as known-good",
          cur.get("commit_sha") == FIX and cur.get("known_good") is True, str(cur))
    check("/status health is measured", status["system_health"]["error_rate"] == 0.001,
          str(status.get("system_health")))

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
