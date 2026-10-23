"""
backend/scripts/emit_event.py against a real uvicorn server (no mocks of the backend).
"""

import importlib.util
import json
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from app.config import settings
from app.main import app

from tests.helpers import BROKEN_SHA, FIX_SHA, drive_to

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "emit_event.py"
spec = importlib.util.spec_from_file_location("emit_event", SCRIPT)
emit_event = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emit_event)


@pytest.fixture(scope="module")
def server_url():
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
def env(server_url, monkeypatch):
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    counter = iter(range(800_000, 900_000))
    base = {
        "SENTINEL_API_URL": server_url,
        "SENTINEL_HMAC_SECRET": settings.hmac_secret,
        "CI_PIPELINE_ID": "77",
        "CI_COMMIT_SHA": BROKEN_SHA,
        "CI_JOB_NAME": "evaluate:canary",
    }

    def make():
        return dict(base, CI_JOB_ID=str(next(counter)))

    return make


def run(env, *argv):
    return emit_event.main(list(argv), env=env)


def test_accepted_event_exits_zero(env, client, capsys):
    rc = run(env(), "--type", "incident.detected", "--incident-id", "inc-cli-01",
             "--source", "sentinel/scripts/evaluator.py",
             "--data", '{"breached_thresholds": ["error_rate 0.26 > 0.02"]}')
    assert rc == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["incident_status"] == "DETECTED"
    assert settings.hmac_secret not in out.out + out.err
    assert client.get("/api/v1/incidents/inc-cli-01").json()["status"] == "DETECTED"


def test_rejected_event_fails_the_job(env, client):
    run(env(), "--type", "incident.detected", "--incident-id", "inc-cli-02",
        "--data", '{"breached_thresholds": ["x"]}')
    rc = run(env(), "--type", "recovery.verified", "--incident-id", "inc-cli-02",
             "--source", "sentinel/scripts/evaluator.py", "--data", '{"verdict": "PASS"}')
    assert rc == emit_event.EXIT_REJECTED


def test_warn_only_never_fails(env, client):
    rc = run(env(), "--warn-only", "--type", "recovery.verified", "--incident-id", "inc-cli-none",
             "--attempts", "1", "--data", '{"verdict": "PASS"}')
    assert rc == 0


def test_retryable_out_of_order_event_is_retried(env, client, monkeypatch):
    """rollback.completed arrives before incident.detected; the client retries and succeeds."""
    detect_env = env()

    def fake_sleep(_seconds):
        # While the client waits, the detection event lands.
        assert run(detect_env, "--type", "incident.detected", "--incident-id", "inc-cli-03",
                   "--data", '{"breached_thresholds": ["p95 > 300ms"]}') == 0

    real_emit = emit_event.emit
    monkeypatch.setattr(emit_event, "emit",
                        lambda api, secret, event, attempts: real_emit(api, secret, event, attempts, 0.0, fake_sleep))
    rc = run(env(), "--type", "rollback.completed", "--incident-id", "inc-cli-03",
             "--data", '{"post_rollback_probe_ok": true}')
    assert rc == 0
    assert client.get("/api/v1/incidents/inc-cli-03").json()["status"] == "ROLLED_BACK"


def test_unreachable_backend_exhausts_retries(env, monkeypatch):
    e = env()
    e["SENTINEL_API_URL"] = "http://127.0.0.1:9"
    real_emit = emit_event.emit
    monkeypatch.setattr(emit_event, "emit",
                        lambda api, secret, event, attempts: real_emit(api, secret, event, attempts, 0.0, lambda s: None))
    assert run(e, "--type", "pipeline.started", "--attempts", "2") == emit_event.EXIT_EXHAUSTED


def test_missing_configuration_is_usage_error(env):
    e = env()
    del e["SENTINEL_HMAC_SECRET"]
    assert run(e, "--type", "pipeline.started") == emit_event.EXIT_USAGE
    assert run({}, "--type", "pipeline.started") == emit_event.EXIT_USAGE


def test_regression_proof_report_drives_verifying(env, client, hmac_secret, tmp_path):
    inc = "inc-cli-proof"
    drive_to(client, hmac_secret, inc, "REPAIR_PROPOSED")
    report = {  # shape written by sentinel/scripts/regression_proof.py --output-json
        "verdict": "PROVEN", "test_file": "tests/regressions/test_inc.py",
        "broken_sha": BROKEN_SHA, "fix_sha": FIX_SHA,
        "broken_run": {"exit_code": 1, "outcome": "failed", "failure_type": "AssertionError",
                       "summary": "very long pytest log ..."},
        "fix_run": {"exit_code": 0, "outcome": "passed", "failure_type": "", "summary": "1 passed"},
        "rejection_reason": None,
    }
    path = tmp_path / "proof.json"
    path.write_text(json.dumps(report))
    e = env()
    e["CI_COMMIT_SHA"] = FIX_SHA
    assert run(e, "--type", "regression_proof.verdict", "--incident-id", inc,
               "--from-regression-proof", str(path)) == 0
    att = client.get(f"/api/v1/incidents/{inc}").json()["recovery_attempts"][-1]
    assert {(t["kind"], t["outcome"]) for t in att["test_results"]} == {
        ("regression_on_broken", "FAILED"), ("regression_on_fix", "PASSED")}


def test_rejected_regression_proof_report_fails_verification(env, client, hmac_secret, tmp_path):
    inc = "inc-cli-vacuous"
    drive_to(client, hmac_secret, inc, "REPAIR_PROPOSED")
    report = {"verdict": "REJECTED", "broken_sha": BROKEN_SHA, "fix_sha": FIX_SHA,
              "broken_run": {"exit_code": 0, "outcome": "passed", "failure_type": ""},
              "fix_run": {}, "rejection_reason": "Test did NOT fail on the broken revision (vacuous test)."}
    path = tmp_path / "proof.json"
    path.write_text(json.dumps(report))
    assert run(env(), "--type", "regression_proof.verdict", "--incident-id", inc,
               "--from-regression-proof", str(path)) == 0
    inc_body = client.get(f"/api/v1/incidents/{inc}").json()
    assert inc_body["status"] == "VERIFICATION_FAILED"
    assert "vacuous" in inc_body["recovery_attempts"][-1]["failure_reason"]


def test_integrity_gate_report_fail_blocks(env, client, hmac_secret, tmp_path):
    inc = "inc-cli-gate"
    drive_to(client, hmac_secret, inc, "REPAIR_PROPOSED")
    report = {"gate": "integrity", "verdict": "FAIL", "findings": [
        {"rule_id": "IG-SKIP", "severity": "BLOCKING", "file": "tests/test_orders.py",
         "message": "added pytest.mark.skip", "details": None}]}
    path = tmp_path / "ig.json"
    path.write_text(json.dumps(report))
    assert run(env(), "--type", "integrity_gate.verdict", "--incident-id", inc,
               "--from-integrity-gate", str(path)) == 0
    body = client.get(f"/api/v1/incidents/{inc}").json()
    assert body["status"] == "VERIFICATION_FAILED"
    assert "IG-SKIP" in body["recovery_attempts"][-1]["gate_results"][-1]["findings"][0]


def test_dry_run_prints_without_sending(env, capsys):
    e = env()
    del e["SENTINEL_API_URL"]
    assert run(e, "--dry-run", "--type", "pipeline.started", "--data", '{"version": "1.0.1"}') == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["data"] == {"version": "1.0.1"} and printed["job_id"] == e["CI_JOB_ID"]
