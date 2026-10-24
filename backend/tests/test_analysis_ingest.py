"""
AI analysis from the repair MR is stored as ADVISORY and never moves state.
GitLab is mocked; the real API call is unverified until run against our project.
"""

import json
from pathlib import Path

import pytest
from app.config import settings

from app import analysis_ingest
from tests.helpers import FIX_SHA, drive_to

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[2] / "docs" / "contracts" / "analysis.example.json").read_text(encoding="utf-8")
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture
def gitlab(monkeypatch):
    monkeypatch.setattr(settings, "gitlab_project_id", "12345")
    monkeypatch.setattr(settings, "gitlab_read_token", "read-token-not-real")
    state = {"response": None, "calls": []}

    def fake_get(url, params, headers, timeout):
        state["calls"].append({"url": url, "params": params})
        return state["response"]

    monkeypatch.setattr(analysis_ingest.httpx, "get", fake_get)
    return state


def _mr_open(client, inc_id):
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {
            "iid": 31, "action": "open", "state": "opened",
            "source_branch": f"duo/fix/{inc_id}", "last_commit": {"id": FIX_SHA},
        },
    }
    return client.post("/api/v1/webhooks/gitlab", json=payload,
                       headers={"X-Gitlab-Token": settings.gitlab_webhook_secret})


def test_valid_analysis_is_stored_as_advisory(client, hmac_secret, gitlab):
    inc_id = "inc-analysis-01"
    gitlab["response"] = FakeResponse(200, dict(EXAMPLE, incident_id=inc_id))
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    assert _mr_open(client, inc_id).status_code == 200

    call = gitlab["calls"][-1]
    assert call["params"] == {"ref": FIX_SHA}
    assert "sentinel%2Fincidents%2Finc-analysis-01%2Fanalysis.json" in call["url"]

    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["status"] == "REPAIR_PROPOSED"  # analysis never changes state
    analysis = inc["recovery_attempts"][-1]["analysis"]
    assert analysis["advisory"] is True
    assert len(analysis["facts"]) == len(EXAMPLE["facts"])
    assert EXAMPLE["facts"][0]["evidence_ref"] in analysis["facts"][0]
    types = [e["type"] for e in client.get(f"/api/v1/incidents/{inc_id}/timeline").json()]
    assert "analysis.recorded" in types


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (FakeResponse(404, None), "not found"),
        (FakeResponse(200, ValueError("bad json")), "not valid JSON"),
        (FakeResponse(200, {"incident_id": "x"}), "schema violation"),
    ],
)
def test_bad_analysis_is_rejected_and_recorded(client, hmac_secret, gitlab, response, reason):
    inc_id = "inc-analysis-bad"
    gitlab["response"] = response
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    _mr_open(client, inc_id)
    inc = client.get(f"/api/v1/incidents/{inc_id}").json()
    assert inc["recovery_attempts"][-1]["analysis"] is None
    rejected = [e for e in client.get(f"/api/v1/incidents/{inc_id}/timeline").json()
                if e["type"] == "analysis.rejected"]
    assert rejected and reason in rejected[0]["data"]["reason"]


def test_analysis_for_another_incident_is_rejected(client, hmac_secret, gitlab):
    inc_id = "inc-analysis-wrong"
    gitlab["response"] = FakeResponse(200, dict(EXAMPLE, incident_id="inc-someone-else"))
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    _mr_open(client, inc_id)
    assert client.get(f"/api/v1/incidents/{inc_id}").json()["recovery_attempts"][-1]["analysis"] is None


def test_analysis_with_secret_is_rejected(client, hmac_secret, gitlab):
    inc_id = "inc-analysis-secret"
    doc = dict(EXAMPLE, incident_id=inc_id, missing_evidence=["token glpat-" + "a1B2c3" * 4])
    gitlab["response"] = FakeResponse(200, doc)
    drive_to(client, hmac_secret, inc_id, "INVESTIGATING")
    _mr_open(client, inc_id)
    assert client.get(f"/api/v1/incidents/{inc_id}").json()["recovery_attempts"][-1]["analysis"] is None


def test_example_contract_is_valid():
    assert analysis_ingest.validate_analysis(EXAMPLE["incident_id"], EXAMPLE) is None
