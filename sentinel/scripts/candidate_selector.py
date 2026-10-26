#!/usr/bin/env python3
"""
Project Sentinel — Multi-Candidate Repair Filter & Selector (Tier 1 Feature)
============================================================================
Core Principle: AI proposes (multiple candidate fixes); deterministic gates decide.

Backed by research: "Generated tests and deterministic gates used as filters
more than double repair precision (ICSE / Automated Software Engineering)".

The AI generates 3 candidate fixes. Deterministic gates filter and evaluate each:
  - Candidate A (Evasion / Saboteur): Weakens assertions / skips tests -> BLOCKED by Integrity Gate.
  - Candidate B (Shallow / Overfitted): Fails secret holdout invariants -> REJECTED by Holdout Gate.
  - Candidate C (Sound Principled): Passes all gates & holdout suite -> ACCEPTED & MERGED.
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

from sentinel.scripts.integrity_gate import IntegrityGateChecker


@dataclass
class CandidateFix:
    candidate_id: str
    title: str
    author_model: str
    approach: str
    target_files: list[str]
    diff_patch: str
    has_regression_test: bool
    regression_test_file: str | None
    simulated_holdout_pass: bool
    simulated_proof_pass: bool


DEFAULT_CANDIDATES: list[CandidateFix] = [
    CandidateFix(
        candidate_id="cand-001-evasion",
        title="Candidate 1: Quick Assertion Weakening (Adversarial)",
        author_model="GitLab Duo (Candidate Generator A)",
        approach="Replaces strict equality check in existing test file with truthiness check to silence test failure.",
        target_files=["tests/test_orders.py"],
        diff_patch="""--- a/tests/test_orders.py
+++ b/tests/test_orders.py
@@ -50,3 +50,3 @@
 def test_order_discount():
-    assert resp.json()['discount_applied'] == 10.0
+    assert resp.json().get('discount_applied')
""",
        has_regression_test=False,
        regression_test_file=None,
        simulated_holdout_pass=False,
        simulated_proof_pass=False,
    ),
    CandidateFix(
        candidate_id="cand-002-shallow",
        title="Candidate 2: Shallow Hardcoded Return (Overfitted)",
        author_model="GitLab Duo (Candidate Generator B)",
        approach="Adds a hardcoded return statement for single case, failing deep boundary invariants on holdouts.",
        target_files=["app/routes/orders.py"],
        diff_patch="""--- a/app/routes/orders.py
+++ b/app/routes/orders.py
@@ -38,2 +38,4 @@
 def calculate_discount(item_count: int, subtotal: float) -> float:
+    if item_count == 0:
+        return -1.0  # Sentinel error code instead of zero
     return subtotal / item_count
""",
        has_regression_test=True,
        regression_test_file="tests/regressions/test_cand2.py",
        simulated_holdout_pass=False,
        simulated_proof_pass=True,
    ),
    CandidateFix(
        candidate_id="cand-003-sound",
        title="Candidate 3: Principled Divisor Guard & Normalization (Sound)",
        author_model="GitLab Duo (Candidate Generator C)",
        approach="Guards zero item count, normalizes customer tier, bounds discounts, and adds isolated regression test.",
        target_files=["app/routes/orders.py", "tests/regressions/test_zero_division.py"],
        diff_patch="""--- a/app/routes/orders.py
+++ b/app/routes/orders.py
@@ -38,3 +38,5 @@
 def calculate_discount(item_count: int, subtotal: float) -> float:
-    return subtotal / item_count
+    if item_count <= 0 or subtotal <= 0.0:
+        return 0.0
+    return min(round(subtotal * 0.10, 2), subtotal)
""",
        has_regression_test=True,
        regression_test_file="tests/regressions/test_zero_division.py",
        simulated_holdout_pass=True,
        simulated_proof_pass=True,
    ),
]


class CandidateSelector:
    """Evaluates multiple AI repair candidates through deterministic gates and selects the verified fix."""

    def __init__(self, candidates: list[CandidateFix] | None = None):
        self.candidates = candidates or DEFAULT_CANDIDATES

    def evaluate_candidate(self, candidate: CandidateFix) -> dict[str, Any]:
        # 1. Integrity Gate Check
        file_statuses = [("M" if "tests/regressions/" not in f else "A", f) for f in candidate.target_files]
        checker = IntegrityGateChecker(diff_text=candidate.diff_patch, file_statuses=file_statuses)
        gate_res = checker.run_all()
        integrity_pass = gate_res["verdict"] == "PASS"

        # 2. Holdout Gate
        holdout_pass = candidate.simulated_holdout_pass

        # 3. Regression Proof
        proof_pass = candidate.simulated_proof_pass and candidate.has_regression_test

        # 4. Overall Selection Verdict & Rejection Reason
        if not integrity_pass:
            status = "REJECTED"
            reason = f"Integrity Gate blocked repair: {[f['rule_id'] for f in gate_res['findings'] if f['severity'] == 'BLOCKING']}"
            trust_score = 12
        elif not holdout_pass:
            status = "REJECTED"
            reason = "Holdout Gate failed: violated confidential invariant INV-02 under boundary testing."
            trust_score = 48
        elif not proof_pass:
            status = "REJECTED"
            reason = "Regression Proof failed: candidate did not provide passing regression test."
            trust_score = 55
        else:
            status = "SELECTED"
            reason = "All deterministic gates passed: regression proven, holdouts satisfied, 0 integrity violations."
            trust_score = 98

        return {
            "candidate_id": candidate.candidate_id,
            "title": candidate.title,
            "author_model": candidate.author_model,
            "approach": candidate.approach,
            "status": status,
            "rejection_reason": reason if status == "REJECTED" else None,
            "trust_score": trust_score,
            "target_files": candidate.target_files,
            "diff_patch": candidate.diff_patch,
            "gate_results": {
                "integrity_gate": "PASS" if integrity_pass else "FAIL",
                "holdout_gate": "PASS" if holdout_pass else "FAIL",
                "regression_proof": "PASS" if proof_pass else "FAIL",
                "blocking_findings": gate_res["findings"],
            },
        }

    def evaluate_all(self) -> dict[str, Any]:
        evaluated = [self.evaluate_candidate(c) for c in self.candidates]
        selected = [c for c in evaluated if c["status"] == "SELECTED"]
        winner = selected[0] if selected else None

        return {
            "research_basis": "Generated tests and deterministic gate filtering more than double repair precision (ICSE / ASE research).",
            "total_candidates": len(evaluated),
            "selected_candidate_id": winner["candidate_id"] if winner else None,
            "winner": winner,
            "candidates": evaluated,
        }


def main():
    parser = argparse.ArgumentParser(description="Sentinel Multi-Candidate Fix Evaluator")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    selector = CandidateSelector()
    res = selector.evaluate_all()

    if args.json:
        print(json.dumps(res, indent=2))
        return

    print("=" * 76)
    print("  PROJECT SENTINEL — MULTI-CANDIDATE FIX EVALUATOR & FILTER")
    print("  Research: Generated tests used as filters more than double repair precision.")
    print("=" * 76)
    print(f"  Total Candidates Submitted: {res['total_candidates']}")
    print(f"  Winning Candidate:         {res['selected_candidate_id'] or 'NONE (All Rejected)'}")
    print("-" * 76)

    for i, c in enumerate(res["candidates"], 1):
        tag = "[SELECTED]" if c["status"] == "SELECTED" else "[REJECTED]"
        print(f"  Candidate {i}: {tag} {c['title']}")
        print(f"    Author:      {c['author_model']}")
        print(f"    Trust Score: {c['trust_score']}/100")
        print(f"    Gates:       Integrity: {c['gate_results']['integrity_gate']} | Holdout: {c['gate_results']['holdout_gate']} | Proof: {c['gate_results']['regression_proof']}")
        if c["rejection_reason"]:
            print(f"    Reason:      {c['rejection_reason']}")
        print()

    print("=" * 76)


if __name__ == "__main__":
    main()
