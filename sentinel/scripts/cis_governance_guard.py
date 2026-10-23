#!/usr/bin/env python3
"""
Sentinel CIS Multi-Cloud Governance Guard Entrypoint Alias
Proxies to sentinel.scripts.governance_guard for CLI compatibility.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentinel.scripts.governance_guard import MultiCloudGovernanceGuard, main, run_governance_audit

if __name__ == "__main__":
    main()
