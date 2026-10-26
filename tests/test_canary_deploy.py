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


# --- real (non-simulated) path: never record a deploy gcloud did not confirm -------------

import os
import sys
import textwrap

from sentinel.scripts import canary_deploy as cd


def _fake_gcloud(tmp_path: Path, monkeypatch, describe_ok: bool = True, deploy_ok: bool = True):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "calls.log"
    service = {"status": {"url": "https://svc.run.app",
                          "traffic": [{"tag": "candidate", "url": "https://candidate---svc.run.app"}]}}
    (tmp_path / "service.json").write_text(json.dumps(service))
    script = bindir / "gcloud"
    script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        echo "$@" >> "{log}"
        case "$*" in
          *"services describe"*) {"cat " + str(tmp_path / "service.json") if describe_ok else "exit 1"} ;;
          *"run deploy"*) {"echo '{{}}'" if deploy_ok else "echo 'permission denied' >&2; exit 1"} ;;
          *) echo '{{}}' ;;
        esac
        """))
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return log


pytestmark_posix = pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX shell stand-in for gcloud")


def test_missing_gcloud_is_a_failure_and_emits_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))  # no gcloud anywhere
    sent = []
    monkeypatch.setattr(cd, "emit_event", lambda **kw: sent.append(kw))
    report = cd.run_canary_deployment("svc", "img:1", "rel-x", initial_traffic=10, commit_sha="a" * 40)
    assert report["success"] is False
    assert sent == []


@pytestmark_posix
def test_failed_deploy_is_a_failure_and_emits_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _fake_gcloud(tmp_path, monkeypatch, deploy_ok=False)
    sent = []
    monkeypatch.setattr(cd, "emit_event", lambda **kw: sent.append(kw))
    report = cd.run_canary_deployment("svc", "img:1", "rel-x", initial_traffic=10, commit_sha="a" * 40)
    assert report["success"] is False and sent == []


@pytestmark_posix
def test_confirmed_deploy_records_real_revision_and_traffic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log = _fake_gcloud(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(cd, "emit_event", lambda **kw: sent.append(kw))
    report = cd.run_canary_deployment("svc", "img:1", "rel-x", initial_traffic=10, commit_sha="abcdef1234" + "0" * 30)
    assert report["success"] is True
    assert report["candidate_revision"].startswith("svc-cabcdef1-")
    assert report["candidate_tag_url"] == "https://candidate---svc.run.app"
    assert report["traffic_percent"] == 10
    calls = log.read_text()
    assert "--no-traffic" in calls and "--to-tags=candidate=10" in calls
    assert sent and sent[0]["data"]["traffic_percent"] == 10
    env = (tmp_path / "artifacts" / "deploy.env").read_text()
    assert "CANDIDATE_URL=https://candidate---svc.run.app" in env and "STABLE_URL=https://svc.run.app" in env
