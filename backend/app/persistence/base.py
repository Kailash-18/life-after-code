"""
Abstract Repository Interface for Project Sentinel Persistence.
Defines storage contracts for Releases, Deployments, Incidents, Events, and Idempotency.
Database-independent: can be implemented by SQLite, Firestore, PostgreSQL, or In-Memory.
"""

from abc import ABC, abstractmethod

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
    TestResult,
)


class SentinelRepository(ABC):
    """Abstract storage interface for all Sentinel entities."""

    # -----------------------------------------------------------------------
    # Releases
    # -----------------------------------------------------------------------
    @abstractmethod
    def save_release(self, release: Release) -> Release:
        """Persist or update a release."""

    @abstractmethod
    def get_release(self, release_id: str) -> Release | None:
        """Fetch a release by ID."""

    @abstractmethod
    def list_releases(
        self, limit: int = 20, status: str | None = None
    ) -> list[Release]:
        """List releases ordered by creation time descending."""

    @abstractmethod
    def get_active_stable_release(self) -> Release | None:
        """Get the current active known-good or stable release."""

    # -----------------------------------------------------------------------
    # Deployments & Health
    # -----------------------------------------------------------------------
    @abstractmethod
    def save_deployment(self, deployment: Deployment) -> Deployment:
        """Persist or update a deployment record."""

    @abstractmethod
    def get_deployment(self, deployment_id: str) -> Deployment | None:
        """Fetch deployment by ID."""

    @abstractmethod
    def list_deployments_for_release(self, release_id: str) -> list[Deployment]:
        """List deployments for a specific release."""

    @abstractmethod
    def save_health_sample(self, sample: HealthSample) -> HealthSample:
        """Record a health sample for a deployment."""

    @abstractmethod
    def get_latest_health_sample(
        self, deployment_id: str | None = None
    ) -> HealthSample | None:
        """Get latest recorded health sample."""

    # -----------------------------------------------------------------------
    # Incidents & Recovery
    # -----------------------------------------------------------------------
    @abstractmethod
    def save_incident(self, incident: Incident) -> Incident:
        """Persist or update an incident."""

    @abstractmethod
    def get_incident(self, incident_id: str) -> Incident | None:
        """Fetch incident by ID with its recovery attempts."""

    @abstractmethod
    def list_incidents(self, status: str | None = None) -> list[Incident]:
        """List incidents with optional status filter."""

    @abstractmethod
    def update_incident_status(
        self, incident_id: str, new_status: IncidentStatus
    ) -> Incident | None:
        """Atomically transition incident status."""

    @abstractmethod
    def add_recovery_attempt(
        self, incident_id: str, attempt: RecoveryAttempt
    ) -> RecoveryAttempt:
        """Add a new recovery attempt to an incident."""

    @abstractmethod
    def add_test_result(
        self, incident_id: str, attempt_id: str, test_result: TestResult
    ) -> None:
        """Attach a test result to a recovery attempt."""

    @abstractmethod
    def add_gate_result(
        self, incident_id: str, attempt_id: str, gate_result: GateResult
    ) -> None:
        """Attach a gate verification result to a recovery attempt."""

    @abstractmethod
    def set_attempt_analysis(
        self, incident_id: str, attempt_id: str, analysis: Analysis
    ) -> None:
        """Attach AI analysis to a recovery attempt."""

    # -----------------------------------------------------------------------
    # Events & Timeline
    # -----------------------------------------------------------------------
    @abstractmethod
    def save_event(self, event: EventRecord) -> EventRecord:
        """Persist an ingested event into the chronological event ledger."""

    @abstractmethod
    def list_events_for_incident(self, incident_id: str) -> list[EventRecord]:
        """Fetch strictly chronological events related to an incident."""

    # -----------------------------------------------------------------------
    # Idempotency & Safety
    # -----------------------------------------------------------------------
    @abstractmethod
    def check_and_set_idempotency(self, key: str) -> bool:
        """
        Check if an idempotency key exists; if not, store it.
        Returns True if newly recorded (first time), False if already processed (duplicate).
        """

    @abstractmethod
    def link_correlation(self, key: str, incident_id: str) -> None:
        """Map a correlation key (pipeline:<id>, sha:<sha>, alias:<id>) to an incident. First link wins."""

    @abstractmethod
    def resolve_correlation(self, key: str) -> str | None:
        """Return the incident id linked to a correlation key, if any."""

    @abstractmethod
    def release_idempotency(self, key: str) -> None:
        """Forget an idempotency key so a retryable rejection can be retried by CI."""

    @abstractmethod
    def clear(self) -> None:
        """Reset storage (for test suites)."""
