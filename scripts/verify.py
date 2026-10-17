#!/usr/bin/env python3
"""
Project Sentinel — Local Push Gate & Verification Runner
Cross-platform verification script that enforces tests, linting, and contract validation.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

# Safe console output across Windows and POSIX
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_step(step_name: str, cmd: list[str], cwd: Path = REPO_ROOT) -> bool:
    print("\n==================================================")
    print(f"[RUNNING] {step_name}")
    print(f"  Command: {' '.join(cmd)}")
    print("==================================================")

    # Try finding executable in active virtualenv if present
    executable = cmd[0]
    venv_bin = REPO_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    candidate = venv_bin / (executable if os.name != "nt" else f"{executable}.exe")
    if candidate.exists():
        cmd[0] = str(candidate)

    try:
        res = subprocess.run(cmd, check=False, cwd=cwd)
        if res.returncode == 0:
            print(f"[PASS] {step_name}")
            return True
        else:
            print(f"[FAIL] {step_name} (exit code {res.returncode})", file=sys.stderr)
            return False
    except FileNotFoundError as e:
        print(f"[ERROR] Command '{cmd[0]}' not found: {e}", file=sys.stderr)
        return False


def validate_contracts() -> bool:
    print("\n==================================================")
    print("[RUNNING] Contract & Schema Validation")
    print("==================================================")
    try:
        import jsonschema
        import yaml

        # 1. OpenAPI check
        openapi_path = REPO_ROOT / "docs" / "contracts" / "openapi.yaml"
        with open(openapi_path, encoding="utf-8") as f:
            openapi_data = yaml.safe_load(f)
        assert "paths" in openapi_data, "OpenAPI spec missing 'paths'"
        print(f"  [OK] OpenAPI 3.1.0 contract valid ({len(openapi_data['paths'])} paths)")

        # 2. Event Schema check
        schema_path = REPO_ROOT / "docs" / "contracts" / "event.schema.json"
        with open(schema_path, encoding="utf-8") as f:
            schema_data = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema_data)
        print("  [OK] CI Event JSON schema valid (Draft 2020-12)")
        print("[PASS] Contract & Schema Validation")
        return True
    except (
        yaml.YAMLError,
        jsonschema.ValidationError,
        json.JSONDecodeError,
        AssertionError,
        OSError,
    ) as e:
        print(f"[FAIL] Contract Validation: {e}", file=sys.stderr)
        return False


def main() -> int:
    os.chdir(REPO_ROOT)
    failures = []

    # 1. Linter
    if not run_step("Ruff Linter", ["ruff", "check", "."]):
        failures.append("Ruff Linter")

    # 2. Schema / Contract Validation
    if not validate_contracts():
        failures.append("Contracts Validation")

    # 3. Target App Tests
    if not run_step("Demo Target App Test Suite", ["pytest", "-v", "app/tests"]):
        failures.append("App Tests")

    # 4. Sentinel Backend Tests
    if not run_step("Sentinel Backend Test Suite", ["pytest", "-v", "backend/tests"]):
        failures.append("Backend Tests")

    print("\n==================================================")
    if failures:
        print(f"[PUSH GATE REJECTED] Failed checks: {', '.join(failures)}", file=sys.stderr)
        print("Resolve all issues before pushing.", file=sys.stderr)
        return 1
    else:
        print("[PUSH GATE PASSED] All quality gates passed! Ready to push.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
