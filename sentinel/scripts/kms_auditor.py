#!/usr/bin/env python3
"""
Sentinel Multi-Cloud KMS Auditor Entrypoint Alias
Proxies to sentinel.scripts.kms_rotation_auditor for CLI compatibility.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentinel.scripts.kms_rotation_auditor import CloudKmsRotationAuditor, main, run_kms_audit

if __name__ == "__main__":
    main()
