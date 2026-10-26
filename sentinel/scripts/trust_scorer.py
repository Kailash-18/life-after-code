#!/usr/bin/env python3
"""
Project Sentinel — Deterministic Repair Trust Scorer (Tier 1 Feature)
=====================================================================
Core Principle: AI proposes; deterministic gates decide.
The AI can explain the trust score, but can NEVER set or alter it.

Calculates a deterministic 0-100 Trust Score based on:
  1. Gate verdicts (Integrity Gate, Holdout Gate, SAST Gate).
  2. Regression proof quality (AssertionError on broken, pass on fix).
  3. Test coverage delta (new regression test added, coverage preserved).
  4. Diff size & blast radius (surgical diffs rewarded; bloated diffs penalised).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class RepairMetrics:
    integrity_blocking_count: int = 0
    integrity_warning_count: int = 0
    regression_proven: bool = True
    regression_has_correct_assertion: bool = True
    holdout_invariants_passed: bool = True
    sast_violations_count: int = 0
    added_lines: int = 6
    deleted_lines: int = 2
    has_isolated_regression_test: bool = True
    coverage_delta_percent: float = +0.8


def calculate_trust_score(metrics: RepairMetrics) -> dict[str, Any]:
    score = 100
    deductions: list[dict[str, Any]] = []
    bonuses: list[dict[str, Any]] = []

    # 1. Integrity Gate Penalties
    if metrics.integrity_blocking_count > 0:
        penalty = metrics.integrity_blocking_count * 50
        score -= penalty
        deductions.append({
            "factor": "Integrity Gate Blocking Findings",
            "points": -penalty,
            "reason": f"{metrics.integrity_blocking_count} blocking integrity violation(s) detected.",
        })

    if metrics.integrity_warning_count > 0:
        penalty = metrics.integrity_warning_count * 10
        score -= penalty
        deductions.append({
            "factor": "Integrity Gate Warnings",
            "points": -penalty,
            "reason": f"{metrics.integrity_warning_count} warning finding(s).",
        })

    # 2. Regression Proof Verification
    if not metrics.regression_proven:
        score -= 40
        deductions.append({
            "factor": "Regression Proof Not Proven",
            "points": -40,
            "reason": "New regression test did not pass both criteria (failed on broken, passed on fix).",
        })
    elif not metrics.regression_has_correct_assertion:
        score -= 25
        deductions.append({
            "factor": "Regression Failed with Wrong Exception",
            "points": -25,
            "reason": "Test failed with unexpected crash rather than a clean AssertionError.",
        })

    # 3. Holdout Gate Invariant Checks
    if not metrics.holdout_invariants_passed:
        score -= 35
        deductions.append({
            "factor": "Holdout Invariant Violation",
            "points": -35,
            "reason": "Candidate failed one or more secret holdout test invariants.",
        })

    # 4. SAST Security Gate
    if metrics.sast_violations_count > 0:
        penalty = min(metrics.sast_violations_count * 15, 30)
        score -= penalty
        deductions.append({
            "factor": "Security SAST Violations",
            "points": -penalty,
            "reason": f"{metrics.sast_violations_count} security issue(s) detected in patch.",
        })

    # 5. Diff Size & Blast Radius
    total_diff_lines = metrics.added_lines + metrics.deleted_lines
    if total_diff_lines <= 25:
        score += 5
        bonuses.append({
            "factor": "Surgical Targeted Diff",
            "points": +5,
            "reason": f"Compact diff ({total_diff_lines} lines total) strictly isolates the bug fix.",
        })
    elif total_diff_lines > 80:
        penalty = 15 if total_diff_lines <= 150 else 30
        score -= penalty
        deductions.append({
            "factor": "Bloated Diff Size",
            "points": -penalty,
            "reason": f"Diff changes {total_diff_lines} lines; excessive blast radius for emergency repair.",
        })

    # 6. Test Coverage Delta
    if metrics.has_isolated_regression_test:
        score += 5
        bonuses.append({
            "factor": "Dedicated Regression Test Added",
            "points": +5,
            "reason": "Adds tests/regressions/ guard file protecting against future regressions.",
        })

    if metrics.coverage_delta_percent < 0:
        penalty = 20
        score -= penalty
        deductions.append({
            "factor": "Test Coverage Regression",
            "points": -penalty,
            "reason": f"Overall test coverage dropped by {abs(metrics.coverage_delta_percent)}%.",
        })
    elif metrics.coverage_delta_percent > 0:
        bonuses.append({
            "factor": "Test Coverage Expansion",
            "points": +3,
            "reason": f"Test coverage increased by +{metrics.coverage_delta_percent}%.",
        })

    # Clamp to [0, 100]
    final_score = max(0, min(100, score))

    if final_score >= 90:
        rating = "EXEMPLARY"
        recommendation = "Eligible for autonomous merge (Gates and invariants fully satisfied)."
    elif final_score >= 75:
        recommendation = "Acceptable quality; all critical safety gates passed."
        rating = "ACCEPTABLE"
    elif final_score >= 50:
        recommendation = "Suspicious patch; requires mandatory on-call human SRE review."
        rating = "SUSPICIOUS"
    else:
        recommendation = "DANGEROUS: Severe gate breaches or test evasion. Strictly blocked."
        rating = "DANGEROUS"

    # AI Natural Language Explanation (AI explains the score, but cannot set it)
    ai_explanation = (
        f"This repair scored {final_score}/100 ({rating}). "
        f"The deterministic scorer evaluated {len(deductions)} risk deductions and {len(bonuses)} positive markers. "
        + (
            f"Key risk: {deductions[0]['reason']} "
            if deductions
            else "The patch is surgical and satisfies all gate invariants. "
        )
        + recommendation
    )

    return {
        "trust_score": final_score,
        "max_score": 100,
        "rating": rating,
        "recommendation": recommendation,
        "metrics_evaluated": asdict(metrics),
        "deductions": deductions,
        "bonuses": bonuses,
        "ai_explanation": ai_explanation,
        "governance_rule": "Deterministic score computed strictly by gates; AI can explain but never set this score.",
    }


def main():
    parser = argparse.ArgumentParser(description="Sentinel Deterministic Repair Trust Scorer")
    parser.add_argument("--blocking-findings", type=int, default=0)
    parser.add_argument("--warning-findings", type=int, default=0)
    parser.add_argument("--regression-proven", action="store_true", default=True)
    parser.add_argument("--holdout-passed", action="store_true", default=True)
    parser.add_argument("--added-lines", type=int, default=6)
    parser.add_argument("--deleted-lines", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    metrics = RepairMetrics(
        integrity_blocking_count=args.blocking_findings,
        integrity_warning_count=args.warning_findings,
        regression_proven=args.regression_proven,
        holdout_invariants_passed=args.holdout_passed,
        added_lines=args.added_lines,
        deleted_lines=args.deleted_lines,
    )

    result = calculate_trust_score(metrics)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 70)
    print("  PROJECT SENTINEL — DETERMINISTIC REPAIR TRUST SCORER")
    print("  Rule: Deterministic metric; AI can explain but never set it.")
    print("=" * 70)
    print(f"  Trust Score:     {result['trust_score']}/100 [{result['rating']}]")
    print(f"  Recommendation:  {result['recommendation']}")
    print("-" * 70)
    print("  Bonuses:")
    for b in result["bonuses"]:
        print(f"    [+{b['points']}] {b['factor']}: {b['reason']}")
    print("  Deductions:")
    if result["deductions"]:
        for d in result["deductions"]:
            print(f"    [{d['points']}] {d['factor']}: {d['reason']}")
    else:
        print("    None (Zero penalties).")
    print("-" * 70)
    print(f"  AI Explanation:  \"{result['ai_explanation']}\"")
    print("=" * 70)


if __name__ == "__main__":
    main()
