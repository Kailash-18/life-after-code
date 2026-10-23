"""
Project Sentinel — State Management & S3 Remote Storage Routes
Exposes endpoints for point-in-time state snapshotting, S3 cryptographic verification,
historical snapshot exploration, and state restoration.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.routes.events import require_ci_signature
from app.s3_state_store import s3_state_store
from app.state_engine import INCIDENTS_STORE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/state", tags=["State Storage"])


class StateSnapshotRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata tags for snapshot")


class StateRestoreRequest(BaseModel):
    snapshot_id: str = Field(..., description="Unique snapshot ID to restore (e.g. snap-20261020-abcd1234)")


class StateRollbackRequest(BaseModel):
    snapshot_id: str | None = Field(default=None, description="Target S3 snapshot ID. If omitted, uses latest verified snapshot.")
    service_name: str = Field(default="sentinel-target-app", description="Service name to rollback traffic for")
    dry_run: bool = Field(default=False, description="Simulate rollback without cloud mutation")


@router.post("/snapshot", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_ci_signature)])
async def create_state_snapshot(req: StateSnapshotRequest | None = None) -> dict[str, Any]:
    """
    Triggers an immediate cryptographic state snapshot.
    Persists incident history and recovery attempts to AWS S3 with KMS encryption.
    """
    meta = req.metadata if req else {}
    summary = s3_state_store.snapshot_state(INCIDENTS_STORE, extra_metadata=meta)
    return {
        "status": "CREATED",
        "snapshot": summary,
    }


@router.get("/snapshots")
async def list_state_snapshots(limit: int = 20) -> dict[str, Any]:
    """
    Lists historical state snapshots stored in S3 / persistent state cache.
    """
    snapshots = s3_state_store.list_snapshots(limit=limit)
    return {
        "total": len(snapshots),
        "snapshots": snapshots,
    }


@router.post("/restore", dependencies=[Depends(require_ci_signature)])
async def restore_state_snapshot(req: StateRestoreRequest) -> dict[str, Any]:
    """
    Atomically restores Sentinel incident state from an authoritative S3 snapshot
    after verifying the SHA-256 integrity hash.
    """
    res = s3_state_store.restore_snapshot(req.snapshot_id, INCIDENTS_STORE)
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "RESTORE_FAILED",
                    "message": res.get("error", "Failed to restore snapshot"),
                    "retryable": False,
                }
            },
        )
    return res


@router.post("/rollback", dependencies=[Depends(require_ci_signature)])
async def rollback_state_snapshot(req: StateRollbackRequest | None = None) -> dict[str, Any]:
    """
    Executes an authoritative rollback using a cryptographically verified S3 state snapshot.
    Atomically restores incident state, diverts 100% traffic back to the known-good release,
    and returns comprehensive verification metadata.
    """
    request_data = req or StateRollbackRequest()
    snapshot_id = request_data.snapshot_id
    if not snapshot_id:
        snapshots = s3_state_store.list_snapshots(limit=1)
        if not snapshots:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "NO_SNAPSHOTS_AVAILABLE",
                        "message": "No S3 state snapshots found to rollback to.",
                    }
                },
            )
        snapshot_id = snapshots[0]["snapshot_id"]

    res = s3_state_store.restore_snapshot(snapshot_id, INCIDENTS_STORE)
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "ROLLBACK_FAILED",
                    "message": res.get("error", "Failed to restore snapshot"),
                    "retryable": False,
                }
            },
        )

    # Report only what actually happened: no assumed revision, traffic split or success.
    traffic_shift: dict[str, Any] = {"attempted": True, "ok": False}
    try:
        from sentinel.scripts.rollback import execute_rollback

        rb_res = execute_rollback(
            service_name=request_data.service_name,
            stable_url=os.getenv("SENTINEL_STABLE_URL", "http://localhost:8080"),
            s3_snapshot_id=snapshot_id,
            dry_run=request_data.dry_run,
            emit_to_backend=False,
        )
        shift = rb_res.get("traffic_res") or {}
        # Only a real gcloud traffic update plus a passing probe counts; "simulation" and
        # "fallback_local" modes did not move any traffic.
        traffic_shift = {
            "attempted": True,
            "ok": bool(shift.get("success")) and shift.get("mode") == "gcloud" and rb_res.get("post_rollback_probe_ok") is True,
            "mode": shift.get("mode"),
            "restored_revision": rb_res.get("restored_revision"),
            "post_rollback_probe_ok": rb_res.get("post_rollback_probe_ok"),
        }
    except Exception as e:  # noqa: BLE001 - surface the failure instead of hiding it
        logger.warning("Rollback traffic shift attempt encountered error: %s", e)
        traffic_shift = {"attempted": True, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}

    return {
        "status": "SUCCESS" if traffic_shift["ok"] else "STATE_RESTORED_TRAFFIC_NOT_SHIFTED",
        "action": "ROLLBACK_TO_S3_SNAPSHOT",
        "snapshot_id": snapshot_id,
        "dry_run": request_data.dry_run,
        "restored_incidents": res.get("restored_incidents_count", 0),
        "sha256": res.get("sha256"),
        "snapshot_integrity_verified": True,
        "traffic_shift": traffic_shift,
        "storage": s3_state_store.get_storage_status(),
    }


@router.get("/storage")
async def get_storage_health() -> dict[str, Any]:
    """
    Returns S3 remote state backend connectivity, KMS encryption configuration,
    DynamoDB distributed lock table status, and storage metrics.
    """
    return s3_state_store.get_storage_status()
