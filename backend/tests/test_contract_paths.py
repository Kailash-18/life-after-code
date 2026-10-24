"""R9: the OpenAPI contract and the running app expose the same API paths."""

from pathlib import Path

import yaml
from app.main import app

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.yaml"


def _normalize(path: str) -> str:
    import re

    return re.sub(r"\{[^}]+\}", "{}", path)


def test_contract_and_app_paths_match():
    spec = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    contract = {(_normalize(p), m.upper()) for p, ops in spec["paths"].items() for m in ops}
    generated = app.openapi()["paths"]
    served = {(_normalize(p), m.upper()) for p, ops in generated.items() for m in ops}
    assert contract == served, {"missing_in_app": contract - served, "missing_in_contract": served - contract}
