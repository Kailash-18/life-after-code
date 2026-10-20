"""
Project Sentinel — State Management & S3 Remote Storage Routes
Exposes endpoints for point-in-time state snapshotting, S3 cryptographic verification,
historical snapshot exploration, and state restoration.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.s3_state_store import s3_state_store
from app.state_engine import INCIDENTS_STORE

router = APIRouter(prefix="/api/v1/state", tags=["State Storage"])


class StateSnapshotRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata tags for snapshot")


class StateRestoreRequest(BaseModel):
    snapshot_id: str = Field(..., description="Unique snapshot ID to restore (e.g. snap-20261020-abcd1234)")


@router.post("/snapshot", status_code=status.HTTP_201_CREATED)
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


@router.post("/restore")
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


@router.get("/storage")
async def get_storage_health() -> dict[str, Any]:
    """
    Returns S3 remote state backend connectivity, KMS encryption configuration,
    DynamoDB distributed lock table status, and storage metrics.
    """
    return s3_state_store.get_storage_status()
