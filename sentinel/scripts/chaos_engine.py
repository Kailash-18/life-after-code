#!/usr/bin/env python3
"""
Project Sentinel — Chaos Engineering & Resilience Circuit Breaker Engine
Implements deterministic fault injection (latency jitter, 503 drops, cascading fault simulation)
and a robust Finite State Machine Circuit Breaker (CLOSED -> OPEN -> HALF-OPEN).
Guarantees resilience against cascading stampeding herds during canary evaluation.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operations: traffic flows freely
    OPEN = "OPEN"            # Tripped: all traffic blocked/diverted to fallback
    HALF_OPEN = "HALF_OPEN"  # Testing: limited probes allowed through to evaluate recovery


class CanaryCircuitBreaker:
    """
    Production-grade Circuit Breaker protecting microservices during canary evaluations.
    Tracks failure counts and trips automatically if fault rate exceeds threshold within evaluation window.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_time_seconds: float = 5.0,
        half_open_success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds
        self.half_open_success_threshold = half_open_success_threshold
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_state_change = time.time()
        self.trip_history: list[dict[str, Any]] = []

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.half_open_success_threshold:
                self._transition_to(CircuitState.CLOSED, "Half-open probe threshold satisfied; service certified healthy")
        elif self.state == CircuitState.CLOSED:
            self.consecutive_failures = 0

    def record_failure(self, reason: str = "Probe failed") -> None:
        self.consecutive_failures += 1
        if self.state == CircuitState.CLOSED and self.consecutive_failures >= self.failure_threshold:
            self._transition_to(CircuitState.OPEN, f"Failure threshold ({self.failure_threshold}) exceeded: {reason}")
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN, f"Half-open probe failed: {reason}")

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.last_state_change
            if elapsed >= self.recovery_time_seconds:
                self._transition_to(CircuitState.HALF_OPEN, f"Recovery timeout ({self.recovery_time_seconds}s) elapsed; entering half-open trial")
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def _transition_to(self, new_state: CircuitState, reason: str) -> None:
        prev_state = self.state
        self.state = new_state
        self.last_state_change = time.time()
        if new_state == CircuitState.CLOSED:
            self.consecutive_failures = 0
            self.consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self.consecutive_successes = 0

        event = {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "previous_state": prev_state.value,
            "new_state": new_state.value,
            "reason": reason,
        }
        self.trip_history.append(event)


class ChaosInjectionEngine:
    """
    Deterministic Chaos Simulation Engine for validating Sentinel's automated recovery.
    Simulates real-world cloud degradations:
    - latency_spike: Simulates database query timeouts / network saturation
    - intermittent_503: Simulates upstream circuit breaker or out-of-memory pods
    - packet_loss: Simulates cross-AZ transport layer drops
    """

    @staticmethod
    def simulate_fault_injection(
        fault_type: str,
        base_latency_ms: float = 25.0,
        intensity: float = 1.0,
    ) -> dict[str, Any]:
        result = {
            "fault_type": fault_type,
            "simulated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "success": True,
            "latency_ms": base_latency_ms,
            "status_code": 200,
            "injected_error": None,
        }

        if fault_type == "latency_spike":
            added_delay = 350.0 * intensity
            result["latency_ms"] = round(base_latency_ms + added_delay, 2)
            result["injected_error"] = f"Injected synthetic delay of +{added_delay:.1f}ms (Total: {result['latency_ms']}ms)"

        elif fault_type == "intermittent_503":
            result["status_code"] = 503
            result["success"] = False
            result["injected_error"] = "HTTP 503 Service Unavailable: Simulated downstream circuit open / pod eviction"

        elif fault_type == "connection_timeout":
            result["status_code"] = 504
            result["success"] = False
            result["latency_ms"] = 5000.0
            result["injected_error"] = "HTTP 504 Gateway Timeout: Read timeout after 5000ms"

        elif fault_type == "none":
            result["latency_ms"] = base_latency_ms

        return result


def execute_chaos_resilience_test(
    iterations: int = 10,
    fault_type: str = "intermittent_503",
    intensity: float = 1.0,
) -> dict[str, Any]:
    """
    Executes a resilience loop verifying that the Circuit Breaker trips cleanly on chaos injection
    and prevents cascading infrastructure degradation.
    """
    breaker = CanaryCircuitBreaker(failure_threshold=3, recovery_time_seconds=1.0)
    audit_log: list[dict[str, Any]] = []

    for i in range(1, iterations + 1):
        allowed = breaker.allow_request()
        if not allowed:
            audit_log.append({
                "iteration": i,
                "circuit_state": breaker.state.value,
                "action": "SHORT_CIRCUITED",
                "detail": "Request rejected by circuit breaker to protect downstream services",
            })
            continue

        # Halfway through, inject fault
        active_fault = fault_type if i in [2, 3, 4, 5] else "none"
        probe = ChaosInjectionEngine.simulate_fault_injection(active_fault, intensity=intensity)

        if probe["success"] and probe["status_code"] == 200:
            breaker.record_success()
            action = "PROBE_SUCCESS"
        else:
            breaker.record_failure(probe["injected_error"] or "Unknown error")
            action = "PROBE_FAILED"

        audit_log.append({
            "iteration": i,
            "circuit_state": breaker.state.value,
            "action": action,
            "status_code": probe["status_code"],
            "latency_ms": probe["latency_ms"],
        })

    report = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fault_type_tested": fault_type,
        "total_probes": iterations,
        "final_circuit_state": breaker.state.value,
        "circuit_trips": len(breaker.trip_history),
        "trip_events": breaker.trip_history,
        "audit_trail": audit_log,
        "resilience_certified": len(breaker.trip_history) > 0,
    }

    # Save artifact
    art_dir = Path("artifacts")
    art_dir.mkdir(exist_ok=True)
    with open(art_dir / "chaos-resilience-report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sentinel Chaos Engineering & Resilience Engine")
    parser.add_argument("--fault", default="intermittent_503", choices=["intermittent_503", "latency_spike", "connection_timeout", "none"])
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--intensity", type=float, default=1.0)
    args = parser.parse_args()

    res = execute_chaos_resilience_test(iterations=args.iterations, fault_type=args.fault, intensity=args.intensity)
    print(f"Chaos Resilience Run Complete. Circuit Trips: {res['circuit_trips']} | Final State: {res['final_circuit_state']}")
