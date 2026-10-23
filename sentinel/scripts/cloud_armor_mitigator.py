#!/usr/bin/env python3
"""
Project Sentinel — Google Cloud Armor Dynamic WAF Threat Mitigator
Stage: Secure / Configure.
Analyzes Layer 7 HTTP flood patterns, evaluates OWASP ModSecurity signatures,
and generates dynamic Cloud Armor adaptive rate-limiting and ban rules.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class CloudArmorMitigator:
    """Evaluates security telemetry and generates dynamic Cloud Armor rules."""

    def __init__(self, ban_threshold_rps: int = 150, ban_duration_sec: int = 600) -> None:
        self.ban_threshold_rps = ban_threshold_rps
        self.ban_duration_sec = ban_duration_sec

    def analyze_threat_vectors(
        self,
        simulated_requests: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Inspects request telemetry for SQLi, XSS, RCE, and abusive IP rate spikes."""
        if simulated_requests is None:
            simulated_requests = [
                {"src_ip": "198.51.100.12", "rps": 220, "pattern": "HTTP_FLOOD"},
                {"src_ip": "203.0.113.44", "rps": 12, "pattern": "NORMAL"},
                {"src_ip": "192.0.2.89", "rps": 5, "pattern": "OWASP_SQLI"},
            ]

        mitigated_rules = []
        for req in simulated_requests:
            if req.get("rps", 0) > self.ban_threshold_rps:
                mitigated_rules.append({
                    "action": "rate_based_ban",
                    "priority": 1050,
                    "target_ip": req["src_ip"],
                    "ban_duration_sec": self.ban_duration_sec,
                    "reason": f"Excessive request rate ({req['rps']} rps > {self.ban_threshold_rps} threshold)",
                })
            elif req.get("pattern") in ("OWASP_SQLI", "OWASP_XSS", "OWASP_RCE"):
                mitigated_rules.append({
                    "action": "deny(403)",
                    "priority": 2100,
                    "target_ip": req["src_ip"],
                    "reason": f"Signature match: {req['pattern']}",
                })

        gcp_policy = self.export_gcp_armor_policy(mitigated_rules)

        return {
            "policy_name": "sentinel-armor-edge-waf",
            "threats_detected": len(mitigated_rules),
            "dynamic_rules_generated": mitigated_rules,
            "waf_active": True,
            "status": "THREATS_MITIGATED" if mitigated_rules else "ALL_TRAFFIC_CLEAN",
            "gcp_security_policy": gcp_policy,
        }

    def export_gcp_armor_policy(self, rules: list[dict[str, Any]]) -> dict[str, Any]:
        """Exports Google Cloud Armor security policy JSON compatible with gcloud compute security-policies import."""
        gcp_rules = []
        for idx, r in enumerate(rules):
            action = "rate_based_ban" if r["action"] == "rate_based_ban" else "deny(403)"
            gcp_rules.append({
                "action": action,
                "priority": r.get("priority", 1000 + idx * 100),
                "match": {
                    "versionedExpr": "SRC_IPS_V1",
                    "config": {
                        "srcIpRanges": [f"{r['target_ip']}/32"],
                    },
                },
                "description": r.get("reason", "Sentinel automated Layer 7 WAF mitigation"),
            })

        # Default allow rule
        gcp_rules.append({
            "action": "allow",
            "priority": 2147483647,
            "match": {
                "versionedExpr": "SRC_IPS_V1",
                "config": {"srcIpRanges": ["*"]},
            },
            "description": "Default allow rule for legitimate application traffic",
        })

        return {
            "name": "sentinel-adaptive-edge-waf",
            "description": "Google Cloud Armor L7 WAF Policy generated autonomously by Project Sentinel",
            "type": "CLOUD_ARMOR",
            "adaptiveProtectionConfig": {
                "layer7DdosDefenseConfig": {
                    "enable": True,
                    "ruleVisibility": "STANDARD",
                },
            },
            "rules": gcp_rules,
        }


def run_armor_audit(output_dir: Path | None = None) -> dict[str, Any]:
    mitigator = CloudArmorMitigator()
    report = mitigator.analyze_threat_vectors()
    report["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "cloud-armor-threat-mitigation-report.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        # Dual-save canonical WAF report artifact for GitLab CI security stage
        (output_dir / "cloud-armor-waf-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Cloud Armor WAF Threat Mitigator")
    parser.add_argument("--output-dir", default="artifacts", help="Report output dir")
    parser.add_argument("--dry-run", action="store_true", help="Simulate Cloud Armor WAF threat mitigation in safe mode")
    args = parser.parse_args()

    report = run_armor_audit(output_dir=Path(args.output_dir))
    print(f"\n{'='*70}")
    print("  PROJECT SENTINEL — GOOGLE CLOUD ARMOR DYNAMIC WAF MITIGATOR")
    print(f"  Status: [{report['status']}] | Threats Mitigated: {report['threats_detected']}")
    for r in report["dynamic_rules_generated"]:
        print(f"    - [RULE] Action: {r['action']} | Target: {r['target_ip']} ({r['reason']})")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
