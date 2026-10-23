"""
Integration: the team's REAL CI clients against a running backend.

Uses Kailash's sentinel/scripts/emit_event.py (the emitter every CI script calls) and
Samvit's sentinel/scripts/report_gate_verdict.py, with the exact event shapes their
scripts send today: the evaluator, rollback and redeploy jobs send NO incident_id, the
evidence job invents its own id, the Duo flow is started by GitLab (no flow.started), and
the redeploy pipeline runs on the merge commit. The backend must still follow one
incident from detection to RECOVERED without skipping a state.
"""

import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from app.config import settings
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

emit_mod = pytest.importorskip("sentinel.scripts.emit_event")
gate_mod = pytest.importorskip("sentinel.scripts.report_gate_verdict")

BROKEN = "e4f8b91c2d3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c"
FIX = "c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
MERGE = "9a9b9c9d9e9f8a8b8c8d8e8f7a7b7c7d7e7f6a6b"
EVIDENCE_ALIAS = "inc-1792780000"  # evidence_collector's default inc-<timestamp>


@pytest.fixture(scope="module")
def backend_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def emit(backend_url, monkeypatch):
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    counter = iter(range(500_000, 600_000))

    def _emit(event_type, source, pipeline_id, commit_sha, **kw):
        return emit_mod.emit_event(
            event_type, source, pipeline_id=str(pipeline_id), job_id=str(next(counter)),
            commit_sha=commit_sha, backend_url=backend_url, secret=settings.hmac_secret, max_retries=1, **kw,
        )

    return _emit


def _status(client, inc_id):
    return client.get(f"/api/v1/incidents/{inc_id}").json()["status"]


def _mr_webhook(client, action, branch, extra=None):
    attrs = {"iid": 77, "action": action, "state": "opened", "source_branch": branch, "last_commit": {"id": FIX}}
    attrs.update(extra or {})
    r = client.post("/api/v1/webhooks/gitlab", json={"object_kind": "merge_request", "object_attributes": attrs},
                    headers={"X-Gitlab-Token": settings.gitlab_webhook_secret})
    assert r.status_code == 200, r.text
    return r.json()


def test_real_team_pipeline_reaches_recovered(client, emit, monkeypatch):
    # ---- Pipeline 1001 on the faulty commit (main) -------------------------------------
    emit("deploy.canary_started", "sentinel-canary-deploy:automated", 1001, BROKEN,
         data={"revision_name": "target-app-00002", "traffic_percent": 10, "target": "candidate"})
    emit("evaluator.verdict", "sentinel-evaluator:canary-step", 1001, BROKEN,
         data={"verdict": "FAIL", "target": "candidate", "error_rate": 0.257, "p95_ms": 120.0,
               "sample_size": 300, "traffic_percent": 10, "revision_name": "target-app-00002",
               "breached_thresholds": ["error_rate 0.257 > 0.02"]})
    inc = "inc-1001"
    assert _status(client, inc) == "DETECTED"  # opened by the evaluator's measured FAIL

    emit("rollback.started", "sentinel-rollback:automated", 1001, BROKEN,
         data={"revision_name": "target-app-00001", "traffic_percent": 100, "target": "stable"})
    emit("rollback.completed", "sentinel-rollback:automated", 1001, BROKEN,
         artifact_url="https://gitlab.com/sentinel/demo/-/jobs/3/artifacts/rollback-report.json",
         data={"revision_name": "target-app-00001", "traffic_percent": 100,
               "post_rollback_probe_ok": True, "target": "stable"})
    assert _status(client, inc) == "ROLLED_BACK"

    emit("evidence.collected", "sentinel-evidence-collector:automated", 1001, BROKEN,
         incident_id=EVIDENCE_ALIAS,
         artifact_url="https://gitlab.com/sentinel/demo/-/jobs/4/artifacts/evidence-bundle.json",
         data={"evidence_sha256": "ab" * 32, "findings": ["error_rate 0.257 > 0.02"]})
    assert _status(client, inc) == "EVIDENCE_COLLECTED"

    # ---- GitLab starts the Duo flow; it opens the repair MR on the alias id ---------------
    out = _mr_webhook(client, "open", f"duo/fix/{EVIDENCE_ALIAS}")
    assert out["incident_id"] == inc and out["state_machine"]["inferred_investigating"] is True
    assert _status(client, inc) == "REPAIR_PROPOSED"

    # ---- MR pipeline 1002: gates report through report_gate_verdict.build_data -----------
    monkeypatch.setenv("CI_COMMIT_SHA", FIX)
    monkeypatch.setenv("CI_MERGE_REQUEST_IID", "77")
    proof = gate_mod.build_data("regression_proof", {
        "verdict": "PROVEN", "broken_sha": BROKEN, "fix_sha": FIX,
        "broken_run": {"exit_code": 1, "outcome": "failed", "failure_type": "AssertionError", "summary": "log"},
        "fix_run": {"exit_code": 0, "outcome": "passed", "failure_type": "", "summary": "log"},
    })
    emit("regression_proof.verdict", "sentinel/scripts/regression_proof.py", 1002, FIX,
         incident_id=EVIDENCE_ALIAS, data=proof)
    gate = gate_mod.build_data("integrity", {"verdict": "PASS", "findings": []})
    emit("integrity_gate.verdict", "sentinel/scripts/integrity_gate.py", 1002, FIX,
         incident_id=EVIDENCE_ALIAS, data=gate)
    assert _status(client, inc) == "VERIFYING"

    # ---- auto-merge job (no incident id) + the MR merge webhook: same merge twice --------
    emit("merge.completed", "sentinel-auto-merge:automated", 1002, MERGE,
         data={"mr_iid": 77, "fix_sha": FIX, "verdict": "PASS"})
    _mr_webhook(client, "merge", f"duo/fix/{EVIDENCE_ALIAS}", {"state": "merged", "merge_commit_sha": MERGE})
    assert _status(client, inc) == "MERGED"

    # ---- Pipeline 1003 on the MERGE commit: canary redeploy, evaluator steps -------------
    emit("deploy.canary_started", "sentinel-canary-deploy:automated", 1003, MERGE,
         data={"revision_name": "target-app-00003", "traffic_percent": 10, "target": "candidate"})
    assert _status(client, inc) == "REDEPLOYING"
    for pct in (10, 50):
        emit("evaluator.verdict", "sentinel-evaluator:canary-step", 1003, MERGE,
             data={"verdict": "PASS", "target": "candidate", "error_rate": 0.0, "p95_ms": 31.0,
                   "sample_size": 300, "traffic_percent": pct})
        assert _status(client, inc) == "REDEPLOYING"
    emit("evaluator.verdict", "sentinel-evaluator:canary-step", 1003, MERGE,
         data={"verdict": "PASS", "target": "candidate", "error_rate": 0.0, "p95_ms": 30.0,
               "sample_size": 600, "traffic_percent": 100})
    assert _status(client, inc) == "RECOVERED"

    # One incident, every step on the timeline, nothing skipped.
    assert [i["id"] for i in client.get("/api/v1/incidents").json()] == [inc]
    types = [e["type"] for e in client.get(f"/api/v1/incidents/{inc}/timeline").json()]
    for expected in ("evaluator.verdict", "rollback.completed", "evidence.collected", "flow.started",
                     "gitlab.merge_request.open", "regression_proof.verdict", "integrity_gate.verdict",
                     "merge.completed"):
        assert expected in types, (expected, types)
    status = client.get("/api/v1/status").json()
    assert status["current_release"]["commit_sha"] == MERGE and status["active_incident"] is None


def test_evaluator_pass_on_the_broken_commit_cannot_recover(client, emit):
    emit("evaluator.verdict", "sentinel-evaluator:canary-step", 2001, BROKEN,
         data={"verdict": "FAIL", "target": "candidate", "error_rate": 0.3, "p95_ms": 90.0,
               "sample_size": 100, "traffic_percent": 10, "breached_thresholds": ["error_rate"]})
    # ...even if someone later reports a 100 % PASS for the broken SHA, nothing recovers.
    emit("evaluator.verdict", "sentinel-evaluator:canary-step", 2001, BROKEN,
         data={"verdict": "PASS", "target": "candidate", "error_rate": 0.0, "p95_ms": 9.0,
               "sample_size": 100, "traffic_percent": 100})
    assert _status(client, "inc-2001") == "DETECTED"


def test_passing_canary_opens_no_incident(client, emit):
    for pct in (10, 50, 100):
        emit("evaluator.verdict", "sentinel-evaluator:canary-step", 3001, FIX,
             data={"verdict": "PASS", "target": "candidate", "error_rate": 0.0, "p95_ms": 20.0,
                   "sample_size": 100, "traffic_percent": pct})
    assert client.get("/api/v1/incidents").json() == []


def test_unauthoritative_fail_does_not_open_incident(client, emit):
    emit("evaluator.verdict", "gitlab/duo/agent", 4001, BROKEN,
         data={"verdict": "FAIL", "target": "candidate", "breached_thresholds": ["made up"]})
    assert client.get("/api/v1/incidents").json() == []


def test_informational_events_join_the_incident_timeline(client, emit):
    emit("evaluator.verdict", "sentinel-evaluator:canary-step", 6001, BROKEN,
         data={"verdict": "FAIL", "target": "candidate", "error_rate": 0.2, "p95_ms": 50.0,
               "sample_size": 100, "traffic_percent": 10, "breached_thresholds": ["error_rate"]})
    emit("rollback.started", "sentinel-rollback:automated", 6001, BROKEN,
         data={"revision_name": "r1", "traffic_percent": 100, "target": "stable"})
    types = [e["type"] for e in client.get("/api/v1/incidents/inc-6001/timeline").json()]
    assert types == ["evaluator.verdict", "rollback.started"]
    assert _status(client, "inc-6001") == "DETECTED"
