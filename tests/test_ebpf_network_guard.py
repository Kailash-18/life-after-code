"""
Unit tests for Sentinel eBPF Network Socket Guard.
Validates kernel TCP retransmit ratios, socket state counts, and transport anomaly alerts.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from sentinel.scripts.ebpf_network_guard import (
    EbpfNetworkSocketGuard,
    run_ebpf_network_audit,
)


def test_ebpf_network_nominal_healthy():
    guard = EbpfNetworkSocketGuard()
    res = guard.analyze_kernel_socket_telemetry(samples=50, simulated_tcp_drops=0)

    assert res["status"] == "HEALTHY"
    assert res["tcp_retransmit_pct"] == 0.0
    assert res["kernel_bypass_certified"] is True
    assert "TCP_ESTABLISHED" in res["socket_states"]


def test_ebpf_network_detects_tcp_degradation():
    guard = EbpfNetworkSocketGuard(max_retransmit_pct=0.5)
    # Simulate high drop count
    res = guard.analyze_kernel_socket_telemetry(samples=50, simulated_tcp_drops=20)

    assert res["status"] == "TRANSPORT_DEGRADED"
    assert res["kernel_bypass_certified"] is False
    assert len(res["anomalies"]) > 0


def test_run_ebpf_network_audit_artifact(tmp_path: Path):
    report = run_ebpf_network_audit(output_dir=tmp_path)
    assert report["status"] == "HEALTHY"
    out_file = tmp_path / "ebpf-network-socket-report.json"
    assert out_file.exists()
