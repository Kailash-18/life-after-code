from pathlib import Path
import tempfile
import pytest
from sentinel.scripts.sast_gate import scan_file

def test_sast_detects_eval_and_hardcoded_token():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("x = eval('2 + 2')\n")
        f.write("gl_token = 'glpat-12345678901234567890'\n")
        temp_path = Path(f.name)

    try:
        findings = scan_file(temp_path)
        assert len(findings) >= 2
        rule_ids = [find["rule_id"] for find in findings]
        assert "SEC-EVAL" in rule_ids
        assert "SEC-HARDCODED-SECRET" in rule_ids
    finally:
        temp_path.unlink()
