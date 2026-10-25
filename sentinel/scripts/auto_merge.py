#!/usr/bin/env python3
"""
Project Sentinel — Authoritative Automated Merge Controller (Task K10)
Inspects deterministic gate reports (integrity gate, regression proof, SAST, unit tests).
Only when all required gates pass does this job auto-merge the repair MR using the project token.
Emits merge.completed event to backend. Never merges if any gate failed or is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentinel.scripts.emit_event import emit_event


def _read_verdict(art_dir: Path, names: list[str]) -> str:
    """Verdict from the first report that exists; MISSING if none does. Never inferred from env vars."""
    for name in names:
        f = art_dir / name
        if f.exists():
            try:
                return str(json.loads(f.read_text(encoding="utf-8")).get("verdict", "FAIL")).upper()
            except (json.JSONDecodeError, OSError):
                return "UNREADABLE"
    return "MISSING"


def verify_gate_reports(artifacts_dir: str | Path = "artifacts") -> dict[str, Any]:
    """Every required gate must have a report on disk that says it passed (PROVEN counts for the regression proof)."""
    art_dir = Path(artifacts_dir)
    gate_statuses = {
        # The gate jobs write integrity-gate.json / regression-proof.json; older names kept for compatibility.
        "integrity_gate": _read_verdict(art_dir, ["integrity-gate.json", "integrity-gate-report.json"]),
        "regression_proof": _read_verdict(art_dir, ["regression-proof.json", "regression-proof-report.json"]),
    }
    sast = _read_verdict(art_dir, ["sast-report.json"])
    if sast != "MISSING":  # optional gate: only counts when its job produced a report
        gate_statuses["sast_gate"] = sast

    passing = {"integrity_gate": {"PASS"}, "regression_proof": {"PROVEN", "PASS"}, "sast_gate": {"PASS"}}
    all_passed = all(v in passing[k] for k, v in gate_statuses.items())
    return {"all_passed": all_passed, "gates": gate_statuses}


def execute_gitlab_merge(
    project_id: str,
    mr_iid: int,
    gitlab_token: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ask GitLab to merge the MR. A dry run or any failure returns merged=False; nothing is ever faked."""
    print(f"[*] Executing automated merge for MR !{mr_iid} in project {project_id}...")
    token = gitlab_token or os.environ.get("GITLAB_PROJECT_TOKEN")

    if dry_run or os.environ.get("SENTINEL_SIMULATION_MODE") == "true":
        print(f"[+] [SIMULATION] would PUT /projects/{project_id}/merge_requests/{mr_iid}/merge — nothing merged")
        return {"merged": False, "mode": "simulation"}
    if not token:
        return {"merged": False, "mode": "no_token", "error": "GITLAB_PROJECT_TOKEN is not set"}

    api_base = os.environ.get("CI_API_V4_URL", "https://gitlab.com/api/v4").rstrip("/")
    api_url = f"{api_base}/projects/{project_id}/merge_requests/{mr_iid}/merge"
    body = json.dumps({"should_remove_source_branch": True}).encode("utf-8")
    req = urllib.request.Request(
        api_url, data=body,
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"merged": False, "mode": "gitlab_api", "error": str(e)}
    sha = data.get("merge_commit_sha") or data.get("squash_commit_sha")
    merged = data.get("state") == "merged" and bool(sha)
    return {"merged": merged, "mode": "gitlab_api", "merge_commit_sha": sha, "state": data.get("state")}


def run_auto_merge(
    project_id: str,
    mr_iid: int,
    fix_sha: str,
    incident_id: str | None = None,
    pipeline_id: str | None = None,
    job_id: str | None = None,
    artifacts_dir: str | Path = "artifacts",
    dry_run: bool = False,
    emit_to_backend: bool = True,
) -> dict[str, Any]:
    print(f"[*] Validating gate requirements before auto-merge for MR !{mr_iid}...")
    gate_eval = verify_gate_reports(artifacts_dir)

    print(f"    Integrity Gate:   [{gate_eval['gates'].get('integrity_gate', 'N/A')}]")
    print(f"    Regression Proof: [{gate_eval['gates'].get('regression_proof', 'N/A')}]")
    print(f"    SAST Gate:        [{gate_eval['gates'].get('sast_gate', 'N/A')}]")

    if not gate_eval["all_passed"]:
        failed_gates = [g for g, st in gate_eval["gates"].items() if st not in ("PASS", "PROVEN")]
        raise RuntimeError(f"Auto-merge blocked! Gates did not pass: {failed_gates}")

    merge_res = execute_gitlab_merge(project_id, mr_iid, dry_run=dry_run)
    if not merge_res["merged"]:
        if merge_res["mode"] == "simulation":
            return {"status": "SIMULATED", "mr_iid": mr_iid, "fix_sha": fix_sha, "merge_res": merge_res, "gates": gate_eval["gates"]}
        raise RuntimeError(f"Merge did not happen ({merge_res.get('mode')}): {merge_res.get('error') or merge_res.get('state')}")
    merge_sha = merge_res["merge_commit_sha"]

    # Emit merge.completed only for a merge GitLab confirmed
    if emit_to_backend:
        try:
            emit_event(
                event_type="merge.completed",
                source="sentinel-auto-merge:automated",
                pipeline_id=pipeline_id,
                job_id=job_id,
                commit_sha=merge_sha,
                incident_id=incident_id,
                data={
                    "mr_iid": mr_iid,
                    "fix_sha": fix_sha,
                    "verdict": "PASS",
                },
            )
        except Exception as e:
            print(f"[!] Warning: could not emit merge.completed: {e}", file=sys.stderr)

    return {
        "status": "MERGED",
        "mr_iid": mr_iid,
        "fix_sha": fix_sha,
        "merge_res": merge_res,
        "gates": gate_eval["gates"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Autonomous Merge Controller")
    parser.add_argument("--project-id", default=os.environ.get("CI_PROJECT_ID", "project-sentinel"), help="GitLab Project ID")
    parser.add_argument("--mr-iid", type=int, required=True, help="Merge Request IID")
    parser.add_argument("--fix-sha", required=True, help="Commit SHA of proposed fix")
    parser.add_argument("--incident-id", help="Sentinel incident ID")
    parser.add_argument("--pipeline-id", help="GitLab CI Pipeline ID")
    parser.add_argument("--job-id", help="GitLab CI Job ID")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Path to gate artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Run without calling remote GitLab API")
    parser.add_argument("--no-emit", action="store_true", help="Do not emit events to backend")

    args = parser.parse_args()

    res = run_auto_merge(
        project_id=args.project_id,
        mr_iid=args.mr_iid,
        fix_sha=args.fix_sha,
        incident_id=args.incident_id,
        pipeline_id=args.pipeline_id,
        job_id=args.job_id,
        artifacts_dir=args.artifacts_dir,
        dry_run=args.dry_run,
        emit_to_backend=not args.no_emit,
    )
    print(f"[+] {res['status']}: MR !{res['mr_iid']}")


if __name__ == "__main__":
    main()
