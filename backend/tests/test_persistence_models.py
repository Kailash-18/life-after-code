"""
Unit Tests for Task R2: Domain Entities and Data Models.
Tests all 9 entities from Section A7 of SENTINEL_AGENT_CONTEXT_Krishna.md and docs/contracts/openapi.yaml.
"""

from app.models.entities import (
    Analysis,
    Deployment,
    DeploymentStage,
    DeploymentVerdict,
    EventRecord,
    GateKind,
    GateResult,
    GateVerdict,
    HealthSample,
    Incident,
    IncidentStatus,
    RecoveryAttempt,
    RecoveryState,
    Release,
    ReleaseStatus,
    TestKind,
    TestOutcome,
    TestResult,
)


def test_release_model():
    rel = Release(
        id="rel-20261018-01",
        commit_sha="c9aaa1f",
        version="1.0.0",
        image_digest="sha256:123456",
        revision_name="target-app-00001",
        pipeline_id="1001",
        status=ReleaseStatus.STABLE,
        known_good=True,
    )
    assert rel.id == "rel-20261018-01"
    assert rel.status == ReleaseStatus.STABLE
    assert rel.known_good is True
    assert rel.created_at is not None

    dumped = rel.model_dump()
    assert dumped["status"] == "STABLE"
    loaded = Release.model_validate(dumped)
    assert loaded == rel


def test_deployment_model():
    dep = Deployment(
        id="dep-101",
        release_id="rel-01",
        stage=DeploymentStage.CANARY_10,
        traffic_percent=10,
        verdict=DeploymentVerdict.IN_PROGRESS,
        evaluator_job_id="job-99",
    )
    assert dep.id == "dep-101"
    assert dep.stage == DeploymentStage.CANARY_10
    assert dep.traffic_percent == 10
    assert dep.ended_at is None


def test_health_sample_model():
    sample = HealthSample(
        id="smp-01",
        deployment_id="dep-101",
        target="candidate",
        error_rate=0.08,
        p95_ms=185.5,
        health_ok=False,
        sample_size=500,
    )
    assert sample.target == "candidate"
    assert sample.error_rate == 0.08
    assert sample.health_ok is False


def test_analysis_model():
    analysis = Analysis(
        attempt_id="att-01",
        facts=["Observed 8% error rate on candidate"],
        hypotheses=["ZeroDivisionError in calculate_discount"],
        missing_evidence=["DB connection pool metrics"],
        suspected_change="app/routes/orders.py:45",
        file_ref="sentinel/incidents/inc-01/analysis.json",
    )
    assert len(analysis.facts) == 1
    assert "calculate_discount" in analysis.hypotheses[0]
    assert analysis.suspected_change == "app/routes/orders.py:45"


def test_test_result_model():
    tr = TestResult(
        id="tst-01",
        attempt_id="att-01",
        kind=TestKind.REGRESSION_ON_BROKEN,
        sha="broken-sha-123",
        outcome=TestOutcome.FAILED,
        failure_type="AssertionError",
        junit_ref="https://gitlab.com/artifacts/junit.xml",
    )
    assert tr.kind == TestKind.REGRESSION_ON_BROKEN
    assert tr.outcome == TestOutcome.FAILED
    assert tr.failure_type == "AssertionError"


def test_gate_result_model():
    gr = GateResult(
        id="gte-01",
        attempt_id="att-01",
        gate=GateKind.INTEGRITY,
        verdict=GateVerdict.PASS,
        findings=[],
        report_ref="https://gitlab.com/artifacts/integrity.json",
    )
    assert gr.gate == GateKind.INTEGRITY
    assert gr.verdict == GateVerdict.PASS
    assert len(gr.findings) == 0


def test_recovery_attempt_and_incident_aggregation():
    att = RecoveryAttempt(
        id="att-01",
        incident_id="inc-01",
        attempt_no=1,
        state=RecoveryState.INVESTIGATING,
        flow_session_id="duo-flow-99",
        mr_iid=42,
        fix_sha="fix-sha-abc",
    )
    incident = Incident(
        id="inc-01",
        release_id="rel-02",
        status=IncidentStatus.INVESTIGATING,
        breached_thresholds=["error_rate > 0.02 (observed 0.08)"],
        evidence_bundle_ref="https://gitlab.com/artifacts/bundle.tar.gz",
        evidence_sha256="abcdef123456",
        recovery_attempts=[att],
    )

    assert incident.id == "inc-01"
    assert incident.status == IncidentStatus.INVESTIGATING
    assert len(incident.recovery_attempts) == 1
    assert incident.recovery_attempts[0].flow_session_id == "duo-flow-99"


def test_event_record_model():
    evt = EventRecord(
        id="evt-001",
        entity_type="Incident",
        entity_id="inc-01",
        type="incident.detected",
        source="sentinel/scripts/evaluator.py",
        source_job_id="job-888",
        data={"breached": True},
        summary="Error rate exceeded",
    )
    assert evt.id == "evt-001"
    assert evt.entity_type == "Incident"
    assert evt.type == "incident.detected"
    assert evt.data["breached"] is True
