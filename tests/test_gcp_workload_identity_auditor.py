"""
Unit tests for Google Cloud Workload Identity & Least Privilege IAM Auditor.
Devpost Transcend Hackathon: Google Cloud Bonus (+0.2).
"""

from pathlib import Path
from sentinel.scripts.gcp_workload_identity_auditor import GcpWorkloadIdentityAuditor, run_gcp_iam_audit


def test_gcp_iam_audit_happy_path():
    auditor = GcpWorkloadIdentityAuditor()
    report = auditor.audit_iam_posture()

    assert report["verdict"] == "PASS"
    assert report["workload_identity_federation_active"] is True
    assert report["static_service_account_keys_count"] == 0
    assert report["least_privilege_certified"] is True
    assert len(report["forbidden_role_violations"]) == 0


def test_gcp_iam_audit_output(tmp_path: Path):
    out_dir = tmp_path / "artifacts"
    report = run_gcp_iam_audit(output_dir=out_dir)

    out_file = out_dir / "gcp-workload-identity-audit.json"
    assert out_file.exists()
    assert report["verdict"] == "PASS"
