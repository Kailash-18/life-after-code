"""
Static checks for the Duo investigation + repair flow (.gitlab/duo/flows/sentinel-investigate-repair.yml).
The flow itself runs on GitLab; these tests keep its wiring and its safety boundaries from drifting.
"""
import re
from pathlib import Path

import yaml

FLOW = Path(__file__).resolve().parent.parent / ".gitlab" / "duo" / "flows" / "sentinel-investigate-repair.yml"
# Tools that would let the AI act beyond proposing (merge, run code, change settings).
FORBIDDEN_TOOLS = {"run_command", "run_tests", "merge_merge_request", "update_merge_request", "create_pipeline", "run_git_command"}


def load():
    return yaml.safe_load(FLOW.read_text(encoding="utf-8"))


def test_flow_top_level_shape():
    f = load()
    assert f["version"] == "v1"
    assert f["environment"] == "ambient"
    for banned in ("name", "description", "product_group"):  # rejected for custom flows
        assert banned not in f


def test_routers_and_entry_point_reference_real_components():
    f = load()
    names = {c["name"] for c in f["components"]}
    assert f["flow"]["entry_point"] in names
    for r in f["routers"]:
        assert r["from"] in names
        assert r["to"] in names | {"end", "abort"}


def test_every_component_has_a_prompt_and_its_inputs_are_used():
    f = load()
    prompts = {p["prompt_id"]: p for p in f["prompts"]}
    for c in f["components"]:
        p = prompts[c["prompt_id"]]
        user = p["prompt_template"]["user"]
        for i in c["inputs"]:
            assert "{{ %s }}" % i["as"] in user, f"{c['name']}: input {i['as']} is never used"
        assert "stop" in p["prompt_template"]["system"].lower(), "every agent needs an explicit stop instruction"
        assert p["unit_primitives"] == []


def test_ai_can_only_propose():
    f = load()
    for c in f["components"]:
        assert not FORBIDDEN_TOOLS & set(c.get("toolset", [])), c["name"]
    tools = set().union(*(set(c.get("toolset", [])) for c in f["components"]))
    assert "create_merge_request" in tools  # it proposes through a merge request…
    assert not any("merge_merge_request" in t for t in tools)  # …and never merges


def test_repair_conventions_match_ci():
    text = FLOW.read_text(encoding="utf-8")
    ci = (FLOW.parents[3] / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert "duo/fix/<incident_id>" in text and re.search(r"\^duo\\?/fix\\?/", ci)
    assert "tests/regressions/test_" in text and "tests/regressions/test_" in ci
    assert "evidence-bundle.json" in text and "artifacts/evidence-bundle.json" in ci
