"""
Tests for Sentinel Regression Proof Gate
Verifies that:
1. Rejects tests failing by syntax error, import error, or collection error.
2. Rejects vacuous tests that pass on broken commits.
3. Rejects tests failing with non-assertion runtime errors.
4. Accepts genuine failure->pass transitions with AssertionError.
5. Safely handles missing files, invalid revisions, and infrastructure failures.
"""

import json
import subprocess
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROOF_SCRIPT = REPO_ROOT / "sentinel" / "scripts" / "regression_proof.py"


def test_regression_proof_missing_test_file():
    proc = subprocess.run(
        [
            sys.executable,
            str(PROOF_SCRIPT),
            "--broken",
            "HEAD",
            "--fix",
            "HEAD",
            "--test",
            "nonexistent_file_xyz.py",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "not found" in proc.stderr.lower()


def test_regression_proof_invalid_commit_rejection(tmp_path):
    dummy_test = tmp_path / "test_dummy.py"
    dummy_test.write_text("def test_foo(): assert True\n", encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(PROOF_SCRIPT),
            "--broken",
            "nonexistent_sha_0000000000000",
            "--fix",
            "HEAD",
            "--test",
            str(dummy_test),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "REJECTED" in proc.stdout
    assert "Failed to execute test on broken commit" in proc.stdout


def test_extract_failure_type_distinguishes_assertion_from_others():
    from sentinel.scripts.regression_proof import extract_failure_type

    # 1. Plain text with 'assert' word in log should NOT be AssertionError unless it's a pytest failure line
    random_log = "2026-10-18 INFO: We need to assert our dominance in cloud market\nAll tests passed"
    assert extract_failure_type(random_log) == "UnknownError"

    # 2. Genuine pytest assertion line
    pytest_assert = "    def test_example():\n>       assert 1 == 2\nE       assert 1 == 2\nE       AssertionError"
    assert extract_failure_type(pytest_assert) == "AssertionError"

    # 3. Syntax error
    syntax_err = "E   SyntaxError: invalid syntax"
    assert extract_failure_type(syntax_err) == "SyntaxError"

    # 4. Collection error
    col_err = "==================== ERRORS ====================\n___ ERROR collecting test_foo.py ___\nImportError: No module named 'bar'"
    assert extract_failure_type(col_err) in ("ImportError", "CollectionError")
