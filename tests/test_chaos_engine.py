"""
Unit tests for Sentinel Chaos Engineering & Resilience Circuit Breaker Engine.
Validates FSM transitions (CLOSED -> OPEN -> HALF-OPEN -> CLOSED) and deterministic fault injection.
"""

from __future__ import annotations

import time
import pytest

from sentinel.scripts.chaos_engine import (
    CanaryCircuitBreaker,
    CircuitState,
    ChaosInjectionEngine,
    execute_chaos_resilience_test,
)


def test_circuit_breaker_initial_state():
    breaker = CanaryCircuitBreaker(failure_threshold=3, recovery_time_seconds=1.0)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_circuit_breaker_trips_to_open_on_threshold():
    breaker = CanaryCircuitBreaker(failure_threshold=3, recovery_time_seconds=1.0)

    breaker.record_failure("Err 1")
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure("Err 2")
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure("Err 3")
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False
    assert len(breaker.trip_history) == 1
    assert breaker.trip_history[0]["previous_state"] == "CLOSED"
    assert breaker.trip_history[0]["new_state"] == "OPEN"


def test_circuit_breaker_transitions_to_half_open_after_timeout():
    breaker = CanaryCircuitBreaker(failure_threshold=2, recovery_time_seconds=0.1)

    breaker.record_failure("Err 1")
    breaker.record_failure("Err 2")
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False

    time.sleep(0.12)
    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN


def test_circuit_breaker_recovers_to_closed_on_half_open_successes():
    breaker = CanaryCircuitBreaker(failure_threshold=2, recovery_time_seconds=0.05, half_open_success_threshold=2)

    breaker.record_failure("Err 1")
    breaker.record_failure("Err 2")
    assert breaker.state == CircuitState.OPEN

    time.sleep(0.06)
    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_re_trips_on_half_open_failure():
    breaker = CanaryCircuitBreaker(failure_threshold=2, recovery_time_seconds=0.05)

    breaker.record_failure("Err 1")
    breaker.record_failure("Err 2")
    assert breaker.state == CircuitState.OPEN

    time.sleep(0.06)
    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.record_failure("Flapped again")
    assert breaker.state == CircuitState.OPEN


def test_chaos_injection_engine_faults():
    # Latency spike
    res_lat = ChaosInjectionEngine.simulate_fault_injection("latency_spike", base_latency_ms=20.0, intensity=1.0)
    assert res_lat["latency_ms"] >= 370.0
    assert res_lat["success"] is True

    # 503 drops
    res_503 = ChaosInjectionEngine.simulate_fault_injection("intermittent_503")
    assert res_503["status_code"] == 503
    assert res_503["success"] is False

    # Timeout
    res_to = ChaosInjectionEngine.simulate_fault_injection("connection_timeout")
    assert res_to["status_code"] == 504
    assert res_to["success"] is False


def test_execute_chaos_resilience_test_simulation():
    res = execute_chaos_resilience_test(iterations=8, fault_type="intermittent_503")
    assert res["total_probes"] == 8
    assert res["resilience_certified"] is True
    assert len(res["trip_events"]) >= 1
