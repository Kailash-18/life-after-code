"""
Unit tests for ISO/IEC 21031 Software Carbon Intensity (SCI) Specification Engine.
Targets the Devpost 'Most Environmentally Impactful' Prize.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.sci_carbon_engine import (
    SoftwareCarbonIntensityCalculator,
    run_sci_evaluation,
)


def test_sci_calculator_nominal_pass():
    calc = SoftwareCarbonIntensityCalculator(region="us-central1", sci_ceiling_score=35.0)
    report = calc.calculate_sci(total_requests=1_000_000, avg_latency_ms=65.0)

    assert report["verdict"] == "PASS"
    assert report["sci_score"] > 0
    assert report["sci_score"] <= 35.0
    assert report["components"]["energy_consumed_kwh_E"] > 0
    assert report["components"]["embodied_emissions_gco2_M"] > 0


def test_sci_calculator_low_carbon_region_benefit():
    calc_us = SoftwareCarbonIntensityCalculator(region="us-central1")
    calc_eu = SoftwareCarbonIntensityCalculator(region="europe-west1")

    res_us = calc_us.calculate_sci(total_requests=1_000_000)
    res_eu = calc_eu.calculate_sci(total_requests=1_000_000)

    # Europe-west1 has 92% CFE and lower marginal grid emission factor than us-central1
    assert res_eu["sci_score"] < res_us["sci_score"]


def test_sci_calculator_breach_ceiling():
    # Artificially low ceiling
    calc = SoftwareCarbonIntensityCalculator(sci_ceiling_score=0.1)
    report = calc.calculate_sci(total_requests=10_000_000, avg_latency_ms=300.0)

    assert report["verdict"] == "CARBON_INTENSITY_EXCEEDED"


def test_run_sci_evaluation_writes_artifact(tmp_path: Path):
    report = run_sci_evaluation(output_dir=tmp_path)
    assert report["verdict"] == "PASS"
    out_file = tmp_path / "sci-carbon-intensity-report.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["specification"] == "ISO/IEC 21031 (Green Software Foundation SCI)"
