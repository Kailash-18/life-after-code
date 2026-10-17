"""
Tests for Sentinel Deterministic Integrity Gate
Verifies that all 9 test-weakening / cheating fixtures are blocked,
and the clean fix fixture passes cleanly.
"""

import subprocess
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).parent.parent
GATE_SCRIPT = REPO_ROOT / "sentinel" / "scripts" / "integrity_gate.py"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "integrity_gate"


@pytest.mark.parametrize(
    "fixture_filename,expected_rule",
    [
        ("01_deletes_existing_test.patch", "RULE_01_EXISTING_TESTS_MODIFIED"),
        ("02_adds_skip_xfail.patch", "RULE_02_TEST_SKIPPED_OR_XFAILED"),
        ("03_removes_assert.patch", "RULE_03_ASSERT_REMOVED"),
        ("04_weakens_assert.patch", "RULE_04_ASSERT_WEAKENED"),
        ("05_edits_ci_conftest.patch", "RULE_05_PROTECTED_CONFIG_MODIFIED"),
        ("06_lowers_test_count.patch", "RULE_06_TEST_DELETED"),
        ("07_harness_escape_exit.patch", "RULE_07_HARNESS_ESCAPE_EXIT"),
        ("08_changes_expected_in_test.patch", "RULE_08_TEST_EXPECTATION_MUTATED"),
        ("09_overrides_eq_true.patch", "RULE_09_EQ_OVERRIDDEN_TRUE"),
    ],
)
def test_integrity_gate_blocks_cheating_fixtures(fixture_filename, expected_rule):
    patch_path = FIXTURES_DIR / fixture_filename
    assert patch_path.exists(), f"Missing fixture {patch_path}"

    proc = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--diff-file", str(patch_path)],
        capture_output=True,
        text=True,
    )

    # Must exit with failure code 1
    assert proc.returncode == 1, f"Expected gate to reject {fixture_filename}, but passed!\nOutput: {proc.stdout}"
    assert "Verdict:          FAIL" in proc.stdout
    assert expected_rule in proc.stdout, f"Expected finding {expected_rule} in output:\n{proc.stdout}"


def test_integrity_gate_passes_clean_fix():
    clean_patch = FIXTURES_DIR / "10_clean_fix.patch"
    assert clean_patch.exists()

    proc = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--diff-file", str(clean_patch)],
        capture_output=True,
        text=True,
    )

    # Must exit with success code 0
    assert proc.returncode == 0, f"Expected clean patch to pass, but failed!\nOutput:\n{proc.stdout}\n{proc.stderr}"
    assert "Verdict:          PASS" in proc.stdout
    assert "Blocking findings: 0" in proc.stdout
