"""
Domain Entities for Project Sentinel.
Defined in Section A7 of SENTINEL_AGENT_CONTEXT_Krishna.md and synchronized with docs/contracts/openapi.yaml.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReleaseStatus(str, Enum):
    DEPLOYING = "DEPLOYING"
    STABLE = "STABLE"
    CANARY = "CANARY"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class DeploymentStage(str, Enum):
    CANARY_10 = "CANARY_10"
    CANARY_50 = "CANARY_50"
    PROD_100 = "PROD_100"
    ROLLBACK = "ROLLBACK"


class DeploymentVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    IN_PROGRESS = "IN_PROGRESS"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    ROLLED_BACK = "ROLLED_BACK"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    INVESTIGATING = "INVESTIGATING"
    REPAIR_PROPOSED = "REPAIR_PROPOSED"
    VERIFYING = "VERIFYING"
    MERGED = "MERGED"
    REDEPLOYING = "REDEPLOYING"
    RECOVERED = "RECOVERED"
    # Terminal failures
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    INVESTIGATION_FAILED = "INVESTIGATION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    REDEPLOY_UNHEALTHY = "REDEPLOY_UNHEALTHY"
    TIMED_OUT = "TIMED_OUT"
    ESCALATED = "ESCALATED"


class RecoveryState(str, Enum):
    DETECTED = "DETECTED"
    ROLLED_BACK = "ROLLED_BACK"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    INVESTIGATING = "INVESTIGATING"
    REPAIR_PROPOSED = "REPAIR_PROPOSED"
    VERIFYING = "VERIFYING"
    MERGED = "MERGED"
    REDEPLOYING = "REDEPLOYING"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"


class TestKind(str, Enum):
    __test__ = False
    REGRESSION_ON_BROKEN = "regression_on_broken"
    REGRESSION_ON_FIX = "regression_on_fix"
    SUITE = "suite"


class TestOutcome(str, Enum):
    __test__ = False
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"



class GateKind(str, Enum):
    INTEGRITY = "integrity"
    SAST = "sast"
    SONAR = "sonar"
    TERRAFORM = "terraform"


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"


# ---------------------------------------------------------------------------
# 1. Release
# ---------------------------------------------------------------------------
class Release(BaseModel):
    id: str
    commit_sha: str
    version: str
    image_digest: str | None = None
    revision_name: str | None = None
    pipeline_id: str
    status: ReleaseStatus = ReleaseStatus.STABLE
    known_good: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# 2. Deployment
# ---------------------------------------------------------------------------
class Deployment(BaseModel):
    id: str
    release_id: str
    stage: DeploymentStage
    traffic_percent: int = Field(ge=0, le=100)
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str | None = None
    verdict: DeploymentVerdict = DeploymentVerdict.IN_PROGRESS
    evaluator_job_id: str | None = None


# ---------------------------------------------------------------------------
# 3. HealthSample
# ---------------------------------------------------------------------------
class HealthSample(BaseModel):
    id: str
    deployment_id: str
    target: str = Field(pattern="^(candidate|stable)$")
    error_rate: float = Field(ge=0.0)
    p95_ms: float = Field(ge=0.0)
    health_ok: bool
    sample_size: int = Field(ge=0)
    measured_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# 6. Analysis
# ---------------------------------------------------------------------------
class Analysis(BaseModel):
    attempt_id: str
    facts: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    suspected_change: str | None = None
    file_ref: str | None = None


# ---------------------------------------------------------------------------
# 7. TestResult
# ---------------------------------------------------------------------------
class TestResult(BaseModel):
    __test__ = False
    id: str
    attempt_id: str
    kind: TestKind
    sha: str
    outcome: TestOutcome
    failure_type: str | None = None
    junit_ref: str | None = None



# ---------------------------------------------------------------------------
# 8. GateResult
# ---------------------------------------------------------------------------
class GateResult(BaseModel):
    id: str
    attempt_id: str
    gate: GateKind
    verdict: GateVerdict
    findings: list[str] = Field(default_factory=list)
    report_ref: str | None = None


# ---------------------------------------------------------------------------
# 5. RecoveryAttempt
# ---------------------------------------------------------------------------
class RecoveryAttempt(BaseModel):
    id: str
    incident_id: str
    attempt_no: int = 1
    state: RecoveryState = RecoveryState.DETECTED
    flow_session_id: str | None = None
    mr_iid: int | None = None
    fix_sha: str | None = None
    failure_reason: str | None = None
    deadline_at: str | None = None
    analysis: Analysis | None = None
    test_results: list[TestResult] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Incident
# ---------------------------------------------------------------------------
class Incident(BaseModel):
    id: str
    release_id: str
    detected_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    breached_thresholds: list[str] = Field(default_factory=list)
    evidence_bundle_ref: str | None = None
    evidence_sha256: str | None = None
    status: IncidentStatus = IncidentStatus.DETECTED
    recovery_attempts: list[RecoveryAttempt] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 9. Event
# ---------------------------------------------------------------------------
class EventRecord(BaseModel):
    id: str
    entity_type: str = "Incident"
    entity_id: str
    type: str
    source: str
    source_job_id: str
    at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload_ref: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    artifact_url: str | None = None
    summary: str | None = None
