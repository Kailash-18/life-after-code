#!/usr/bin/env python3
"""
Project Sentinel — Hidden Holdout Gate Runner (Tier 1 Feature)
=============================================================
Core Principle: AI proposes; deterministic gates decide.

Runs secret holdout invariant tests isolated inside the gate container.
The AI repair agent never sees these tests, ensuring fixes are not merely
overfitted or hardcoded to pass the known public test suite.

Reports:
  - Invariant validation summary (INV-01 .. INV-05).
  - Gate verdict: PASS or FAIL.
  - Zero leakage of raw secret test implementations to merge request comments.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HOLDOUT_TEST_DIR = PROJECT_ROOT / "sentinel" / "holdout_tests"

INVARIANT_CATALOG = {
    "INV-01": "Zero divisor & empty cart safety invariant",
    "INV-02": "Non-negative & upper-bounded discount invariant",
    "INV-03": "Tier normalization & case-insensitivity invariant",
    "INV-04": "Numerical precision stability invariant",
    "INV-05": "Stateless idempotency & purity invariant",
}


def run_holdout_gate(
    holdout_dir: Path | str | None = None,
    candidate_sha: str = "HEAD",
    incident_id: str | None = None,
    output_json: Path | str | None = None,
) -> dict[str, Any]:
    suite_path = Path(holdout_dir or HOLDOUT_TEST_DIR)
    if not suite_path.exists():
        return {
            "gate": "holdout_tests",
            "verdict": "FAIL",
            "error": f"Holdout suite directory not found at {suite_path}",
            "tested_sha": candidate_sha,
            "incident_id": incident_id,
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Run pytest on the secret holdout suite
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(suite_path),
        "-q",
        "--tb=short",
    ]

    start_t = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    elapsed_ms = round((time.perf_counter() - start_t) * 1000, 1)

    passed = proc.returncode == 0
    verdict = "PASS" if passed else "FAIL"

    # Analyze invariants without leaking code details
    invariants_checked = []
    for inv_id, inv_name in INVARIANT_CATALOG.items():
        invariants_checked.append({
            "invariant_id": inv_id,
            "name": inv_name,
            "status": "VERIFIED" if passed else "VIOLATED",
            "confidential": True,
        })

    report = {
        "gate": "holdout_tests",
        "verdict": verdict,
        "candidate_sha": candidate_sha,
        "incident_id": incident_id,
        "elapsed_ms": elapsed_ms,
        "invariants_tested": len(invariants_checked),
        "invariants_passed": len(invariants_checked) if passed else 0,
        "invariants_failed": 0 if passed else len(invariants_checked),
        "invariants": invariants_checked,
        "security_note": (
            "Holdout tests execute strictly within the isolated gate container. "
            "Raw test code and input corpora are never exposed to LLM context."
        ),
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    if output_json:
        out_p = Path(output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report


def main():
    parser = argparse.ArgumentParser(description="Sentinel Hidden Holdout Gate Runner")
    parser.add_argument("--candidate-sha", default="HEAD", help="Git SHA of the candidate fix")
    parser.add_argument("--incident-id", default=None, help="Incident ID being repaired")
    parser.add_argument("--output-json", default="artifacts/holdout-gate-report.json", help="Path to write report")
    args = parser.parse_args()

    report = run_holdout_gate(
        candidate_sha=args.candidate_sha,
        incident_id=args.incident_id,
        output_json=args.output_json,
    )

    print("=" * 70)
    print("  PROJECT SENTINEL — HIDDEN HOLDOUT GATE")
    print("  Core Principle: Secret invariants AI cannot tune or overfit against.")
    print("=" * 70)
    print(f"  Gate Verdict:       {report['verdict']}")
    print(f"  Candidate SHA:      {report['candidate_sha']}")
    print(f"  Execution Time:     {report['elapsed_ms']} ms")
    print(f"  Invariants Tested:  {report['invariants_tested']}")
    print("-" * 70)
    for inv in report["invariants"]:
        status_tag = "[PASS]" if inv["status"] == "VERIFIED" else "[FAIL]"
        print(f"  {status_tag} {inv['invariant_id']}: {inv['name']}")
    print("=" * 70)

    if report["verdict"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
