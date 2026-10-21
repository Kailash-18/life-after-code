"""
Unit tests for Sentinel 9-Stage DevSecOps Lifecycle Orchestrator.
Validates all 9 lifecycle stages, autonomy level, and artifact generation.
"""

from pathlib import Path
from sentinel.scripts.lifecycle_orchestrator import LifecycleOrchestrator, run_lifecycle_audit, STAGES_CATALOG


def test_lifecycle_orchestrator_all_nine_stages():
    orch = LifecycleOrchestrator()
    report = orch.orchestrate_lifecycle_audit()

    assert report["total_stages"] == 9
    assert report["stages_covered"] == 9
    assert report["coverage_percentage"] == 100.0
    assert report["verdict"] == "FULL_LIFECYCLE_CERTIFIED"
    assert "Hands-off" in report["autonomy_level"]

    expected_stages = {
        "plan", "create", "verify", "package", "secure",
        "release", "configure", "monitor", "govern"
    }
    actual_stages = {s["stage"] for s in report["stages"]}
    assert expected_stages == actual_stages


def test_lifecycle_orchestrator_report_output(tmp_path: Path):
    out_dir = tmp_path / "artifacts"
    report = run_lifecycle_audit(output_dir=out_dir)

    out_file = out_dir / "devsecops-9-stage-lifecycle-report.json"
    assert out_file.exists()
    assert report["coverage_percentage"] == 100.0
