#!/usr/bin/env python3
"""
Sentinel CycloneDX VEX Entrypoint Alias
Proxies to sentinel.scripts.vex_attestor for CLI compatibility.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentinel.scripts.vex_attestor import CycloneDxVexAttestor, main, run_vex_audit

if __name__ == "__main__":
    main()
