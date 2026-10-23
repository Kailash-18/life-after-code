"""
SQLite Implementation of SentinelRepository.
Provides real ACID persistence across application restarts using standard Python sqlite3.
Requires zero external database packages, avoiding unapproved database lock-in.
"""

import json
import sqlite3
import threading

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
from app.persistence.base import SentinelRepository


class SqliteSentinelRepository(SentinelRepository):
    """
    Thread-safe, file-backed or in-memory SQLite implementation of SentinelRepository.
    """

    def __init__(self, db_path: str = "sentinel.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn


    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS releases (
                id TEXT PRIMARY KEY,
                commit_sha TEXT NOT NULL,
                version TEXT NOT NULL,
                image_digest TEXT,
                revision_name TEXT,
                pipeline_id TEXT NOT NULL,
                status TEXT NOT NULL,
                known_good INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deployments (
                id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                traffic_percent INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                verdict TEXT NOT NULL,
                evaluator_job_id TEXT,
                FOREIGN KEY(release_id) REFERENCES releases(id)
            );

            CREATE TABLE IF NOT EXISTS health_samples (
                id TEXT PRIMARY KEY,
                deployment_id TEXT NOT NULL,
                target TEXT NOT NULL,
                error_rate REAL NOT NULL,
                p95_ms REAL NOT NULL,
                health_ok INTEGER NOT NULL,
                sample_size INTEGER NOT NULL,
                measured_at TEXT NOT NULL,
                FOREIGN KEY(deployment_id) REFERENCES deployments(id)
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                breached_thresholds TEXT NOT NULL,
                evidence_bundle_ref TEXT,
                evidence_sha256 TEXT,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recovery_attempts (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                attempt_no INTEGER NOT NULL,
                state TEXT NOT NULL,
                flow_session_id TEXT,
                mr_iid INTEGER,
                fix_sha TEXT,
                failure_reason TEXT,
                deadline_at TEXT,
                FOREIGN KEY(incident_id) REFERENCES incidents(id)
            );

            CREATE TABLE IF NOT EXISTS analyses (
                attempt_id TEXT PRIMARY KEY,
                facts TEXT NOT NULL,
                hypotheses TEXT NOT NULL,
                missing_evidence TEXT NOT NULL,
                suspected_change TEXT,
                file_ref TEXT,
                FOREIGN KEY(attempt_id) REFERENCES recovery_attempts(id)
            );

            CREATE TABLE IF NOT EXISTS test_results (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                sha TEXT NOT NULL,
                outcome TEXT NOT NULL,
                failure_type TEXT,
                junit_ref TEXT,
                FOREIGN KEY(attempt_id) REFERENCES recovery_attempts(id)
            );

            CREATE TABLE IF NOT EXISTS gate_results (
                id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL,
                gate TEXT NOT NULL,
                verdict TEXT NOT NULL,
                findings TEXT NOT NULL,
                report_ref TEXT,
                FOREIGN KEY(attempt_id) REFERENCES recovery_attempts(id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                at TEXT NOT NULL,
                payload_ref TEXT,
                data TEXT NOT NULL,
                artifact_url TEXT,
                summary TEXT
            );

            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_id);
            CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);
            """)

    # -----------------------------------------------------------------------
    # Releases
    # -----------------------------------------------------------------------
    def save_release(self, release: Release) -> Release:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO releases (
                    id, commit_sha, version, image_digest, revision_name,
                    pipeline_id, status, known_good, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release.id,
                    release.commit_sha,
                    release.version,
                    release.image_digest,
                    release.revision_name,
                    release.pipeline_id,
                    release.status.value,
                    1 if release.known_good else 0,
                    release.created_at,
                ),
            )
        return release

    def get_release(self, release_id: str) -> Release | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM releases WHERE id = ?", (release_id,)
            ).fetchone()
            if not row:
                return None
            return Release(
                id=row["id"],
                commit_sha=row["commit_sha"],
                version=row["version"],
                image_digest=row["image_digest"],
                revision_name=row["revision_name"],
                pipeline_id=row["pipeline_id"],
                status=ReleaseStatus(row["status"]),
                known_good=bool(row["known_good"]),
                created_at=row["created_at"],
            )

    def list_releases(
        self, limit: int = 20, status: str | None = None
    ) -> list[Release]:
        with self._lock, self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM releases WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM releases ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                Release(
                    id=r["id"],
                    commit_sha=r["commit_sha"],
                    version=r["version"],
                    image_digest=r["image_digest"],
                    revision_name=r["revision_name"],
                    pipeline_id=r["pipeline_id"],
                    status=ReleaseStatus(r["status"]),
                    known_good=bool(r["known_good"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def get_active_stable_release(self) -> Release | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM releases WHERE status = ? ORDER BY created_at DESC LIMIT 1",
                (ReleaseStatus.STABLE.value,),
            ).fetchone()
            if not row:
                return None
            return Release(
                id=row["id"],
                commit_sha=row["commit_sha"],
                version=row["version"],
                image_digest=row["image_digest"],
                revision_name=row["revision_name"],
                pipeline_id=row["pipeline_id"],
                status=ReleaseStatus(row["status"]),
                known_good=bool(row["known_good"]),
                created_at=row["created_at"],
            )

    # -----------------------------------------------------------------------
    # Deployments & Health
    # -----------------------------------------------------------------------
    def save_deployment(self, deployment: Deployment) -> Deployment:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO deployments (
                    id, release_id, stage, traffic_percent, started_at,
                    ended_at, verdict, evaluator_job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deployment.id,
                    deployment.release_id,
                    deployment.stage.value,
                    deployment.traffic_percent,
                    deployment.started_at,
                    deployment.ended_at,
                    deployment.verdict.value,
                    deployment.evaluator_job_id,
                ),
            )
        return deployment

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM deployments WHERE id = ?", (deployment_id,)
            ).fetchone()
            if not row:
                return None
            return Deployment(
                id=row["id"],
                release_id=row["release_id"],
                stage=DeploymentStage(row["stage"]),
                traffic_percent=row["traffic_percent"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                verdict=DeploymentVerdict(row["verdict"]),
                evaluator_job_id=row["evaluator_job_id"],
            )

    def list_deployments_for_release(self, release_id: str) -> list[Deployment]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM deployments WHERE release_id = ? ORDER BY started_at DESC",
                (release_id,),
            ).fetchall()
            return [
                Deployment(
                    id=r["id"],
                    release_id=r["release_id"],
                    stage=DeploymentStage(r["stage"]),
                    traffic_percent=r["traffic_percent"],
                    started_at=r["started_at"],
                    ended_at=r["ended_at"],
                    verdict=DeploymentVerdict(r["verdict"]),
                    evaluator_job_id=r["evaluator_job_id"],
                )
                for r in rows
            ]

    def save_health_sample(self, sample: HealthSample) -> HealthSample:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO health_samples (
                    id, deployment_id, target, error_rate, p95_ms,
                    health_ok, sample_size, measured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample.id,
                    sample.deployment_id,
                    sample.target,
                    sample.error_rate,
                    sample.p95_ms,
                    1 if sample.health_ok else 0,
                    sample.sample_size,
                    sample.measured_at,
                ),
            )
        return sample

    def get_latest_health_sample(
        self, deployment_id: str | None = None
    ) -> HealthSample | None:
        with self._lock, self._get_connection() as conn:
            if deployment_id:
                row = conn.execute(
                    "SELECT * FROM health_samples WHERE deployment_id = ? ORDER BY measured_at DESC LIMIT 1",
                    (deployment_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM health_samples ORDER BY measured_at DESC LIMIT 1"
                ).fetchone()
            if not row:
                return None
            return HealthSample(
                id=row["id"],
                deployment_id=row["deployment_id"],
                target=row["target"],
                error_rate=row["error_rate"],
                p95_ms=row["p95_ms"],
                health_ok=bool(row["health_ok"]),
                sample_size=row["sample_size"],
                measured_at=row["measured_at"],
            )

    # -----------------------------------------------------------------------
    # Incidents & Recovery
    # -----------------------------------------------------------------------
    def save_incident(self, incident: Incident) -> Incident:
        with self._lock, self._get_connection() as conn:
            thresholds_json = json.dumps(incident.breached_thresholds)
            conn.execute(
                """
                INSERT OR REPLACE INTO incidents (
                    id, release_id, detected_at, breached_thresholds,
                    evidence_bundle_ref, evidence_sha256, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.id,
                    incident.release_id,
                    incident.detected_at,
                    thresholds_json,
                    incident.evidence_bundle_ref,
                    incident.evidence_sha256,
                    incident.status.value,
                ),
            )

            # Persist recovery attempts
            for att in incident.recovery_attempts:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO recovery_attempts (
                        id, incident_id, attempt_no, state,
                        flow_session_id, mr_iid, fix_sha, failure_reason, deadline_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        att.id,
                        att.incident_id,
                        att.attempt_no,
                        att.state.value,
                        att.flow_session_id,
                        att.mr_iid,
                        att.fix_sha,
                        att.failure_reason,
                        att.deadline_at,
                    ),
                )
                if att.analysis:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO analyses (
                            attempt_id, facts, hypotheses, missing_evidence, suspected_change, file_ref
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            att.analysis.attempt_id,
                            json.dumps(att.analysis.facts),
                            json.dumps(att.analysis.hypotheses),
                            json.dumps(att.analysis.missing_evidence),
                            att.analysis.suspected_change,
                            att.analysis.file_ref,
                        ),
                    )
                for tr in att.test_results:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO test_results (
                            id, attempt_id, kind, sha, outcome, failure_type, junit_ref
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tr.id,
                            tr.attempt_id,
                            tr.kind.value,
                            tr.sha,
                            tr.outcome.value,
                            tr.failure_type,
                            tr.junit_ref,
                        ),
                    )
                for gr in att.gate_results:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO gate_results (
                            id, attempt_id, gate, verdict, findings, report_ref
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            gr.id,
                            gr.attempt_id,
                            gr.gate.value,
                            gr.verdict.value,
                            json.dumps(gr.findings),
                            gr.report_ref,
                        ),
                    )
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            if not row:
                return None

            thresholds = json.loads(row["breached_thresholds"])

            # Load recovery attempts
            attempt_rows = conn.execute(
                "SELECT * FROM recovery_attempts WHERE incident_id = ? ORDER BY attempt_no ASC",
                (incident_id,),
            ).fetchall()

            attempts = []
            for att_row in attempt_rows:
                att_id = att_row["id"]
                # Analysis
                ana_row = conn.execute(
                    "SELECT * FROM analyses WHERE attempt_id = ?", (att_id,)
                ).fetchone()
                analysis = None
                if ana_row:
                    analysis = Analysis(
                        attempt_id=ana_row["attempt_id"],
                        facts=json.loads(ana_row["facts"]),
                        hypotheses=json.loads(ana_row["hypotheses"]),
                        missing_evidence=json.loads(ana_row["missing_evidence"]),
                        suspected_change=ana_row["suspected_change"],
                        file_ref=ana_row["file_ref"],
                    )

                # Test results
                tr_rows = conn.execute(
                    "SELECT * FROM test_results WHERE attempt_id = ?", (att_id,)
                ).fetchall()
                test_results = [
                    TestResult(
                        id=tr["id"],
                        attempt_id=tr["attempt_id"],
                        kind=TestKind(tr["kind"]),
                        sha=tr["sha"],
                        outcome=TestOutcome(tr["outcome"]),
                        failure_type=tr["failure_type"],
                        junit_ref=tr["junit_ref"],
                    )
                    for tr in tr_rows
                ]

                # Gate results
                gr_rows = conn.execute(
                    "SELECT * FROM gate_results WHERE attempt_id = ?", (att_id,)
                ).fetchall()
                gate_results = [
                    GateResult(
                        id=gr["id"],
                        attempt_id=gr["attempt_id"],
                        gate=GateKind(gr["gate"]),
                        verdict=GateVerdict(gr["verdict"]),
                        findings=json.loads(gr["findings"]),
                        report_ref=gr["report_ref"],
                    )
                    for gr in gr_rows
                ]

                attempts.append(
                    RecoveryAttempt(
                        id=att_row["id"],
                        incident_id=att_row["incident_id"],
                        attempt_no=att_row["attempt_no"],
                        state=RecoveryState(att_row["state"]),
                        flow_session_id=att_row["flow_session_id"],
                        mr_iid=att_row["mr_iid"],
                        fix_sha=att_row["fix_sha"],
                        failure_reason=att_row["failure_reason"],
                        deadline_at=att_row["deadline_at"],
                        analysis=analysis,
                        test_results=test_results,
                        gate_results=gate_results,
                    )
                )

            return Incident(
                id=row["id"],
                release_id=row["release_id"],
                detected_at=row["detected_at"],
                breached_thresholds=thresholds,
                evidence_bundle_ref=row["evidence_bundle_ref"],
                evidence_sha256=row["evidence_sha256"],
                status=IncidentStatus(row["status"]),
                recovery_attempts=attempts,
            )

    def list_incidents(self, status: str | None = None) -> list[Incident]:
        with self._lock, self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT id FROM incidents WHERE status = ? ORDER BY detected_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM incidents ORDER BY detected_at DESC"
                ).fetchall()

        incidents = []
        for r in rows:
            inc = self.get_incident(r["id"])
            if inc:
                incidents.append(inc)
        return incidents

    def update_incident_status(
        self, incident_id: str, new_status: IncidentStatus
    ) -> Incident | None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE incidents SET status = ? WHERE id = ?",
                (new_status.value, incident_id),
            )
            # Update latest attempt state as well
            conn.execute(
                """
                UPDATE recovery_attempts
                SET state = ?
                WHERE incident_id = ?
                  AND attempt_no = (SELECT MAX(attempt_no) FROM recovery_attempts WHERE incident_id = ?)
                """,
                (
                    (
                        new_status.value
                        if new_status.value in RecoveryState._value2member_map_
                        else RecoveryState.FAILED.value
                    ),
                    incident_id,
                    incident_id,
                ),
            )
        return self.get_incident(incident_id)

    def add_recovery_attempt(
        self, incident_id: str, attempt: RecoveryAttempt
    ) -> RecoveryAttempt:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO recovery_attempts (
                    id, incident_id, attempt_no, state,
                    flow_session_id, mr_iid, fix_sha, failure_reason, deadline_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.id,
                    incident_id,
                    attempt.attempt_no,
                    attempt.state.value,
                    attempt.flow_session_id,
                    attempt.mr_iid,
                    attempt.fix_sha,
                    attempt.failure_reason,
                    attempt.deadline_at,
                ),
            )
        return attempt

    def add_test_result(
        self, incident_id: str, attempt_id: str, test_result: TestResult
    ) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO test_results (
                    id, attempt_id, kind, sha, outcome, failure_type, junit_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_result.id,
                    attempt_id,
                    test_result.kind.value,
                    test_result.sha,
                    test_result.outcome.value,
                    test_result.failure_type,
                    test_result.junit_ref,
                ),
            )

    def add_gate_result(
        self, incident_id: str, attempt_id: str, gate_result: GateResult
    ) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO gate_results (
                    id, attempt_id, gate, verdict, findings, report_ref
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    gate_result.id,
                    attempt_id,
                    gate_result.gate.value,
                    gate_result.verdict.value,
                    json.dumps(gate_result.findings),
                    gate_result.report_ref,
                ),
            )

    def set_attempt_analysis(
        self, incident_id: str, attempt_id: str, analysis: Analysis
    ) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analyses (
                    attempt_id, facts, hypotheses, missing_evidence, suspected_change, file_ref
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    json.dumps(analysis.facts),
                    json.dumps(analysis.hypotheses),
                    json.dumps(analysis.missing_evidence),
                    analysis.suspected_change,
                    analysis.file_ref,
                ),
            )

    # -----------------------------------------------------------------------
    # Events & Timeline
    # -----------------------------------------------------------------------
    def save_event(self, event: EventRecord) -> EventRecord:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    id, entity_type, entity_id, type, source,
                    source_job_id, at, payload_ref, data, artifact_url, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.entity_type,
                    event.entity_id,
                    event.type,
                    event.source,
                    event.source_job_id,
                    event.at,
                    event.payload_ref,
                    json.dumps(event.data),
                    event.artifact_url,
                    event.summary,
                ),
            )
        return event

    def list_events_for_incident(self, incident_id: str) -> list[EventRecord]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE entity_id = ?
                   OR json_extract(data, '$.incident_id') = ?
                ORDER BY at ASC
                """,
                (incident_id, incident_id),
            ).fetchall()

            return [
                EventRecord(
                    id=r["id"],
                    entity_type=r["entity_type"],
                    entity_id=r["entity_id"],
                    type=r["type"],
                    source=r["source"],
                    source_job_id=r["source_job_id"],
                    at=r["at"],
                    payload_ref=r["payload_ref"],
                    data=json.loads(r["data"]),
                    artifact_url=r["artifact_url"],
                    summary=r["summary"],
                )
                for r in rows
            ]

    # -----------------------------------------------------------------------
    # Idempotency
    # -----------------------------------------------------------------------
    def check_and_set_idempotency(self, key: str) -> bool:
        """
        Returns True if key was inserted (fresh), False if it already existed.
        Atomically prevents duplicate event processing.
        """
        with self._lock, self._get_connection() as conn:
            try:
                from datetime import UTC, datetime

                conn.execute(
                    "INSERT INTO idempotency_keys (key, created_at) VALUES (?, ?)",
                    (key, datetime.now(UTC).isoformat()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def release_idempotency(self, key: str) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))

    def clear(self) -> None:
        """Clean all tables for testing isolation."""
        with self._lock, self._get_connection() as conn:
            conn.execute("DELETE FROM analyses;")
            conn.execute("DELETE FROM gate_results;")
            conn.execute("DELETE FROM test_results;")
            conn.execute("DELETE FROM recovery_attempts;")
            conn.execute("DELETE FROM incidents;")
            conn.execute("DELETE FROM health_samples;")
            conn.execute("DELETE FROM deployments;")
            conn.execute("DELETE FROM releases;")
            conn.execute("DELETE FROM events;")
            conn.execute("DELETE FROM idempotency_keys;")

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()

