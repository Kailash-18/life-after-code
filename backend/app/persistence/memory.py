"""
In-Memory implementation of SentinelRepository.
Fast, thread-safe test double and ephemeral storage adapter.
"""

import threading

from app.models.entities import (
    Analysis,
    Deployment,
    EventRecord,
    GateResult,
    HealthSample,
    Incident,
    IncidentStatus,
    RecoveryAttempt,
    Release,
    ReleaseStatus,
    TestResult,
)
from app.persistence.base import SentinelRepository


class InMemorySentinelRepository(SentinelRepository):
    """
    Thread-safe in-memory repository implementing SentinelRepository.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.releases: dict[str, Release] = {}
        self.deployments: dict[str, Deployment] = {}
        self.health_samples: list[HealthSample] = []
        self.incidents: dict[str, Incident] = {}
        self.events: list[EventRecord] = []
        self.idempotency_keys: set[str] = set()

    # Releases
    def save_release(self, release: Release) -> Release:
        with self._lock:
            self.releases[release.id] = release.model_copy(deep=True)
            return release

    def get_release(self, release_id: str) -> Release | None:
        with self._lock:
            rel = self.releases.get(release_id)
            return rel.model_copy(deep=True) if rel else None

    def list_releases(
        self, limit: int = 20, status: str | None = None
    ) -> list[Release]:
        with self._lock:
            rels = list(self.releases.values())
            if status:
                rels = [r for r in rels if r.status.value == status]
            rels.sort(key=lambda r: r.created_at, reverse=True)
            return [r.model_copy(deep=True) for r in rels[:limit]]

    def get_active_stable_release(self) -> Release | None:
        with self._lock:
            stables = [
                r for r in self.releases.values() if r.status == ReleaseStatus.STABLE
            ]
            if not stables:
                return None
            stables.sort(key=lambda r: r.created_at, reverse=True)
            return stables[0].model_copy(deep=True)

    # Deployments & Health
    def save_deployment(self, deployment: Deployment) -> Deployment:
        with self._lock:
            self.deployments[deployment.id] = deployment.model_copy(deep=True)
            return deployment

    def get_deployment(self, deployment_id: str) -> Deployment | None:
        with self._lock:
            dep = self.deployments.get(deployment_id)
            return dep.model_copy(deep=True) if dep else None

    def list_deployments_for_release(self, release_id: str) -> list[Deployment]:
        with self._lock:
            deps = [
                d for d in self.deployments.values() if d.release_id == release_id
            ]
            deps.sort(key=lambda d: d.started_at, reverse=True)
            return [d.model_copy(deep=True) for d in deps]

    def save_health_sample(self, sample: HealthSample) -> HealthSample:
        with self._lock:
            self.health_samples.append(sample.model_copy(deep=True))
            return sample

    def get_latest_health_sample(
        self, deployment_id: str | None = None
    ) -> HealthSample | None:
        with self._lock:
            samples = self.health_samples
            if deployment_id:
                samples = [s for s in samples if s.deployment_id == deployment_id]
            if not samples:
                return None
            samples.sort(key=lambda s: s.measured_at, reverse=True)
            return samples[0].model_copy(deep=True)

    # Incidents & Recovery
    def save_incident(self, incident: Incident) -> Incident:
        with self._lock:
            self.incidents[incident.id] = incident.model_copy(deep=True)
            return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._lock:
            inc = self.incidents.get(incident_id)
            return inc.model_copy(deep=True) if inc else None

    def list_incidents(self, status: str | None = None) -> list[Incident]:
        with self._lock:
            incs = list(self.incidents.values())
            if status:
                incs = [i for i in incs if i.status.value == status]
            incs.sort(key=lambda i: i.detected_at, reverse=True)
            return [i.model_copy(deep=True) for i in incs]

    def update_incident_status(
        self, incident_id: str, new_status: IncidentStatus
    ) -> Incident | None:
        with self._lock:
            inc = self.incidents.get(incident_id)
            if not inc:
                return None
            inc.status = new_status
            if inc.recovery_attempts:
                inc.recovery_attempts[-1].state = new_status.value
            return inc.model_copy(deep=True)

    def add_recovery_attempt(
        self, incident_id: str, attempt: RecoveryAttempt
    ) -> RecoveryAttempt:
        with self._lock:
            inc = self.incidents.get(incident_id)
            if inc:
                inc.recovery_attempts.append(attempt.model_copy(deep=True))
            return attempt

    def add_test_result(
        self, incident_id: str, attempt_id: str, test_result: TestResult
    ) -> None:
        with self._lock:
            inc = self.incidents.get(incident_id)
            if inc:
                for att in inc.recovery_attempts:
                    if att.id == attempt_id:
                        att.test_results.append(test_result.model_copy(deep=True))
                        break

    def add_gate_result(
        self, incident_id: str, attempt_id: str, gate_result: GateResult
    ) -> None:
        with self._lock:
            inc = self.incidents.get(incident_id)
            if inc:
                for att in inc.recovery_attempts:
                    if att.id == attempt_id:
                        att.gate_results.append(gate_result.model_copy(deep=True))
                        break

    def set_attempt_analysis(
        self, incident_id: str, attempt_id: str, analysis: Analysis
    ) -> None:
        with self._lock:
            inc = self.incidents.get(incident_id)
            if inc:
                for att in inc.recovery_attempts:
                    if att.id == attempt_id:
                        att.analysis = analysis.model_copy(deep=True)
                        break

    # Events & Timeline
    def save_event(self, event: EventRecord) -> EventRecord:
        with self._lock:
            self.events.append(event.model_copy(deep=True))
            return event

    def list_events_for_incident(self, incident_id: str) -> list[EventRecord]:
        with self._lock:
            matching = [
                e
                for e in self.events
                if e.entity_id == incident_id
                or e.data.get("incident_id") == incident_id
            ]
            matching.sort(key=lambda e: e.at)
            return [e.model_copy(deep=True) for e in matching]

    # Idempotency
    def check_and_set_idempotency(self, key: str) -> bool:
        with self._lock:
            if key in self.idempotency_keys:
                return False
            self.idempotency_keys.add(key)
            return True

    def clear(self) -> None:
        with self._lock:
            self.releases.clear()
            self.deployments.clear()
            self.health_samples.clear()
            self.incidents.clear()
            self.events.clear()
            self.idempotency_keys.clear()
