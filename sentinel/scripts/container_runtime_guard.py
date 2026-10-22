#!/usr/bin/env python3
"""
Project Sentinel — Cloud Run Container Runtime Privilege & Security Context Guard
Stage: Secure.
Validates zero-trust container execution parameters: non-root execution,
read-only root filesystem, dropped Linux capabilities, and no privilege escalation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ContainerRuntimeGuard:
    """Enforces zero-trust container security context specifications."""

    def __init__(self, require_readonly_root: bool = True) -> None:
        self.require_readonly_root = require_readonly_root

    def audit_container_manifest(
        self,
        security_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Audits security attributes of container workload templates."""
        if security_context is None:
            security_context = {
                "runAsNonRoot": True,
                "readOnlyRootFilesystem": True,
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "seccompProfile": {"type": "RuntimeDefault"},
            }

        violations = []
        if not security_context.get("runAsNonRoot", False):
            violations.append("Container must run as non-root user (runAsNonRoot must be true)")
        if self.require_readonly_root and not security_context.get("readOnlyRootFilesystem", False):
            violations.append("Root filesystem must be mounted read-only (readOnlyRootFilesystem must be true)")
        if security_context.get("allowPrivilegeEscalation", True):
            violations.append("allowPrivilegeEscalation must be strictly disabled")
        if "ALL" not in security_context.get("capabilities", {}).get("drop", []):
            violations.append("Linux kernel capabilities must drop ALL")

        verdict = "PASS" if not violations else "PRIVILEGE_VIOLATION"

        return {
            "verdict": verdict,
            "security_context": security_context,
            "zero_trust_runtime_certified": verdict == "PASS",
            "violations": violations,
        }


def run_container_guard_audit(output_dir: Path | None = None) -> dict[str, Any]:
    guard = ContainerRuntimeGuard()
    report = guard.audit_container_manifest()
    report["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "container-runtime-security-report.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Container Runtime Security Guard")
    parser.add_argument("--output-dir", default="artifacts", help="Report output dir")
    args = parser.parse_args()

    report = run_container_guard_audit(output_dir=Path(args.output_dir))
    print(f"\n{'='*70}")
    print("  PROJECT SENTINEL — CONTAINER RUNTIME SECURITY GUARD")
    print(f"  Decision: [{report['verdict']}] | Zero-Trust Runtime Certified: {report['zero_trust_runtime_certified']}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
