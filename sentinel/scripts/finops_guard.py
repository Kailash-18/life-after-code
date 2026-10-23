#!/usr/bin/env python3
"""
Project Sentinel — Cloud FinOps & Carbon Intensity Guard (Task K-FinOps)
Enterprise multi-cloud cost forecasting, FinOps budget policy enforcement,
and carbon intensity (GreenOps) scoring across Google Cloud Run and AWS S3 State Planes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentinel.scripts.emit_event import emit_event

# ------------------------------------------------------------------------------
# MULTI-CLOUD PRICING CATALOG (GCP Tier 1 & AWS us-east-1)
# ------------------------------------------------------------------------------
GCP_PRICING = {
    "cloud_run": {
        "vcpu_second_usd": 0.00002400,
        "gib_second_usd": 0.00000250,
        "requests_per_million_usd": 0.40,
        "free_tier_requests": 2_000_000,
        "free_tier_vcpu_seconds": 180_000,
        "free_tier_gib_seconds": 360_000,
    },
    "cloud_armor": {
        "policy_base_monthly_usd": 5.00,
        "requests_per_million_usd": 0.75,
    },
}

AWS_PRICING = {
    "s3_state": {
        "standard_gb_monthly_usd": 0.023,
        "standard_ia_gb_monthly_usd": 0.0125,
        "put_copy_per_1000_usd": 0.005,
        "kms_requests_per_10k_usd": 0.03,
    },
    "dynamodb_locks": {
        "pitr_and_storage_monthly_usd": 1.25,
        "lock_transitions_per_million_usd": 0.25,
    },
}

# Regional average grid emission factors (gCO2eq / kWh)
REGIONAL_CARBON_INTENSITY = {
    "us-central1": {"gco2_per_kwh": 380.0, "carbon_free_energy_pct": 64.0},
    "us-east1": {"gco2_per_kwh": 340.0, "carbon_free_energy_pct": 58.0},
    "europe-west1": {"gco2_per_kwh": 115.0, "carbon_free_energy_pct": 92.0},
}


class CloudFinOpsGuard:
    """Evaluates multi-cloud operational expenditure and environmental carbon footprint."""

    def __init__(
        self,
        policy_path: Path | None = None,
        monthly_budget_usd: float = 250.0,
        max_cost_increase_pct: float = 25.0,
        max_carbon_intensity_gco2: float = 450.0,
    ) -> None:
        self.monthly_budget_usd = monthly_budget_usd
        self.max_cost_increase_pct = max_cost_increase_pct
        self.max_carbon_intensity_gco2 = max_carbon_intensity_gco2

        # Override defaults with sentinel/policy.yaml if present
        if policy_path and policy_path.exists():
            try:
                cfg = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
                finops_cfg = cfg.get("finops_budget", {})
                if "monthly_budget_usd" in finops_cfg:
                    self.monthly_budget_usd = float(finops_cfg["monthly_budget_usd"])
                if "max_cost_increase_pct" in finops_cfg:
                    self.max_cost_increase_pct = float(finops_cfg["max_cost_increase_pct"])
                if "max_carbon_intensity_gco2" in finops_cfg:
                    self.max_carbon_intensity_gco2 = float(finops_cfg["max_carbon_intensity_gco2"])
            except Exception:
                pass

    def estimate_cloud_run_cost(
        self,
        monthly_requests: int = 5_000_000,
        avg_duration_ms: float = 65.0,
        vcpu: float = 1.0,
        memory_gib: float = 0.5,
    ) -> dict[str, float]:
        """Calculates projected Google Cloud Run serverless compute spend."""
        pricing = GCP_PRICING["cloud_run"]

        billable_requests = max(0, monthly_requests - pricing["free_tier_requests"])
        request_cost = (billable_requests / 1_000_000) * pricing["requests_per_million_usd"]

        total_active_seconds = monthly_requests * (avg_duration_ms / 1000.0)
        total_vcpu_seconds = total_active_seconds * vcpu
        total_gib_seconds = total_active_seconds * memory_gib

        billable_vcpu_sec = max(0.0, total_vcpu_seconds - pricing["free_tier_vcpu_seconds"])
        billable_gib_sec = max(0.0, total_gib_seconds - pricing["free_tier_gib_seconds"])

        vcpu_cost = billable_vcpu_sec * pricing["vcpu_second_usd"]
        memory_cost = billable_gib_sec * pricing["gib_second_usd"]

        total_cloud_run = round(request_cost + vcpu_cost + memory_cost, 2)
        return {
            "request_cost_usd": round(request_cost, 2),
            "vcpu_cost_usd": round(vcpu_cost, 2),
            "memory_cost_usd": round(memory_cost, 2),
            "total_cloud_run_usd": total_cloud_run,
        }

    def estimate_storage_and_security_cost(
        self,
        monthly_requests: int = 5_000_000,
        state_snapshots_stored_gb: float = 15.0,
        monthly_state_mutations: int = 25_000,
    ) -> dict[str, float]:
        """Calculates Cloud Armor WAF and AWS S3 + DynamoDB remote state storage spend."""
        # Cloud Armor
        armor_pricing = GCP_PRICING["cloud_armor"]
        armor_req_cost = (monthly_requests / 1_000_000) * armor_pricing["requests_per_million_usd"]
        armor_total = armor_pricing["policy_base_monthly_usd"] + armor_req_cost

        # AWS S3 Remote State
        s3_pricing = AWS_PRICING["s3_state"]
        # 30% stored in Standard, 70% in Standard-IA cold lifecycle tier
        standard_storage = (state_snapshots_stored_gb * 0.3) * s3_pricing["standard_gb_monthly_usd"]
        ia_storage = (state_snapshots_stored_gb * 0.7) * s3_pricing["standard_ia_gb_monthly_usd"]
        s3_mutations = (monthly_state_mutations / 1_000) * s3_pricing["put_copy_per_1000_usd"]
        kms_ops = (monthly_state_mutations / 10_000) * s3_pricing["kms_requests_per_10k_usd"]
        s3_total = standard_storage + ia_storage + s3_mutations + kms_ops

        # AWS DynamoDB Distributed Locks
        ddb_pricing = AWS_PRICING["dynamodb_locks"]
        ddb_total = ddb_pricing["pitr_and_storage_monthly_usd"] + (
            (monthly_state_mutations / 1_000_000) * ddb_pricing["lock_transitions_per_million_usd"]
        )

        return {
            "cloud_armor_waf_usd": round(armor_total, 2),
            "s3_remote_state_usd": round(s3_total, 2),
            "dynamodb_locks_usd": round(ddb_total, 2),
            "total_infra_security_usd": round(armor_total + s3_total + ddb_total, 2),
        }

    def estimate_carbon_footprint(
        self,
        primary_region: str = "us-central1",
        monthly_requests: int = 5_000_000,
        avg_duration_ms: float = 65.0,
        vcpu: float = 1.0,
    ) -> dict[str, Any]:
        """Calculates operational energy consumption and environmental CO2 emissions."""
        region_info = REGIONAL_CARBON_INTENSITY.get(
            primary_region, {"gco2_per_kwh": 360.0, "carbon_free_energy_pct": 60.0}
        )
        grid_intensity = region_info["gco2_per_kwh"]

        # Cloud server energy model: ~4.5W per allocated container vCPU
        active_hours = (monthly_requests * (avg_duration_ms / 1000.0)) / 3600.0
        power_draw_kw = (vcpu * 4.5) / 1000.0
        kwh_consumed = active_hours * power_draw_kw

        # CO2 emissions in kg
        co2_kg = (kwh_consumed * grid_intensity) / 1000.0
        gco2_per_100k_requests = (co2_kg * 1000.0) / (monthly_requests / 100_000.0)

        return {
            "region": primary_region,
            "regional_grid_intensity_gco2": grid_intensity,
            "carbon_free_energy_pct": region_info["carbon_free_energy_pct"],
            "kwh_consumed_monthly": round(kwh_consumed, 4),
            "co2_emissions_kg_monthly": round(co2_kg, 4),
            "gco2_per_100k_requests": round(gco2_per_100k_requests, 2),
            "green_window_certified": grid_intensity <= self.max_carbon_intensity_gco2,
        }

    def forecast_carbon_optimal_deployment_window(
        self,
        primary_region: str = "us-central1",
        target_hour_utc: int | None = None,
    ) -> dict[str, Any]:
        """
        Calculates diurnal renewable energy curves (CFE%) to forecast optimal low-carbon deployment windows.
        Recommends scheduling canary transitions during high clean-energy generation windows.
        """
        import math
        if target_hour_utc is None:
            target_hour_utc = datetime.now(UTC).hour

        region_info = REGIONAL_CARBON_INTENSITY.get(
            primary_region, {"gco2_per_kwh": 360.0, "carbon_free_energy_pct": 60.0}
        )
        base_cfe = region_info["carbon_free_energy_pct"]

        # Diurnal solar/wind curve simulation (solar peaks 11:00-16:00 UTC)
        hourly_forecast = []
        for h in range(24):
            solar_factor = math.sin(max(0, min(math.pi, (h - 7) / 10.0 * math.pi))) if 7 <= h <= 17 else 0.0
            cfe_est = min(98.0, max(25.0, base_cfe + (solar_factor * 22.0) - 5.0))
            hourly_forecast.append({
                "hour_utc": h,
                "projected_cfe_pct": round(cfe_est, 1),
                "is_green_window": cfe_est >= 70.0,
            })

        current_cfe = hourly_forecast[target_hour_utc]["projected_cfe_pct"]
        is_green = current_cfe >= 60.0
        best_hour = max(hourly_forecast, key=lambda x: x["projected_cfe_pct"])

        recommendation = (
            "OPTIMAL_CARBON_WINDOW_ACTIVE: Grid renewable generation is high. Safe to proceed with deployment."
            if is_green
            else f"CARBON_AWARE_ADVISORY: Current CFE is {current_cfe}%. Consider scheduling non-urgent canary transitions at {best_hour['hour_utc']:02d}:00 UTC (Projected CFE: {best_hour['projected_cfe_pct']}%)."
        )

        return {
            "region": primary_region,
            "evaluated_hour_utc": target_hour_utc,
            "current_projected_cfe_pct": current_cfe,
            "optimal_window_hour_utc": best_hour["hour_utc"],
            "optimal_window_cfe_pct": best_hour["projected_cfe_pct"],
            "carbon_optimized_deployment_recommended": is_green,
            "recommendation": recommendation,
            "diurnal_24h_forecast": hourly_forecast,
        }

    def evaluate_release_finops(
        self,
        candidate_revision: str = "sentinel-target-app-cand-001",
        baseline_revision: str = "sentinel-target-app-stable-001",
        primary_region: str = "us-central1",
        candidate_vcpu: float = 1.0,
        candidate_mem_gib: float = 0.5,
        baseline_vcpu: float = 1.0,
        baseline_mem_gib: float = 0.5,
        monthly_requests: int = 5_000_000,
        candidate_latency_ms: float = 65.0,
        baseline_latency_ms: float = 60.0,
    ) -> dict[str, Any]:
        """Runs the comprehensive multi-cloud FinOps & GreenOps evaluation gate."""
        cand_compute = self.estimate_cloud_run_cost(
            monthly_requests=monthly_requests,
            avg_duration_ms=candidate_latency_ms,
            vcpu=candidate_vcpu,
            memory_gib=candidate_mem_gib,
        )
        base_compute = self.estimate_cloud_run_cost(
            monthly_requests=monthly_requests,
            avg_duration_ms=baseline_latency_ms,
            vcpu=baseline_vcpu,
            memory_gib=baseline_mem_gib,
        )

        infra_costs = self.estimate_storage_and_security_cost(monthly_requests=monthly_requests)
        carbon_info = self.estimate_carbon_footprint(
            primary_region=primary_region,
            monthly_requests=monthly_requests,
            avg_duration_ms=candidate_latency_ms,
            vcpu=candidate_vcpu,
        )
        carbon_schedule = self.forecast_carbon_optimal_deployment_window(primary_region=primary_region)

        total_candidate_spend = round(cand_compute["total_cloud_run_usd"] + infra_costs["total_infra_security_usd"], 2)
        total_baseline_spend = round(base_compute["total_cloud_run_usd"] + infra_costs["total_infra_security_usd"], 2)

        cost_delta_usd = round(total_candidate_spend - total_baseline_spend, 2)
        cost_delta_pct = round(((cost_delta_usd / total_baseline_spend) * 100.0) if total_baseline_spend > 0 else 0.0, 2)

        violations = []
        if total_candidate_spend > self.monthly_budget_usd:
            violations.append(
                f"Candidate projected monthly spend (${total_candidate_spend}) exceeds maximum FinOps budget (${self.monthly_budget_usd})"
            )
        if cost_delta_pct > self.max_cost_increase_pct:
            violations.append(
                f"Cost surge (+{cost_delta_pct}%) exceeds allowable delta threshold (+{self.max_cost_increase_pct}%)"
            )
        if not carbon_info["green_window_certified"]:
            violations.append(
                f"Grid carbon intensity ({carbon_info['regional_grid_intensity_gco2']} gCO2/kWh) exceeds GreenOps ceiling ({self.max_carbon_intensity_gco2} gCO2/kWh)"
            )

        verdict = "PASS" if not violations else "BUDGET_EXCEEDED"

        return {
            "verdict": verdict,
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "candidate_revision": candidate_revision,
            "baseline_revision": baseline_revision,
            "projected_monthly_spend_usd": total_candidate_spend,
            "baseline_monthly_spend_usd": total_baseline_spend,
            "cost_delta_usd": cost_delta_usd,
            "cost_delta_pct": cost_delta_pct,
            "monthly_budget_limit_usd": self.monthly_budget_usd,
            "budget_utilization_pct": round((total_candidate_spend / self.monthly_budget_usd) * 100.0, 1),
            "cloud_cost_breakdown": {
                "google_cloud_run_compute": cand_compute,
                "google_cloud_armor_waf": {"monthly_cost_usd": infra_costs["cloud_armor_waf_usd"]},
                "aws_s3_state_storage": {"monthly_cost_usd": infra_costs["s3_remote_state_usd"]},
                "aws_dynamodb_locks": {"monthly_cost_usd": infra_costs["dynamodb_locks_usd"]},
            },
            "carbon_footprint": carbon_info,
            "carbon_window_forecast": carbon_schedule,
            "violations": violations,
            "violations_count": len(violations),
        }


def evaluate_cloud_finops_guard(
    policy_path: Path | None = None,
    candidate_revision: str = "sentinel-target-app-cand-001",
    primary_region: str = "us-central1",
    candidate_vcpu: float = 1.0,
    candidate_mem_gib: float = 0.5,
    output_dir: Path | None = None,
    emit_to_backend: bool = False,
    backend_url: str | None = None,
    hmac_secret: str | None = None,
    pipeline_id: str = "finops-01",
    job_id: str = "job-finops-01",
    commit_sha: str = "localdev",
) -> dict[str, Any]:
    """Runs the FinOps guard and writes reports/emits events."""
    guard = CloudFinOpsGuard(policy_path=policy_path)
    report = guard.evaluate_release_finops(
        candidate_revision=candidate_revision,
        primary_region=primary_region,
        candidate_vcpu=candidate_vcpu,
        candidate_mem_gib=candidate_mem_gib,
    )

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "finops-cloud-cost-report.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        # Dual-save canonical spend forecast artifact for GitLab CI plan stage
        forecast_file = output_dir / "finops-spend-forecast.json"
        forecast_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if emit_to_backend and backend_url:
        try:
            emit_event(
                event_type="finops.evaluated",
                data={
                    "verdict": report["verdict"],
                    "projected_monthly_spend_usd": report["projected_monthly_spend_usd"],
                    "budget_utilization_pct": report["budget_utilization_pct"],
                    "violations_count": report["violations_count"],
                    "carbon_gco2_per_100k": report["carbon_footprint"]["gco2_per_100k_requests"],
                },
                backend_url=backend_url,
                hmac_secret=hmac_secret or "sentinel-dev-secret-key-change-in-prod",
                pipeline_id=pipeline_id,
                job_id=job_id,
                commit_sha=commit_sha,
            )
        except Exception:
            pass

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Multi-Cloud FinOps & Carbon Intensity Guard")
    parser.add_argument("--candidate", default="sentinel-target-app-cand-001", help="Candidate revision name")
    parser.add_argument("--region", default="us-central1", help="GCP Region (e.g. us-central1, us-east1)")
    parser.add_argument("--vcpu", type=float, default=1.0, help="Candidate container vCPU sizing")
    parser.add_argument("--memory-gib", type=float, default=0.5, help="Candidate container GiB RAM sizing")
    parser.add_argument("--budget", type=float, default=250.0, help="Monthly cloud budget ceiling ($ USD)")
    parser.add_argument("--policy", default="sentinel/policy.yaml", help="Path to sentinel/policy.yaml")
    parser.add_argument("--output-dir", default="artifacts", help="Directory for JSON artifact output")
    parser.add_argument("--dry-run", action="store_true", help="Simulate FinOps analysis in safe validation mode")
    parser.add_argument("--no-emit", action="store_true", help="Skip backend event emission")
    args = parser.parse_args()

    policy_p = Path(args.policy) if Path(args.policy).exists() else None
    out_dir = Path(args.output_dir)

    report = evaluate_cloud_finops_guard(
        policy_path=policy_p,
        candidate_revision=args.candidate,
        primary_region=args.region,
        candidate_vcpu=args.vcpu,
        candidate_mem_gib=args.memory_gib,
        output_dir=out_dir,
        emit_to_backend=not args.no_emit,
    )

    print(f"\n{'='*65}")
    print("  PROJECT SENTINEL — MULTI-CLOUD FINOPS & GREENOPS GUARD")
    print(f"  Decision: [{report['verdict']}] | Budget Utilization: {report['budget_utilization_pct']}%")
    print(f"  Projected Monthly Spend: ${report['projected_monthly_spend_usd']} / ${report['monthly_budget_limit_usd']}")
    print(f"  Regional Grid Carbon Intensity: {report['carbon_footprint']['regional_grid_intensity_gco2']} gCO2/kWh ({report['carbon_footprint']['region']})")
    print(f"  Carbon Footprint: {report['carbon_footprint']['gco2_per_100k_requests']} gCO2 / 100k requests")
    print(f"  Cost Delta vs Baseline: ${report['cost_delta_usd']} (+{report['cost_delta_pct']}%)")
    if report["violations"]:
        print("  FinOps Policy Violations:")
        for v in report["violations"]:
            print(f"    - [!] {v}")
    else:
        print("  [OK] Release certified within enterprise cloud spend and GreenOps limits.")
    print(f"{'='*65}\n")

    if report["verdict"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
