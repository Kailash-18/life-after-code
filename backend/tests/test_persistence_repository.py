"""
Unit and Integration Tests for Task R2: Repository Layer and Persistence.
Tests SQLite and In-Memory repositories, CRUD operations, nested aggregates,
chronological timeline ordering, idempotency, and persistence across simulated restarts.
"""

import concurrent.futures
from pathlib import Path

import pytest
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
from app.persistence.memory import InMemorySentinelRepository
from app.persistence.sqlite import SqliteSentinelRepository


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path: Path):
    """Parametrized fixture providing both in-memory and SQLite repository instances."""
    if request.param == "memory":
        return InMemorySentinelRepository()
    else:
        db_path = str(tmp_path / "test_repo.db")
        return SqliteSentinelRepository(db_path=db_path)


def test_releases_crud(repo):
    rel1 = Release(
        id="rel-01",
        commit_sha="c9aaa1f",
        version="1.0.0",
        pipeline_id="101",
        status=ReleaseStatus.STABLE,
        known_good=True,
    )
    rel2 = Release(
        id="rel-02",
        commit_sha="d67851a",
        version="1.1.0-canary",
        pipeline_id="102",
        status=ReleaseStatus.CANARY,
        known_good=False,
    )

    repo.save_release(rel1)
    repo.save_release(rel2)

    # Get by ID
    fetched1 = repo.get_release("rel-01")
    assert fetched1 is not None
    assert fetched1.version == "1.0.0"
    assert fetched1.known_good is True

    # List all
    all_rels = repo.list_releases()
    assert len(all_rels) == 2

    # Filter by status
    canaries = repo.list_releases(status="CANARY")
    assert len(canaries) == 1
    assert canaries[0].id == "rel-02"

    # Get active stable
    active_stable = repo.get_active_stable_release()
    assert active_stable is not None
    assert active_stable.id == "rel-01"


def test_deployments_and_health_samples(repo):
    rel = Release(
        id="rel-deploy-01",
        commit_sha="abc1234",
        version="2.0.0",
        pipeline_id="201",
        status=ReleaseStatus.CANARY,
    )
    repo.save_release(rel)

    dep = Deployment(
        id="dep-201",
        release_id="rel-deploy-01",
        stage=DeploymentStage.CANARY_10,
        traffic_percent=10,
        verdict=DeploymentVerdict.IN_PROGRESS,
    )
    repo.save_deployment(dep)

    fetched_dep = repo.get_deployment("dep-201")
    assert fetched_dep is not None
    assert fetched_dep.traffic_percent == 10

    # Save health samples
    smp1 = HealthSample(
        id="smp-01",
        deployment_id="dep-201",
        target="candidate",
        error_rate=0.01,
        p95_ms=45.0,
        health_ok=True,
        sample_size=200,
        measured_at="2026-10-18T10:00:00Z",
    )
    smp2 = HealthSample(
        id="smp-02",
        deployment_id="dep-201",
        target="candidate",
        error_rate=0.07,
        p95_ms=190.0,
        health_ok=False,
        sample_size=500,
        measured_at="2026-10-18T10:05:00Z",
    )
    repo.save_health_sample(smp1)
    repo.save_health_sample(smp2)

    latest = repo.get_latest_health_sample("dep-201")
    assert latest is not None
    assert latest.id == "smp-02"
    assert latest.health_ok is False


def test_incident_lifecycle_and_aggregates(repo):
    inc = Incident(
        id="inc-test-01",
        release_id="rel-deploy-01",
        status=IncidentStatus.DETECTED,
        breached_thresholds=["error_rate > 0.02 (observed 0.07)"],
        evidence_bundle_ref="https://gitlab.com/artifacts/bundle.tar.gz",
        evidence_sha256="sha-12345",
        recovery_attempts=[
            RecoveryAttempt(
                id="att-test-01",
                incident_id="inc-test-01",
                attempt_no=1,
                state=RecoveryState.DETECTED,
            )
        ],
    )
    repo.save_incident(inc)

    # 1. Verify retrieval
    stored = repo.get_incident("inc-test-01")
    assert stored is not None
    assert stored.status == IncidentStatus.DETECTED
    assert len(stored.recovery_attempts) == 1
    assert "error_rate > 0.02" in stored.breached_thresholds[0]

    # 2. Add test results and gate results to attempt
    test_res = TestResult(
        id="tst-01",
        attempt_id="att-test-01",
        kind=TestKind.REGRESSION_ON_BROKEN,
        sha="broken-sha",
        outcome=TestOutcome.FAILED,
        failure_type="AssertionError",
    )
    gate_res = GateResult(
        id="gte-01",
        attempt_id="att-test-01",
        gate=GateKind.INTEGRITY,
        verdict=GateVerdict.PASS,
        findings=[],
    )
    analysis = Analysis(
        attempt_id="att-test-01",
        facts=["Spike in 500 responses"],
        hypotheses=["ZeroDivisionError in discount calculation"],
        missing_evidence=[],
        suspected_change="app/routes/orders.py:45",
    )

    repo.add_test_result("inc-test-01", "att-test-01", test_res)
    repo.add_gate_result("inc-test-01", "att-test-01", gate_res)
    repo.set_attempt_analysis("inc-test-01", "att-test-01", analysis)

    # 3. Transition status
    repo.update_incident_status("inc-test-01", IncidentStatus.VERIFYING)

    updated = repo.get_incident("inc-test-01")
    assert updated.status == IncidentStatus.VERIFYING
    assert len(updated.recovery_attempts) == 1
    att = updated.recovery_attempts[0]
    assert len(att.test_results) == 1
    assert att.test_results[0].failure_type == "AssertionError"
    assert len(att.gate_results) == 1
    assert att.gate_results[0].verdict == GateVerdict.PASS
    assert att.analysis is not None
    assert "ZeroDivisionError" in att.analysis.hypotheses[0]


def test_chronological_timeline_ordering(repo):
    inc_id = "inc-timeline-order"

    e1 = EventRecord(
        id="evt-3",
        entity_id=inc_id,
        type="flow.started",
        source="sentinel/dispatcher",
        source_job_id="303",
        at="2026-10-18T12:05:00Z",
    )
    e2 = EventRecord(
        id="evt-1",
        entity_id=inc_id,
        type="incident.detected",
        source="sentinel/evaluator",
        source_job_id="301",
        at="2026-10-18T12:00:00Z",
    )
    e3 = EventRecord(
        id="evt-2",
        entity_id=inc_id,
        type="rollback.completed",
        source="sentinel/ci/rollback",
        source_job_id="302",
        at="2026-10-18T12:02:00Z",
    )

    # Insert out of order
    repo.save_event(e1)
    repo.save_event(e2)
    repo.save_event(e3)

    timeline = repo.list_events_for_incident(inc_id)
    assert len(timeline) == 3
    # Must be ordered strictly by timestamp ascending
    assert timeline[0].type == "incident.detected"
    assert timeline[1].type == "rollback.completed"
    assert timeline[2].type == "flow.started"


def test_idempotency_atomicity(repo):
    key = "job-404:incident.detected"

    # First time -> fresh (True)
    assert repo.check_and_set_idempotency(key) is True

    # Duplicate -> rejected (False)
    assert repo.check_and_set_idempotency(key) is False

    # Different key -> fresh (True)
    assert repo.check_and_set_idempotency("job-405:incident.detected") is True


def test_sqlite_persistence_across_restarts(tmp_path: Path):
    """
    CRITICAL TEST FOR TASK R2:
    Proves that data written by one process/instance survives application shutdown
    and is accurately reloaded by a completely new instance from the persistent SQLite database.
    """
    db_file = str(tmp_path / "persistent_sentinel.db")

    # Instance 1: Startup, write entities, and close
    repo1 = SqliteSentinelRepository(db_path=db_file)
    rel = Release(
        id="rel-restart-01",
        commit_sha="c9aaa1f",
        version="1.0.0",
        pipeline_id="901",
        status=ReleaseStatus.STABLE,
        known_good=True,
    )
    repo1.save_release(rel)

    inc = Incident(
        id="inc-restart-01",
        release_id="rel-restart-01",
        status=IncidentStatus.INVESTIGATING,
        breached_thresholds=["error_rate > 0.05"],
        recovery_attempts=[
            RecoveryAttempt(
                id="att-restart-01",
                incident_id="inc-restart-01",
                attempt_no=1,
                state=RecoveryState.INVESTIGATING,
                flow_session_id="duo-restart-sess",
            )
        ],
    )
    repo1.save_incident(inc)

    repo1.save_event(
        EventRecord(
            id="evt-restart-01",
            entity_id="inc-restart-01",
            type="incident.detected",
            source="sentinel/evaluator",
            source_job_id="job-901",
            at="2026-10-18T15:00:00Z",
        )
    )

    # Simulate shutdown
    del repo1

    # Instance 2: Cold startup, read back from disk
    repo2 = SqliteSentinelRepository(db_path=db_file)

    loaded_rel = repo2.get_release("rel-restart-01")
    assert loaded_rel is not None
    assert loaded_rel.version == "1.0.0"
    assert loaded_rel.known_good is True

    loaded_inc = repo2.get_incident("inc-restart-01")
    assert loaded_inc is not None
    assert loaded_inc.status == IncidentStatus.INVESTIGATING
    assert len(loaded_inc.recovery_attempts) == 1
    assert loaded_inc.recovery_attempts[0].flow_session_id == "duo-restart-sess"

    timeline = repo2.list_events_for_incident("inc-restart-01")
    assert len(timeline) == 1
    assert timeline[0].type == "incident.detected"


def test_sqlite_concurrent_writes(tmp_path: Path):
    """Verifies that thread-safe locking in SqliteSentinelRepository handles concurrent writes safely."""
    db_file = str(tmp_path / "concurrent_sentinel.db")
    repo = SqliteSentinelRepository(db_path=db_file)

    def write_worker(worker_id: int):
        for i in range(10):
            repo.save_event(
                EventRecord(
                    id=f"evt-w{worker_id}-{i}",
                    entity_id="inc-concurrent",
                    type="worker.ping",
                    source=f"worker-{worker_id}",
                    source_job_id=str(worker_id * 100 + i),
                    at=f"2026-10-18T16:{worker_id:02d}:{i:02d}Z",
                )
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(write_worker, w) for w in range(5)]
        concurrent.futures.wait(futures)
        for f in futures:
            assert f.exception() is None

    events = repo.list_events_for_incident("inc-concurrent")
    assert len(events) == 50
