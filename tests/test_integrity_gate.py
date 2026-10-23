"""
Tests for Sentinel Deterministic Integrity Gate
Verifies that all 9 test-weakening / cheating fixtures are blocked,
the clean fix fixture passes cleanly, and JUnit XML generation maps
findings (including harness escape variants) accurately.
"""

import subprocess
import sys
import xml.etree.ElementTree as ET
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


def test_integrity_gate_junit_xml_attribution(tmp_path):
    """
    Verifies that the generated JUnit XML correctly attributes harness-escape findings
    (RULE_07_HARNESS_ESCAPE_EXIT and RULE_07_HARNESS_ESCAPE_ENV_CHECK) to the
    'rule_07_no_harness_escapes' testcase.
    """
    patch_path = FIXTURES_DIR / "07_harness_escape_exit.patch"
    junit_out = tmp_path / "junit_report.xml"

    proc = subprocess.run(
        [
            sys.executable,
            str(GATE_SCRIPT),
            "--diff-file",
            str(patch_path),
            "--output-junit",
            str(junit_out),
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    assert junit_out.exists()

    tree = ET.parse(junit_out)
    root = tree.getroot()
    assert root.tag == "testsuite"
    assert root.attrib["name"] == "sentinel.integrity_gate"

    # Find the specific testcase for harness escape
    harness_tc = None
    for tc in root.findall("testcase"):
        if tc.attrib.get("name") == "rule_07_no_harness_escapes":
            harness_tc = tc
            break

    assert harness_tc is not None, "Missing rule_07_no_harness_escapes testcase in JUnit XML"
    failure_el = harness_tc.find("failure")
    assert failure_el is not None, "rule_07_no_harness_escapes testcase should be marked as failure"
    assert "process termination" in failure_el.attrib.get("message", "").lower() or "harness escape" in failure_el.attrib.get("message", "").lower()


def test_integrity_gate_detects_multiple_violations(tmp_path):
    """Verifies that multiple findings across different rules in a single patch are all detected."""
    multi_patch = tmp_path / "multi_cheat.patch"
    multi_patch.write_text(
        """diff --git a/.gitlab-ci.yml b/.gitlab-ci.yml
--- a/.gitlab-ci.yml
+++ b/.gitlab-ci.yml
@@ -1,2 +1,3 @@
 test:
+  script: exit 0
diff --git a/app/core.py b/app/core.py
--- a/app/core.py
+++ b/app/core.py
@@ -1,2 +1,4 @@
+def __eq__(self, other):
+    return True
""",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--diff-file", str(multi_patch)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    assert "RULE_05_PROTECTED_CONFIG_MODIFIED" in proc.stdout
    assert "RULE_09_EQ_OVERRIDDEN_TRUE" in proc.stdout


def test_integrity_gate_covers_nested_test_directories():
    """A repair that edits app/tests/... (not only the top-level tests/) must be blocked too."""
    patch_path = FIXTURES_DIR / "11_weakens_nested_app_test.patch"
    proc = subprocess.run([sys.executable, str(GATE_SCRIPT), "--diff-file", str(patch_path)], capture_output=True, text=True)
    assert proc.returncode == 1, proc.stdout
    assert "RULE_01_EXISTING_TESTS_MODIFIED" in proc.stdout
    assert "RULE_04_ASSERT_WEAKENED" in proc.stdout
