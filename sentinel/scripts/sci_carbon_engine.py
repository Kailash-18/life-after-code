#!/usr/bin/env python3
"""
Project Sentinel — ISO/IEC 21031 Software Carbon Intensity (SCI) Specification Engine
Implements the Green Software Foundation SCI Equation:
    SCI = ((E * I) + M) / R
Where:
    E = Energy consumed by software system (kWh)
    I = Location-based marginal carbon intensity of grid (gCO2eq / kWh)
    M = Embodied emissions of serverless hardware infrastructure (gCO2eq)
    R = Functional unit of work (e.g. per 1,000,000 HTTP API transactions)
Targets the Devpost 'Most Environmentally Impactful' Prize ($5,000).
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
# GRID CARBON INTENSITIES (gCO2eq / kWh) & EMBODIED CARBON PARAMETERS
# Sources: Green Software Foundation Carbon Aware SDK, WattTime, and Cloud Carbon Footprint
# ------------------------------------------------------------------------------
REGIONAL_GRID_EMISSIONS = {
    "us-central1": {"marginal_gco2_kwh": 380.0, "grid_mix": "SPP / MISO", "cfe_pct": 64.0},
    "us-east1": {"marginal_gco2_kwh": 340.0, "grid_mix": "PJM Interconnection", "cfe_pct": 58.0},
    "europe-west1": {"marginal_gco2_kwh": 115.0, "grid_mix": "Elia Grid", "cfe_pct": 92.0},
    "us-west1": {"marginal_gco2_kwh": 110.0, "grid_mix": "BPA Hydro/Wind", "cfe_pct": 89.0},
}

# Embodied carbon of server rack hardware allocated to serverless vCPU
# ~1200 kg CO2eq per physical 2-socket server over 4-year lifespan (35,040 hours)
# Allocated per vCPU-hour: ~0.0085 kg CO2eq = 8.5 gCO2eq / vCPU-hour
EMBODIED_CARBON_PER_VCPU_HOUR_GCO2 = 8.5
CONTAINER_AVG_POWER_DRAW_KW_PER_VCPU = 0.0045  # 4.5 Watts active


class SoftwareCarbonIntensityCalculator:
    """Calculates standardized ISO/IEC 21031 Software Carbon Intensity (SCI)."""

    def __init__(
        self,
        service_name: str = "sentinel-target-app",
        region: str = "us-central1",
        sci_ceiling_score: float = 35.0,
    ) -> None:
        self.service_name = service_name
        self.region = region
        self.sci_ceiling_score = sci_ceiling_score

    def calculate_sci(
        self,
        total_requests: int = 1_000_000,
        avg_latency_ms: float = 65.0,
        allocated_vcpu: float = 1.0,
        allocated_mem_gb: float = 0.5,
        network_egress_gb: float = 2.5,
    ) -> dict[str, Any]:
        """Evaluates ISO/IEC 21031 SCI equation components and outputs certification."""
        region_data = REGIONAL_GRID_EMISSIONS.get(
            self.region, {"marginal_gco2_kwh": 350.0, "grid_mix": "Global Average", "cfe_pct": 60.0}
        )
        grid_i = region_data["marginal_gco2_kwh"]

        # 1. Operational Energy (E) in kWh
        active_hours = (total_requests * (avg_latency_ms / 1000.0)) / 3600.0
        compute_kwh = active_hours * (allocated_vcpu * CONTAINER_AVG_POWER_DRAW_KW_PER_VCPU)
        # DRAM power draw ~ 0.38W per GiB
        memory_kwh = active_hours * ((allocated_mem_gb * 0.38) / 1000.0)
        # Network transmission energy ~ 0.001 kWh / GB
        network_kwh = network_egress_gb * 0.001
        total_energy_e = compute_kwh + memory_kwh + network_kwh

        # 2. Operational Emissions: E * I (in gCO2eq)
        operational_emissions_gco2 = total_energy_e * grid_i

        # 3. Embodied Emissions (M) in gCO2eq
        embodied_emissions_m = active_hours * allocated_vcpu * EMBODIED_CARBON_PER_VCPU_HOUR_GCO2

        # 4. Total Carbon Footprint (O + M)
        total_carbon_gco2 = operational_emissions_gco2 + embodied_emissions_m

        # 5. Functional Unit (R) = per 100,000 HTTP transactions
        functional_units = total_requests / 100_000.0
        sci_score = round(total_carbon_gco2 / functional_units, 3)

        passed_gate = sci_score <= self.sci_ceiling_score

        return {
            "specification": "ISO/IEC 21031 (Green Software Foundation SCI)",
            "service_name": self.service_name,
            "region": self.region,
            "grid_name": region_data["grid_mix"],
            "carbon_free_energy_pct": region_data["cfe_pct"],
            "sci_score": sci_score,
            "sci_unit": "gCO2eq / 100,000 requests",
            "sci_ceiling_target": self.sci_ceiling_score,
            "verdict": "PASS" if passed_gate else "CARBON_INTENSITY_EXCEEDED",
            "components": {
                "energy_consumed_kwh_E": round(total_energy_e, 5),
                "grid_marginal_intensity_I": grid_i,
                "operational_emissions_gco2": round(operational_emissions_gco2, 3),
                "embodied_emissions_gco2_M": round(embodied_emissions_m, 3),
                "total_emissions_gco2": round(total_carbon_gco2, 3),
                "functional_units_R": functional_units,
            },
            "recommendations": [
                "Deploy during high renewable energy availability windows (CFE > 80%)",
                "Utilize serverless concurrency scaling to minimize active vCPU idle hours",
            ],
        }


def run_sci_evaluation(
    service_name: str = "sentinel-target-app",
    region: str = "us-central1",
    output_dir: Path | None = None,
    emit_to_backend: bool = False,
    backend_url: str | None = None,
    hmac_secret: str | None = None,
) -> dict[str, Any]:
    calc = SoftwareCarbonIntensityCalculator(service_name=service_name, region=region)
    report = calc.calculate_sci()

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "sci-carbon-intensity-report.json"
        out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if emit_to_backend and backend_url:
        try:
            emit_event(
                event_type="sustainability.sci_evaluated",
                data={
                    "service": service_name,
                    "sci_score": report["sci_score"],
                    "verdict": report["verdict"],
                    "grid": report["grid_name"],
                },
                backend_url=backend_url,
                hmac_secret=hmac_secret or "sentinel-dev-secret-key-change-in-prod",
            )
        except Exception:
            pass

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel ISO/IEC 21031 Software Carbon Intensity (SCI) Engine")
    parser.add_argument("--service", default="sentinel-target-app", help="Service name")
    parser.add_argument("--region", default="us-central1", help="Target cloud deployment region")
    parser.add_argument("--requests", type=int, default=1_000_000, help="Transaction volume")
    parser.add_argument("--latency-ms", type=float, default=65.0, help="Average service latency (ms)")
    parser.add_argument("--output-dir", default="artifacts", help="Report output directory")
    parser.add_argument("--no-emit", action="store_true", help="Skip backend event emission")
    args = parser.parse_args()

    calc = SoftwareCarbonIntensityCalculator(service_name=args.service, region=args.region)
    report = calc.calculate_sci(total_requests=args.requests, avg_latency_ms=args.latency_ms)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sci-carbon-intensity-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{'='*70}")
    print("  PROJECT SENTINEL — ISO/IEC 21031 SOFTWARE CARBON INTENSITY (SCI)")
    print(f"  Service: {report['service_name']} | Decision: [{report['verdict']}]")
    print(f"  SCI Score: {report['sci_score']} {report['sci_unit']} (Target: < {report['sci_ceiling_target']})")
    print(f"  Region: {report['region']} ({report['grid_name']}) | Carbon-Free Energy: {report['carbon_free_energy_pct']}%")
    print(f"  Total Energy (E): {report['components']['energy_consumed_kwh_E']} kWh | Embodied Carbon (M): {report['components']['embodied_emissions_gco2_M']} gCO2")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
