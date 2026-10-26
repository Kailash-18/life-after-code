#!/usr/bin/env python3
"""
Project Sentinel — Secret Holdout Test Suite (Tier 1 Feature)
============================================================
This test suite is kept strictly isolated inside the gate runner environment.
The repair AI never sees these tests in its context or repository checkout,
preventing the model from tuning fixes specifically to pass known test assertions.

Invariants Verified:
  - INV-01: Zero divisor & empty cart safety (no crash on item_count == 0).
  - INV-02: Non-negative subtotal invariant (discounts can never exceed subtotal).
  - INV-03: Tier normalization invariance (case-insensitive & whitespace resilient).
  - INV-04: Numerical precision stability (floating point rounding bounded to 2 decimals).
  - INV-05: State purity (discount calculations are strictly stateless and side-effect free).
"""

import math
import pytest


def calculate_discount(item_count: int, subtotal: float, tier: str = "Standard") -> float:
    """
    Authoritative reference implementation of order discount logic for invariant checks.
    In actual evaluation, this imports from the candidate repair branch.
    """
    if item_count <= 0 or subtotal <= 0.0:
        return 0.0
    
    tier_clean = tier.strip().upper()
    tier_multipliers = {
        "STANDARD": 0.0,
        "SILVER": 0.05,
        "GOLD": 0.10,
        "PLATINUM": 0.15,
    }
    rate = tier_multipliers.get(tier_clean, 0.0)
    discount = round(subtotal * rate, 2)
    return min(discount, subtotal)


def test_inv01_zero_divisor_empty_cart():
    """INV-01: Zero items must safely return 0.0 discount, never raise ZeroDivisionError."""
    assert calculate_discount(item_count=0, subtotal=150.0) == 0.0
    assert calculate_discount(item_count=0, subtotal=0.0) == 0.0


def test_inv02_non_negative_and_bounded_discount():
    """INV-02: Discount can never be negative and can never exceed total subtotal."""
    discount = calculate_discount(item_count=5, subtotal=200.0, tier="PLATINUM")
    assert 0.0 <= discount <= 200.0

    # Large values
    huge_discount = calculate_discount(item_count=1000, subtotal=1_000_000.0, tier="GOLD")
    assert 0.0 <= huge_discount <= 1_000_000.0


def test_inv03_tier_normalization_invariance():
    """INV-03: Customer tier must be case-insensitive and handle leading/trailing spaces."""
    d1 = calculate_discount(item_count=2, subtotal=100.0, tier="gold")
    d2 = calculate_discount(item_count=2, subtotal=100.0, tier="  GOLD  ")
    d3 = calculate_discount(item_count=2, subtotal=100.0, tier="Gold")
    assert d1 == d2 == d3 == 10.0


def test_inv04_numerical_precision_bounded():
    """INV-04: Calculated values must not suffer from unrounded IEEE 754 precision drift."""
    val = calculate_discount(item_count=3, subtotal=19.99, tier="SILVER")
    # 19.99 * 0.05 = 0.9995 -> 1.00
    assert isinstance(val, float)
    assert not math.isnan(val)
    assert not math.isinf(val)
    # Check max 2 decimal places
    assert round(val, 2) == val


def test_inv05_idempotent_pure_execution():
    """INV-05: Successive calculations must produce identical deterministic results."""
    res1 = calculate_discount(item_count=4, subtotal=88.50, tier="PLATINUM")
    res2 = calculate_discount(item_count=4, subtotal=88.50, tier="PLATINUM")
    assert res1 == res2
