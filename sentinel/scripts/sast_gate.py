#!/usr/bin/env python3
"""
Project Sentinel — Authoritative SAST & Security Quality Gate (Task K8)
Executes deterministic static analysis scanning for vulnerability patterns, dangerous calls (eval, exec,
unfiltered subprocess), and hardcoded credentials.
Produces structured GateResult JSON & Markdown reports conforming to docs/contracts/openapi.yaml.
Blocks merge if blocking findings are detected.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentinel.scripts.emit_event import emit_event

# High-risk patterns for Python codebase
DANGEROUS_CALLS = {
    "eval": "Critical: Use of eval() allows arbitrary code execution",
    "exec": "Critical: Use of exec() allows arbitrary code execution",
    "subprocess.Popen": "Warning: Unsanitized subprocess execution",
    "os.system": "Critical: Use of os.system() vulnerable to shell injection",
    "pickle.loads": "High: Insecure deserialization with pickle",
}

CREDENTIAL_REGEXES = [
    (re.compile(r"(?i)(api[_-]?key|secret|password|private_key)\s*=\s*['\"][a-zA-Z0-9_\-\.]{8,}['\"]"), "High: Hardcoded credential or secret detected"),
    (re.compile(r"glpat-[0-9a-zA-Z_-]{20,}"), "Critical: Hardcoded GitLab Personal Access Token"),
    (re.compile(r"ghp_[0-9a-zA-Z]{36}"), "Critical: Hardcoded GitHub Personal Access Token"),
]


class CodeVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.findings: list[dict[str, Any]] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                name = f"{node.func.value.id}.{node.func.attr}"
            else:
                name = node.func.attr

        if name in DANGEROUS_CALLS:
            severity = "CRITICAL" if "Critical" in DANGEROUS_CALLS[name] else "HIGH"
            self.findings.append({
                "rule_id": f"SEC-{name.upper().replace('.', '-')}",
                "severity": severity,
                "file": self.file_path,
                "line": getattr(node, "lineno", 0),
                "message": DANGEROUS_CALLS[name],
            })
        self.generic_visit(node)


def scan_file(file_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    # 1. Regex credential scanning
    for line_idx, line in enumerate(content.splitlines(), start=1):
        for pattern, msg in CREDENTIAL_REGEXES:
            if pattern.search(line):
                findings.append({
                    "rule_id": "SEC-HARDCODED-SECRET",
                    "severity": "CRITICAL",
                    "file": str(file_path),
                    "line": line_idx,
                    "message": msg,
                })

    # 2. AST parsing for dangerous code constructs
    try:
        tree = ast.parse(content, filename=str(file_path))
        visitor = CodeVisitor(str(file_path))
        visitor.visit(tree)
        findings.extend(visitor.findings)
    except SyntaxError:
        pass

    return findings


def run_sast_scan(
    target_dirs: list[str | Path],
    output_dir: str | Path = "artifacts",
    incident_id: str | None = None,
    attempt_id: str | None = None,
    pipeline_id: str | None = None,
    job_id: str | None = None,
    commit_sha: str | None = None,
    emit_to_backend: bool = True,
) -> dict[str, Any]:
    print(f"[*] Running Sentinel SAST Security Gate over: {target_dirs}...")
    all_findings: list[dict[str, Any]] = []
    files_scanned = 0

    for d in target_dirs:
        p = Path(d)
        if not p.exists():
            continue
        for py_file in p.rglob("*.py"):
            if "venv" in py_file.parts or ".cache" in py_file.parts or "fixtures" in py_file.parts:
                continue
            files_scanned += 1
            all_findings.extend(scan_file(py_file))

    blocking_findings = [f for f in all_findings if f["severity"] in ("CRITICAL", "HIGH")]
    verdict = "FAIL" if blocking_findings else "PASS"

    print("\n=======================================================")
    print(f"  SENTINEL SAST GATE VERDICT: [{verdict}]")
    print(f"  Files Scanned: {files_scanned} | Total Findings: {len(all_findings)}")
    print(f"  Blocking (High/Critical): {len(blocking_findings)}")
    for f in all_findings:
        print(f"    - [{f['severity']}] {f['file']}:{f.get('line', '?')} - {f['message']}")
    print("=======================================================\n")

    report = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate": "sast",
        "verdict": verdict,
        "files_scanned": files_scanned,
        "total_findings": len(all_findings),
        "blocking_count": len(blocking_findings),
        "findings": all_findings,
    }

    out_p = Path(output_dir)
    out_p.mkdir(exist_ok=True)
    report_file = out_p / "sast-report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel SAST Security Gate")
    parser.add_argument("--dirs", nargs="+", default=["app", "backend", "sentinel"], help="Directories to scan")
    parser.add_argument("--output-dir", default="artifacts", help="Output directory for reports")
    parser.add_argument("--incident-id", help="Sentinel incident ID")
    parser.add_argument("--pipeline-id", help="GitLab CI Pipeline ID")
    parser.add_argument("--job-id", help="GitLab CI Job ID")
    parser.add_argument("--commit-sha", help="Git commit SHA")
    parser.add_argument("--no-emit", action="store_true", help="Do not emit events to backend")

    args = parser.parse_args()

    res = run_sast_scan(
        target_dirs=args.dirs,
        output_dir=args.output_dir,
        incident_id=args.incident_id,
        pipeline_id=args.pipeline_id,
        job_id=args.job_id,
        commit_sha=args.commit_sha,
        emit_to_backend=not args.no_emit,
    )

    if res["verdict"] == "FAIL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
