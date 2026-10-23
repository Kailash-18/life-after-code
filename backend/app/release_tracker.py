"""
Release / deployment / health bookkeeping (feeds GET /api/v1/status and /releases).

Every value written here comes from a CI event (authoritative sources per §A5):
- traffic split: deploy events carrying revision + traffic_percent
- health numbers: evaluator.verdict events with measured values
- release known-good: evaluator PASS at 100% traffic
Nothing is invented: if a measurement is absent, nothing is recorded.
"""

from datetime import UTC, datetime
from typing import Any

from app.models.entities import (
    Deployment,
    DeploymentStage,
    DeploymentVerdict,
    HealthSample,
    Release,
    ReleaseStatus,
)
from app.persistence.factory import get_repository

RELEASE_EVENT_TYPES = {
    "pipeline.started",
    "deploy.canary_started",
    "evaluator.verdict",
    "rollback.completed",
    "redeploy.completed",
    "recovery.verified",
}


def release_id_for(event: dict[str, Any]) -> str | None:
    if event.get("release_id"):
        return event["release_id"]
    sha = event.get("commit_sha")
    return f"rel-{sha[:12]}" if sha else None


def _stage_for(traffic_percent: int) -> DeploymentStage:
    if traffic_percent >= 100:
        return DeploymentStage.PROD_100
    if traffic_percent > 10:
        return DeploymentStage.CANARY_50
    return DeploymentStage.CANARY_10


def _upsert_release(event: dict[str, Any], rel_id: str, status: ReleaseStatus | None) -> Release:
    repo = get_repository()
    data = event.get("data") or {}
    rel = repo.get_release(rel_id)
    if rel is None:
        rel = Release(
            id=rel_id,
            commit_sha=event.get("commit_sha", ""),
            version=str(data.get("version") or event.get("commit_sha", "")[:7] or "unknown"),
            image_digest=data.get("image_digest"),
            revision_name=data.get("revision_name"),
            pipeline_id=str(event.get("pipeline_id", "")),
            status=status or ReleaseStatus.DEPLOYING,
            known_good=False,
        )
    else:
        if data.get("revision_name"):
            rel.revision_name = data["revision_name"]
        if data.get("image_digest"):
            rel.image_digest = data["image_digest"]
        if status is not None:
            rel.status = status
    repo.save_release(rel)
    return rel


def _latest_deployment(rel_id: str) -> Deployment | None:
    deps = get_repository().list_deployments_for_release(rel_id)
    return deps[0] if deps else None


def process_release_event(event: dict[str, Any]) -> None:
    """Apply a CI event to release/deployment/health records. Never raises for unknown types."""
    etype = event.get("type")
    if etype not in RELEASE_EVENT_TYPES:
        return
    rel_id = release_id_for(event)
    if not rel_id:
        return
    repo = get_repository()
    data = event.get("data") or {}
    now = datetime.now(UTC).isoformat()

    if etype == "pipeline.started":
        _upsert_release(event, rel_id, None)
        return

    if etype in ("deploy.canary_started", "redeploy.completed"):
        _upsert_release(event, rel_id, ReleaseStatus.CANARY)
        pct = data.get("traffic_percent")
        if isinstance(pct, int):
            repo.save_deployment(
                Deployment(
                    id=f"dep-{event.get('job_id')}-{pct}",
                    release_id=rel_id,
                    stage=_stage_for(pct),
                    traffic_percent=pct,
                    started_at=now,
                )
            )
        return

    if etype in ("evaluator.verdict", "recovery.verified"):
        verdict = str(data.get("verdict", "")).upper()
        if verdict not in ("PASS", "FAIL"):
            return
        rel = _upsert_release(event, rel_id, None)
        pct = data.get("traffic_percent")
        dep = _latest_deployment(rel_id)
        if dep is None or (isinstance(pct, int) and dep.traffic_percent != pct):
            if not isinstance(pct, int):
                pct = dep.traffic_percent if dep else 0
            dep = Deployment(
                id=f"dep-{event.get('job_id')}-{pct}",
                release_id=rel_id,
                stage=_stage_for(pct),
                traffic_percent=pct,
                started_at=now,
            )
        target = data.get("target") or "candidate"
        if target == "candidate":
            dep.verdict = DeploymentVerdict.PASS if verdict == "PASS" else DeploymentVerdict.FAIL
            dep.evaluator_job_id = str(event.get("job_id"))
            dep.ended_at = now
        repo.save_deployment(dep)

        if isinstance(data.get("error_rate"), (int, float)) and isinstance(
            data.get("p95_ms"), (int, float)
        ):
            repo.save_health_sample(
                HealthSample(
                    id=f"hs-{event.get('job_id')}-{target}-{dep.traffic_percent}",
                    deployment_id=dep.id,
                    target=target if target in ("candidate", "stable") else "candidate",
                    error_rate=float(data["error_rate"]),
                    p95_ms=float(data["p95_ms"]),
                    health_ok=verdict == "PASS",
                    sample_size=int(data.get("sample_size") or 0),
                    measured_at=now,
                )
            )

        if target == "candidate":
            if verdict == "FAIL":
                rel.status = ReleaseStatus.FAILED
                repo.save_release(rel)
            elif dep.traffic_percent >= 100:
                rel.status = ReleaseStatus.STABLE
                rel.known_good = True
                repo.save_release(rel)
        return

    if etype == "rollback.completed" and data.get("post_rollback_probe_ok") is True:
        rel = repo.get_release(rel_id)
        if rel is not None and rel.status != ReleaseStatus.STABLE:
            rel.status = ReleaseStatus.ROLLED_BACK
            repo.save_release(rel)
