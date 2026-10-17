#!/usr/bin/env python3
"""
Install repository Git hooks for Project Sentinel.
Installs .git/hooks/pre-push to prevent pushing failing code.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_HOOKS_DIR = REPO_ROOT / ".git" / "hooks"
PRE_PUSH_DEST = GIT_HOOKS_DIR / "pre-push"

HOOK_CONTENT = """#!/usr/bin/env bash
# Git pre-push hook for Project Sentinel
# Enforces tests, linting, and contract validation before pushing.

echo "[Sentinel Push Gate] Running verification suite..."

if [ -f "./.venv/bin/python" ]; then
    PYTHON="./.venv/bin/python"
elif [ -f "./.venv/Scripts/python.exe" ]; then
    PYTHON="./.venv/Scripts/python.exe"
else
    PYTHON="python"
fi

"$PYTHON" scripts/verify.py
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[Sentinel Push Gate] PUSH BLOCKED! Verification checks failed."
    echo "Fix failing checks or run 'python scripts/verify.py' locally."
    exit 1
fi

exit 0
"""


def install_hooks() -> int:
    if not GIT_HOOKS_DIR.exists():
        print(
            f"Error: {GIT_HOOKS_DIR} does not exist. Is this a Git repository?",
            file=sys.stderr,
        )
        return 1

    PRE_PUSH_DEST.write_text(HOOK_CONTENT, encoding="utf-8")
    try:
        # Make executable on Unix
        import os

        os.chmod(PRE_PUSH_DEST, 0o755)
    except OSError:
        pass

    print(f"[OK] Successfully installed Git pre-push hook to {PRE_PUSH_DEST}")
    print("NOTE: Git hooks run locally and prevent accidental pushes of broken code.")
    print(
        "NOTE: Because local hooks can be bypassed (e.g. via --no-verify), GitLab CI serves as the authoritative remote gate."
    )
    return 0


if __name__ == "__main__":
    sys.exit(install_hooks())
