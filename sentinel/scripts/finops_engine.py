#!/usr/bin/env python3
"""
Sentinel FinOps Engine Entrypoint Alias
Proxies to sentinel.scripts.finops_guard for CLI compatibility.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentinel.scripts.finops_guard import CloudFinOpsGuard, evaluate_cloud_finops_guard, main

if __name__ == "__main__":
    main()
