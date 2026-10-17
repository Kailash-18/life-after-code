#!/usr/bin/env python3
"""
Install repository Git hooks for Project Sentinel.
Installs .git/hooks/pre-push with LF line endings to prevent pushing failing code.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_HOOKS_DIR = REPO_ROOT / ".git" / "hooks"
PRE_PUSH_DEST = GIT_HOOKS_DIR / "pre-push"

# Must use strict LF (\n) line endings so Git Bash on Windows does not fail on \r
HOOK_CONTENT = (
    "#!/usr/bin/env bash\n"
    "# Git pre-push hook for Project Sentinel\n"
    "# Enforces tests, linting, and contract validation before pushing.\n\n"
    'echo "[Sentinel Push Gate] Running verification suite..."\n\n'
    'if [ -f "./.venv/bin/python" ]; then\n'
    '    PYTHON="./.venv/bin/python"\n'
    'elif [ -f "./.venv/Scripts/python.exe" ]; then\n'
    '    PYTHON="./.venv/Scripts/python.exe"\n'
    "else\n"
    '    PYTHON="python"\n'
    "fi\n\n"
    '"$PYTHON" scripts/verify.py\n'
    "EXIT_CODE=$?\n\n"
    "if [ $EXIT_CODE -ne 0 ]; then\n"
    '    echo ""\n'
    '    echo "[Sentinel Push Gate] PUSH BLOCKED! Verification checks failed."\n'
    '    echo "Fix failing checks or run \'python scripts/verify.py\' locally."\n'
    "    exit 1\n"
    "fi\n\n"
    "exit 0\n"
)


def install_hooks() -> int:
    if not GIT_HOOKS_DIR.exists():
        print(
            f"Error: {GIT_HOOKS_DIR} does not exist. Is this a Git repository?",
            file=sys.stderr,
        )
        return 1

    # Write in binary mode with strict LF endings
    with open(PRE_PUSH_DEST, "wb") as f:
        f.write(HOOK_CONTENT.encode("utf-8"))

    try:
        # Make executable on Unix
        os.chmod(PRE_PUSH_DEST, 0o755)
    except OSError:
        pass

    print(f"[OK] Successfully installed Git pre-push hook (LF endings) to {PRE_PUSH_DEST}")
    print("NOTE: Git hooks run locally and prevent accidental pushes of broken code.")
    print("NOTE: Because local hooks can be bypassed (e.g. via --no-verify), GitLab CI serves as the authoritative remote gate.")
    return 0


if __name__ == "__main__":
    sys.exit(install_hooks())
