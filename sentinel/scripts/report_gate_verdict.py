#!/usr/bin/env python3
"""
Project Sentinel — report a verification gate's verdict to the backend.

Reads the JSON report written by regression_proof.py or integrity_gate.py and emits the
matching signed event (regression_proof.verdict / integrity_gate.verdict) through emit_event.py.

The verdict is copied from the report, never computed here:
  regression proof  PROVEN -> PASS, anything else (or a missing report) -> FAIL
  integrity gate    PASS   -> PASS, anything else (or a missing report) -> FAIL

Usage (inside a repair-MR pipeline):
  python sentinel/scripts/report_gate_verdict.py --gate regression_proof \
      --report artifacts/regression-proof.json --incident-id inc-123
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from sentinel.scripts.emit_event import emit_event  # noqa: E402

GATES = {
    "regression_proof": ("regression_proof.verdict", "sentinel/scripts/regression_proof.py"),
    "integrity": ("integrity_gate.verdict", "sentinel/scripts/integrity_gate.py"),
}
SHA_RE = re.compile(r"^[a-f0-9]{7,40}$")


def incident_from_branch(branch: str | None) -> str | None:
    """duo/fix/inc-123 -> inc-123 (the repair-branch convention)."""
    if branch and branch.startswith("duo/fix/"):
        return branch[len("duo/fix/"):] or None
    return None


def build_data(gate: str, report: dict[str, Any] | None) -> dict[str, Any]:
    fix_sha = (os.environ.get("CI_COMMIT_SHA") or "").lower()
    data: dict[str, Any] = {}
    if SHA_RE.match(fix_sha):
        data["fix_sha"] = fix_sha
    mr = os.environ.get("CI_MERGE_REQUEST_IID")
    if mr and mr.isdigit():
        data["mr_iid"] = int(mr)
    if gate == "regression_proof":
        data["kind"] = "regression_proof"

    if report is None:
        data["verdict"] = "FAIL"
        data["findings"] = ["REPORT_MISSING: the gate did not write a report"]
        return data

    if gate == "regression_proof":
        proven = report.get("verdict") == "PROVEN"
        data["verdict"] = "PASS" if proven else "FAIL"
        data["proof_verdict"] = report.get("verdict", "UNKNOWN")
        if not proven and report.get("rejection_reason"):
            data["findings"] = [str(report["rejection_reason"])]
        for key in ("broken_run", "fix_run"):
            run = report.get(key) or {}
            if run:
                data[key] = {k: run.get(k) for k in ("exit_code", "outcome", "failure_type") if k in run}
    else:
        passed = report.get("verdict") == "PASS"
        data["verdict"] = "PASS" if passed else "FAIL"
        data["findings"] = [str(f.get("rule_id") or f.get("message") or "finding") for f in report.get("findings", [])
                            if f.get("severity", "BLOCKING") == "BLOCKING"]
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gate", required=True, choices=sorted(GATES))
    ap.add_argument("--report", required=True, help="Path to the gate's JSON report")
    ap.add_argument("--incident-id", default=None, help="Defaults to the id in CI_MERGE_REQUEST_SOURCE_BRANCH_NAME")
    ap.add_argument("--artifact-url", default=None, help="Defaults to this job's artifacts URL")
    ap.add_argument("--dry-run", action="store_true", help="Print the event data instead of sending it")
    args = ap.parse_args()

    incident = args.incident_id or incident_from_branch(os.environ.get("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME"))
    path = Path(args.report)
    report = None
    if path.exists():
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = None
    data = build_data(args.gate, report)
    event_type, source = GATES[args.gate]
    artifact = args.artifact_url or (f"{os.environ['CI_JOB_URL']}/artifacts/browse" if os.environ.get("CI_JOB_URL") else None)

    if args.dry_run:
        print(json.dumps({"type": event_type, "source": source, "incident_id": incident, "artifact_url": artifact, "data": data}, indent=2))
        return 0
    if not incident:
        print("[!] No incident id (not a duo/fix/* branch and none given); nothing reported.", file=sys.stderr)
        return 0
    try:
        res = emit_event(event_type, source, incident_id=incident, artifact_url=artifact, data=data)
        print(f"[+] {event_type} reported for {incident}: {data['verdict']} (HTTP {res['status_code']})")
    except Exception as exc:  # reporting must never change the gate's own outcome
        print(f"[!] Could not report {event_type} to the backend: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
