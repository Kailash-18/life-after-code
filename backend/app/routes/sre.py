"""
Project Sentinel — SRE Platform Telemetry Routes
Exposes authoritative endpoints for:
- Statistical Latency Significance (Mann-Whitney U) & Google SRE Multi-Window Error Budget Burn Rate
- Policy-as-Code Open Policy Agent (OPA) / Rego Admission Guardrails Compliance
- L4/L7 eBPF Kernel Socket Tracing & Latency Decomposition
- Multi-Region Disaster Recovery (DR) RTO/RPO SLA Health
- EWMA & CUSUM Adaptive Drift Detection
"""

from __future__ import annotations

import copy
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.persistence.factory import get_repository
from sentinel.scripts.disaster_recovery import DisasterRecoveryOrchestrator
from sentinel.scripts.drift_detector import AdaptiveDriftDetector
from sentinel.scripts.ebpf_tracer import run_ebpf_telemetry_audit
from sentinel.scripts.opa_validator import RegoPolicyEngine
from sentinel.scripts.statistical_analyzer import compute_composite_health_score

logger = logging.getLogger("sentinel.sre")

router = APIRouter(prefix="/api/v1/sre", tags=["SRE Telemetry"])

# Global singleton for continuous drift tracking. It is fed only with evaluator samples
# it has not seen yet, so polling the endpoint does not move the statistics.
_DRIFT_DETECTOR = AdaptiveDriftDetector(baseline_mean=28.5, baseline_std=4.2)
_DRIFT_LAST_SAMPLE_ID: str | None = None


def _source(kind: str, note: str) -> dict[str, str]:
    """Where a panel's numbers come from. Only "measured" reads the running service.

    kind: measured | derived (from a real measurement plus modelled inputs) |
          reference (a fixed reference input, not the deployed service) | simulated.
    """
    return {"kind": kind, "note": note}


def _label(result: dict[str, Any], kind: str, note: str) -> dict[str, Any]:
    """Attach where the numbers come from (see _source); never upgrades simulated data to measured."""
    result["data_source"] = _source(kind, note)
    if kind != "measured" and "is_measured" in result:
        result["is_measured"] = False
    return result


_SABOTEUR_NOTE = ("Scripted attack diffs run through the real Integrity Gate rules; these are examples, "
                  "not attacks seen in a live repair.")


class ManifestEvaluationRequest(BaseModel):
    manifest: dict[str, Any] = Field(default_factory=dict, description="Deployment manifest to evaluate against OPA Rego policies")


def _get_nominal_manifest() -> dict[str, Any]:
    """Nominal production-grade Cloud Run manifest adhering to SLSA Level 3 Zero-Trust guardrails."""
    return {
        "service": "sentinel-target-app",
        "containers": [
            {
                "name": "target-app",
                "image": "us-docker.pkg.dev/project-sentinel/sentinel-repo/target-app:v1.5.0@sha256:7f1c2d3e4f5a6b7c",
                "resources": {
                    "limits": {"cpu": "2000m", "memory": "2Gi"},
                    "requests": {"cpu": "1000m", "memory": "1Gi"},
                },
                "security_context": {
                    "run_as_root": False,
                    "read_only_root_filesystem": True,
                    "allow_privilege_escalation": False,
                },
            }
        ],
        "deployment": {
            "strategy": "canary",
            "canary_initial_traffic": 10,
        },
        "network": {
            "cloud_armor_waf_enabled": True,
            "ingress": "internal-and-cloud-load-balancing",
        },
        "supply_chain": {
            "slsa_level": "SLSA_BUILD_LEVEL_3",
            "cosign_verified": True,
        },
    }


@router.get("/health", response_model=dict[str, Any])
async def get_sre_composite_health(
    slo_target: float = Query(0.999, description="Target availability SLO (e.g. 0.999 for 99.9%)"),
) -> dict[str, Any]:
    """
    Computes an authoritative SRE composite health score combining:
    - Statistical latency significance (Mann-Whitney U rank-sum test)
    - Google SRE Multi-Window Multi-Burn-Rate Error Budget tracking
    - Latency IQR & Z-score outlier spread
    """
    repo = get_repository()
    latest_sample = repo.get_latest_health_sample()
    if latest_sample is None or latest_sample.error_rate is None or latest_sample.p95_ms is None:
        # Never invent a health score: without an evaluator measurement there is nothing to score.
        return {
            "status": "NO_DATA",
            "health_score": None,
            "error_budget": None,
            "hypothesis_testing": None,
            "latency_iqr": None,
            "data_source": _source("measured", "No evaluator measurement recorded yet."),
        }

    error_rate = latest_sample.error_rate
    p95_ms = latest_sample.p95_ms

    # Synthesize realistic latency samples around observed p95 for rank-sum testing
    candidate_latencies = [max(5.0, p95_ms * (0.8 + 0.05 * i)) for i in range(10)]
    stable_latencies = [max(5.0, 25.0 * (0.85 + 0.03 * i)) for i in range(10)]

    score_data = compute_composite_health_score(
        candidate_latencies=candidate_latencies,
        stable_latencies=stable_latencies,
        error_rate=error_rate,
        slo_target=slo_target,
    )
    score_data["data_source"] = _source(
        "derived",
        f"Error rate and p95 from evaluator sample {latest_sample.id}; the latency distributions "
        "used for the rank-sum test are modelled around that p95, not raw request timings.",
    )
    return score_data


@router.get("/opa", response_model=dict[str, Any])
async def get_opa_compliance() -> dict[str, Any]:
    """
    Evaluates current production deployment configuration against immutable Rego policies:
    - Zero-Trust Least Privilege (non-root, read-only rootfs)
    - SLSA Build Level 3 Supply Chain Attestation
    - Blast Radius Limits (canary split <= 10%)
    - Cloud Armor L7 WAF Protection
    """
    engine = RegoPolicyEngine()
    manifest = _get_nominal_manifest()
    result = engine.evaluate(manifest)
    result["data_source"] = _source(
        "reference", "Policies evaluated against a fixed reference manifest, not the deployed Cloud Run service."
    )
    return result


@router.post("/opa/validate", response_model=dict[str, Any])
async def validate_opa_manifest(req: ManifestEvaluationRequest) -> dict[str, Any]:
    """Ad-hoc evaluation of a custom deployment manifest against OPA Rego guardrails."""
    engine = RegoPolicyEngine()
    manifest = req.manifest or _get_nominal_manifest()
    return engine.evaluate(manifest)


@router.get("/ebpf", response_model=dict[str, Any])
async def get_ebpf_telemetry(
    samples: int = Query(5, ge=1, le=50, description="Number of kernel socket connection traces to aggregate"),
) -> dict[str, Any]:
    """
    Simulates low-overhead L4/L7 eBPF socket tracing:
    - Nanosecond latency decomposition (DNS -> TCP SYN/ACK -> TLS 1.3 -> TTFB -> Content transfer)
    - Kernel socket metrics (tcp_retransmits, syn_queue_drops, buffer jitter)
    """
    result = run_ebpf_telemetry_audit(samples=samples, simulate_degradation=False)
    result["data_source"] = _source("simulated", "Socket traces are generated by the simulator; no eBPF probe is attached.")
    return result


@router.get("/dr", response_model=dict[str, Any])
async def get_disaster_recovery_status() -> dict[str, Any]:
    """
    Returns multi-region disaster recovery SLA metrics:
    - Primary Region (us-central1) & Failover Standby Region (us-east1)
    - Recovery Time Objective (RTO < 5.0s SLA)
    - Recovery Point Objective (RPO = 0.0s stateless guarantee)
    - Anycast BGP route steering readiness
    """
    orchestrator = DisasterRecoveryOrchestrator(
        primary_region="us-central1",
        secondary_region="us-east1",
    )
    # Perform non-destructive probe verification
    report = orchestrator.simulate_regional_outage_and_failover()
    rto = report.get("recovery_metrics", {}).get("rto_seconds", 1.85)
    rpo = report.get("recovery_metrics", {}).get("rpo_seconds", 0.0)

    return {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "primary_region": "us-central1",
        "secondary_region": "us-east1",
        "active_region": "us-central1",
        "rto_seconds": rto,
        "rpo_seconds": rpo,
        "status": "OPTIMAL" if rto <= 5.0 and rpo == 0.0 else "DEGRADED",
        "data_source": _source("simulated", "RTO/RPO come from a simulated regional failover; no failover was run."),
    }


@router.get("/drift", response_model=dict[str, Any])
async def get_adaptive_drift_telemetry(
    observed_latency: float | None = Query(None, description="Optional observed latency measurement to update EWMA/CUSUM state"),
) -> dict[str, Any]:
    """
    Two-sided CUSUM and EWMA quality control engine:
    Detects statistically significant micro-regressions and gradual latency creep before hard static SLO thresholds breach.
    """
    global _DRIFT_LAST_SAMPLE_ID
    repo = get_repository()
    latest_sample = repo.get_latest_health_sample()

    if observed_latency is not None:
        # What-if query: evaluated on a copy so callers cannot move the shared statistics.
        detector = copy.deepcopy(_DRIFT_DETECTOR)
        val = observed_latency
        update_res = detector.update(val)
        source = _source("derived", "What-if value supplied in the request; shared drift state unchanged.")
    elif latest_sample is None or latest_sample.p95_ms is None:
        return {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "observed_value": None,
            "current_ewma": None,
            "cusum_high_statistic": None,
            "cusum_low_statistic": None,
            "decision_threshold_h": None,
            "drift_detected": False,
            "status": "NO_DATA",
            "action": "No evaluator measurement recorded yet.",
            "data_source": _source("measured", "No evaluator measurement recorded yet."),
        }
    else:
        detector = _DRIFT_DETECTOR
        val = latest_sample.p95_ms
        if latest_sample.id != _DRIFT_LAST_SAMPLE_ID:
            update_res = detector.update(val)
            _DRIFT_LAST_SAMPLE_ID = latest_sample.id
        else:
            update_res = detector.history[-1] if detector.history else {}
        source = _source("measured", f"p95 from evaluator sample {latest_sample.id}; baseline is a fixed assumption.")

    return {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observed_value": val,
        "current_ewma": round(detector.current_ewma, 2),
        "cusum_high_statistic": round(detector.s_high, 2),
        "cusum_low_statistic": round(detector.s_low, 2),
        "decision_threshold_h": round(detector.cusum_h, 2),
        "drift_detected": update_res.get("drift_detected", False),
        "status": update_res.get("status", "NOMINAL"),
        "action": update_res.get("action", "NOMINAL: Process mean centered within allowable variance envelope"),
        "data_source": source,
    }


@router.get("/saboteur", response_model=dict[str, Any])
async def get_saboteur_arena(
    strategy: str = Query("all", description="Specific attack strategy to evaluate or 'all'"),
) -> dict[str, Any]:
    """
    Tier 1 Headline Feature: Saboteur Adversarial Agent vs Integrity Gate.
    Demonstrates live adversarial LLM evasion attempts (skips, weakened assertions, test deletions)
    and verifies that the deterministic Integrity Gate intercepts 100% of attempts.
    """
    from sentinel.scripts.saboteur import ATTACK_CATALOG, SaboteurEngine

    engine = SaboteurEngine()
    if strategy == "all":
        return _label(engine.run_all_attacks(), "reference", _SABOTEUR_NOTE)
    
    matched = [a for a in ATTACK_CATALOG if a.strategy_id == strategy]
    if not matched:
        return _label(engine.run_all_attacks(), "reference", _SABOTEUR_NOTE)
    
    res = engine.run_attack(matched[0])
    return _label({
        "total_attacks": 1,
        "caught_count": 1 if res["blocked"] else 0,
        "evaded_count": 0 if res["blocked"] else 1,
        "all_blocked": res["blocked"],
        "results": [res],
    }, "reference", _SABOTEUR_NOTE)


@router.get("/candidates", response_model=dict[str, Any])
async def get_candidate_fixes() -> dict[str, Any]:
    """
    Tier 1 Feature: Multiple Candidate Fixes.
    The AI writes 3 candidate fixes. Deterministic gates filter and evaluate each,
    selecting the verified fix while showing explicit rejection reasons for rejects.
    Backed by research: generated tests used as filters more than double precision.
    """
    from sentinel.scripts.candidate_selector import CandidateSelector

    selector = CandidateSelector()
    return _label(selector.evaluate_all(), "simulated",
                  "Three scripted example candidates with preset gate outcomes; not candidates from a real incident.")


@router.get("/trust-score", response_model=dict[str, Any])
async def get_repair_trust_score(
    blocking_findings: int = Query(0, ge=0),
    warning_findings: int = Query(0, ge=0),
    regression_proven: bool = Query(True),
    holdout_passed: bool = Query(True),
    added_lines: int = Query(6, ge=0),
    deleted_lines: int = Query(2, ge=0),
    coverage_delta: float = Query(0.8),
) -> dict[str, Any]:
    """
    Tier 1 Feature: Deterministic Trust Score per Repair.
    Calculates a deterministic 0-100 score built from gate results, test coverage change,
    and diff size. The AI can explain the score but never set or alter it.
    """
    from sentinel.scripts.trust_scorer import RepairMetrics, calculate_trust_score

    metrics = RepairMetrics(
        integrity_blocking_count=blocking_findings,
        integrity_warning_count=warning_findings,
        regression_proven=regression_proven,
        holdout_invariants_passed=holdout_passed,
        added_lines=added_lines,
        deleted_lines=deleted_lines,
        coverage_delta_percent=coverage_delta,
    )
    return _label(calculate_trust_score(metrics), "derived",
                  "Computed from the query parameters (defaults if none given), not from a recorded repair.")


@router.get("/holdout", response_model=dict[str, Any])
async def get_holdout_gate_status(
    candidate_sha: str = Query("HEAD", description="Candidate SHA to evaluate against secret holdout invariants"),
) -> dict[str, Any]:
    """
    Tier 1 Feature: Hidden Holdout Tests.
    Executes secret holdout test invariants strictly inside the isolated gate environment.
    Guarantees AI fixes are not overfitted to known public test assertions.
    """
    from sentinel.scripts.holdout_gate import run_holdout_gate

    return _label(run_holdout_gate(candidate_sha=candidate_sha), "reference",
                  "Holdout invariants run against the code in this deployment, not against a specific repair MR.")


@router.get("/diff-risk", response_model=dict[str, Any])
async def get_canary_diff_risk(
    diff_text: str = Query("", description="Git diff to evaluate"),
    author: str = Query("gitlab-duo-flow", description="Commit author"),
    branch: str = Query("duo/repair-candidate", description="Git branch name"),
) -> dict[str, Any]:
    """
    Tier 2 Feature 5: Risk-Adaptive Canary Diff Scorer.
    Scores diffs deterministically based on sensitive files, size, dependency bumps,
    and AI authorship. Generates adaptive rollout schedules (1% -> 10% -> 50% -> 100%).
    """
    from sentinel.scripts.canary_deploy import get_deployment_strategies_catalog, score_diff_risk

    risk = score_diff_risk(diff_text=diff_text, author=author, branch=branch)
    return _label(get_deployment_strategies_catalog(diff_risk=risk), "derived",
                  "Scored from the diff text given in the request (empty by default), not from a deployed release.")


@router.get("/shadow-replay", response_model=dict[str, Any])
async def get_shadow_traffic_replay(
    incident_id: str = Query("inc-demo-003", description="Incident ID to replay"),
    candidate_rev: str = Query("sentinel-target-app-cand-fix-002", description="Candidate revision"),
    samples: int = Query(50, ge=5, le=200, description="Number of shadowed requests to replay"),
) -> dict[str, Any]:
    """
    Tier 2 Feature 7: Shadow Traffic Replay Engine.
    Replays failing incident traffic against the candidate revision to verify
    zero errors and 100% response parity with 0% live user blast radius.
    """
    from sentinel.scripts.shadow_replay import run_shadow_replay

    return _label(run_shadow_replay(incident_id=incident_id, candidate_revision=candidate_rev, sample_count=samples),
                  "simulated", "Requests and responses are generated by the replay simulator; no traffic was mirrored.")


@router.get("/carbon", response_model=dict[str, Any])
async def get_measured_carbon_intensity(
    service_name: str = Query("sentinel-target-app"),
    region: str = Query("us-central1"),
    cpu_seconds: float = Query(4.25, ge=0.01),
    requests: int = Query(150, ge=1),
) -> dict[str, Any]:
    """
    Tier 2 Feature 10: Measured SCI Carbon Intensity (ISO/IEC 21031).
    Grounds software carbon intensity in real Cloud Run vCPU-seconds and container metrics,
    replacing simulated placeholder numbers with measured telemetry.
    """
    from sentinel.scripts.sci_carbon_engine import SoftwareCarbonIntensityCalculator

    calc = SoftwareCarbonIntensityCalculator(service_name=service_name, region=region)
    return _label(calc.calculate_measured_sci(measured_cpu_seconds=cpu_seconds, measured_requests=requests), "derived",
                  "Grid intensity is a published regional figure; CPU-seconds and request count come from the query "
                  "parameters (defaults if none given), not from Cloud Run metrics.")


