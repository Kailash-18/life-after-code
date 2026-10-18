"""
Unit tests for Sentinel L4/L7 eBPF Kernel Network & TLS Telemetry Engine.
Validates transport layer decomposition (DNS -> TCP -> TLS -> TTFB) and socket anomaly detection.
"""

from __future__ import annotations

import pytest

from sentinel.scripts.ebpf_tracer import KernelSocketProbe, run_ebpf_telemetry_audit


def test_kernel_socket_probe_nominal():
    trace = KernelSocketProbe.trace_connection_lifecycle(simulate_degradation=False)

    assert trace["phases_ms"]["dns_resolution"] > 0
    assert trace["phases_ms"]["tcp_3way_handshake"] > 0
    assert trace["phases_ms"]["tls_1_3_handshake"] > 0
    assert trace["phases_ms"]["time_to_first_byte"] > 0
    assert trace["transport_health_score"] >= 80.0
    assert trace["ebpf_kernel_metrics"]["socket_state"] == "TCP_ESTABLISHED"


def test_kernel_socket_probe_degradation():
    trace = KernelSocketProbe.trace_connection_lifecycle(simulate_degradation=True)

    assert trace["ebpf_kernel_metrics"]["tcp_retransmits"] > 0
    assert trace["transport_health_score"] < 80.0
    assert trace["transport_status"] in ["DEGRADED", "CRITICAL"]


def test_run_ebpf_telemetry_audit():
    report = run_ebpf_telemetry_audit(samples=5, simulate_degradation=False)

    assert report["samples_collected"] == 5
    assert report["status"] == "PASS"
    assert report["mean_transport_health_score"] >= 80.0
    assert len(report["traces"]) == 5
