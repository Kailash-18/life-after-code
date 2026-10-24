"""
Unit tests for Sentinel Canary Deployment Controller (Task K4).
Validates strategy recommendations, tag-isolated zero-traffic candidate deployments,
traffic split adjustment, simulation mode, and artifact generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.canary_deploy import (
    adjust_canary_traffic,
    deploy_candidate_revision,
    get_deployment_strategies_catalog,
    run_canary_deployment,
)


def test_deployment_strategies_catalog():
    catalog = get_deployment_strategies_catalog()
    assert catalog["recommended_strategy"] == "canary_progressive"
    assert "strategies" in catalog
    assert "canary_progressive" in catalog["strategies"]
    assert "blue_green" in catalog["strategies"]
    assert "shadow_traffic" in catalog["strategies"]
    assert catalog["strategies"]["canary_progressive"]["zero_downtime"] is True
    assert catalog["strategies"]["canary_progressive"]["recommended"] is True


def test_deploy_candidate_revision_simulation():
    res = deploy_candidate_revision(
        service_name="sentinel-target-app",
        image_uri="us-central1-docker.pkg.dev/project-sentinel/sentinel/target-app:cand-01",
        candidate_tag="candidate",
        region="us-central1",
        dry_run=True,
    )
    assert res["success"] is True
    assert res["traffic_percent"] == 0
    assert res["tag"] == "candidate"
    assert "tag_url" in res
    assert "https://candidate---" in res["tag_url"]
    assert "sentinel-target-app" in res["revision_name"]


def test_adjust_canary_traffic_stepped_split():
    traffic = adjust_canary_traffic(
        service_name="sentinel-target-app",
        candidate_revision="cand-rev-01",
        candidate_percent=10,
        stable_revision="stable-rev-01",
        dry_run=True,
    )
    assert traffic["success"] is True
    assert traffic["traffic_split"]["cand-rev-01"] == 10
    assert traffic["traffic_split"]["stable-rev-01"] == 90


def test_run_canary_deployment_writes_artifact(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = run_canary_deployment(
        service_name="sentinel-target-app",
        image_uri="us-central1-docker.pkg.dev/project-sentinel/sentinel/target-app:prod",
        release_id="rel-test-001",
        initial_traffic=10,
        dry_run=True,
        emit_to_backend=False,
    )
    assert report["service"] == "sentinel-target-app"
    assert report["initial_traffic_percent"] == 10
    assert report["candidate_revision"] is not None

    artifact_file = tmp_path / "artifacts" / "canary-deploy-report.json"
    assert artifact_file.exists()
    saved = json.loads(artifact_file.read_text(encoding="utf-8"))
    assert saved["release_id"] == "rel-test-001"
