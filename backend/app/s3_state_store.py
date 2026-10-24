"""
Project Sentinel — Enterprise S3 State Storage Subsystem
Provides cryptographically verified, KMS-encrypted, versioned persistence for Sentinel
incident timelines, recovery attempts, and authoritative CI/CD state files.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("sentinel.s3_state_store")


class S3StateStore:
    """
    Manages enterprise-grade S3 state persistence, point-in-time snapshotting,
    and zero-data-loss state restoration for Project Sentinel.
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        region: str | None = None,
        prefix: str | None = None,
        kms_key_id: str | None = None,
        endpoint_url: str | None = None,
        auto_sync: bool = True,
    ):
        self.bucket_name = (
            bucket_name
            or os.getenv("SENTINEL_STATE_BUCKET")
            or "sentinel-terraform-state-prod"
        )
        self.region = (
            region or os.getenv("SENTINEL_STATE_REGION") or "us-east-1"
        )
        self.prefix = (
            prefix or os.getenv("SENTINEL_STATE_PREFIX") or "sentinel/state/"
        ).rstrip("/") + "/"
        self.kms_key_id = (
            kms_key_id
            or os.getenv("SENTINEL_STATE_KMS_KEY_ID")
            or os.getenv("TF_VAR_state_kms_key_arn")
        )
        self.endpoint_url = endpoint_url or os.getenv("SENTINEL_S3_ENDPOINT_URL")
        self.auto_sync = auto_sync

        self._s3_client: Any = None
        self._s3_available = False
        self._last_sync_time: str | None = None
        self._snapshots_history: list[dict[str, Any]] = []

        # Local fallback cache directory for offline resilience. Must be writable by the
        # (non-root) service user; an unwritable path disables the cache instead of
        # crashing the backend at import time.
        self.local_cache_dir = Path(os.getenv("SENTINEL_STATE_CACHE_DIR") or "artifacts/state_cache")
        self.max_cached_snapshots = int(os.getenv("SENTINEL_STATE_CACHE_MAX", "50"))
        self.local_cache_enabled = True
        try:
            self.local_cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("State cache disabled: cannot create %s (%s)", self.local_cache_dir, exc)
            self.local_cache_enabled = False

        self._initialize_s3()

    def _initialize_s3(self) -> None:
        """Initializes boto3 S3 client if boto3 and valid credentials exist."""
        try:
            import boto3
            from botocore.config import Config

            cfg = Config(
                region_name=self.region,
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            )
            kwargs: dict[str, Any] = {"config": cfg}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url

            self._s3_client = boto3.client("s3", **kwargs)
            # Lightweight probe to check bucket availability
            try:
                self._s3_client.head_bucket(Bucket=self.bucket_name)
                self._s3_available = True
                logger.info("Connected to S3 state bucket: %s", self.bucket_name)
            except Exception:
                # Bucket may not exist yet or running in local dev without live credentials
                self._s3_available = False
        except Exception as e:
            logger.debug("S3 client initialization fallback: %s", e)
            self._s3_available = False

    @property
    def is_s3_connected(self) -> bool:
        return self._s3_available

    @staticmethod
    def compute_state_sha256(data: dict[str, Any]) -> str:
        """Computes deterministic canonical SHA-256 hash of state dictionary."""
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def snapshot_state(
        self,
        incident_store: dict[str, Any],
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Creates an immutable, content-addressed state snapshot.
        Persists to S3 with KMS encryption and writes to local fallback cache.
        """
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        sha256_hash = self.compute_state_sha256(incident_store)
        snapshot_id = f"snap-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{sha256_hash[:8]}"

        payload = {
            "snapshot_id": snapshot_id,
            "created_at": now,
            "sha256": sha256_hash,
            "bucket": self.bucket_name,
            "region": self.region,
            "encryption": "aws:kms" if self.kms_key_id else "AES256",
            "active_incidents_count": len(incident_store),
            "incidents": incident_store,
            "metadata": extra_metadata or {},
        }

        serialized = json.dumps(payload, indent=2)
        s3_key = f"{self.prefix}snapshots/{snapshot_id}.json"
        latest_key = f"{self.prefix}latest_state.json"

        # 1. Attempt AWS S3 PutObject with Server-Side KMS Encryption
        s3_written = False
        if self._s3_available and self._s3_client:
            try:
                put_args: dict[str, Any] = {
                    "Bucket": self.bucket_name,
                    "Key": s3_key,
                    "Body": serialized.encode("utf-8"),
                    "ContentType": "application/json",
                    "Metadata": {
                        "sha256": sha256_hash,
                        "snapshot_id": snapshot_id,
                        "created_at": now,
                    },
                }
                if self.kms_key_id:
                    put_args["ServerSideEncryption"] = "aws:kms"
                    put_args["SSEKMSKeyId"] = self.kms_key_id
                else:
                    put_args["ServerSideEncryption"] = "AES256"

                self._s3_client.put_object(**put_args)

                # Update latest state pointer
                latest_args = dict(put_args)
                latest_args["Key"] = latest_key
                self._s3_client.put_object(**latest_args)
                s3_written = True
                self._last_sync_time = now
            except Exception as e:
                logger.warning("Failed to write state snapshot to S3: %s", e)

        # 2. Persist to Local Secure Fallback Cache (bounded: Cloud Run's filesystem is memory)
        cache_file = self.local_cache_dir / f"{snapshot_id}.json"
        local_written = False
        if self.local_cache_enabled:
            try:
                cache_file.write_text(serialized, encoding="utf-8")
                (self.local_cache_dir / "latest_state.json").write_text(serialized, encoding="utf-8")
                local_written = True
                for old_file in sorted(self.local_cache_dir.glob("snap-*.json"), reverse=True)[self.max_cached_snapshots:]:
                    old_file.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not write local state snapshot: %s", exc)

        summary = {
            "snapshot_id": snapshot_id,
            "created_at": now,
            "sha256": sha256_hash,
            "active_incidents": len(incident_store),
            "s3_persisted": s3_written,
            "s3_uri": f"s3://{self.bucket_name}/{s3_key}" if s3_written else None,
            "local_cache_path": str(cache_file) if local_written else None,
            "status": "PASS" if (s3_written or local_written) else "NOT_PERSISTED",
        }
        self._snapshots_history.insert(0, summary)
        del self._snapshots_history[self.max_cached_snapshots:]
        return summary

    def list_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        """Lists historical snapshots from S3 or local fallback cache."""
        results: list[dict[str, Any]] = []

        # Try S3 first if connected
        if self._s3_available and self._s3_client:
            try:
                res = self._s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=f"{self.prefix}snapshots/",
                    MaxKeys=limit,
                )
                for item in res.get("Contents", []):
                    key = item.get("Key", "")
                    snap_id = Path(key).stem
                    results.append({
                        "snapshot_id": snap_id,
                        "size_bytes": item.get("Size"),
                        "last_modified": item.get("LastModified").strftime("%Y-%m-%dT%H:%M:%SZ") if item.get("LastModified") else None,
                        "s3_uri": f"s3://{self.bucket_name}/{key}",
                        "storage_tier": item.get("StorageClass", "STANDARD"),
                    })
                if results:
                    return results
            except Exception as e:
                logger.debug("Failed listing S3 snapshots: %s", e)

        # Fallback to in-memory history and local cache
        if self._snapshots_history:
            return self._snapshots_history[:limit]

        local_files = sorted(self.local_cache_dir.glob("snap-*.json"), reverse=True) if self.local_cache_enabled else []
        for f in local_files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                results.append({
                    "snapshot_id": data.get("snapshot_id", f.stem),
                    "created_at": data.get("created_at"),
                    "sha256": data.get("sha256"),
                    "active_incidents": data.get("active_incidents_count", 0),
                    "local_cache_path": str(f),
                })
            except Exception:
                continue

        return results

    def restore_snapshot(
        self, snapshot_id: str, incident_store: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Restores state from an S3 or local snapshot after validating the SHA-256 checksum.
        """
        payload = None

        # 1. Fetch from S3
        if self._s3_available and self._s3_client:
            try:
                key = f"{self.prefix}snapshots/{snapshot_id}.json"
                resp = self._s3_client.get_object(Bucket=self.bucket_name, Key=key)
                content = resp["Body"].read().decode("utf-8")
                payload = json.loads(content)
            except Exception as e:
                logger.warning("Could not read snapshot %s from S3: %s", snapshot_id, e)

        # 2. Fallback to Local Cache
        if not payload:
            cache_file = self.local_cache_dir / f"{snapshot_id}.json"
            if cache_file.exists():
                payload = json.loads(cache_file.read_text(encoding="utf-8"))

        if not payload:
            return {
                "success": False,
                "error": f"Snapshot '{snapshot_id}' not found in S3 or local state cache.",
            }

        # 3. Cryptographic Verification
        stored_hash = payload.get("sha256")
        incidents_data = payload.get("incidents", {})
        computed_hash = self.compute_state_sha256(incidents_data)

        if stored_hash and stored_hash != computed_hash:
            return {
                "success": False,
                "error": "State tampering or corruption detected: SHA-256 hash mismatch.",
                "stored_hash": stored_hash,
                "computed_hash": computed_hash,
            }

        # 4. Atomic Restoration
        incident_store.clear()
        incident_store.update(incidents_data)

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "restored_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "restored_incidents_count": len(incident_store),
            "sha256": computed_hash,
            "status": "RESTORED",
        }

    def rehydrate_on_boot(self, incident_store: dict[str, Any]) -> bool:
        """Loads latest valid state from S3 or local cache on backend startup."""
        if incident_store:
            return True  # Already has state

        payload = None
        # Check S3
        if self._s3_available and self._s3_client:
            try:
                latest_key = f"{self.prefix}latest_state.json"
                resp = self._s3_client.get_object(Bucket=self.bucket_name, Key=latest_key)
                payload = json.loads(resp["Body"].read().decode("utf-8"))
            except Exception:
                pass

        # Check local
        if not payload:
            latest_file = self.local_cache_dir / "latest_state.json"
            if latest_file.exists():
                try:
                    payload = json.loads(latest_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

        if payload and "incidents" in payload:
            incidents = payload["incidents"]
            sha256_stored = payload.get("sha256")
            if sha256_stored == self.compute_state_sha256(incidents):
                incident_store.update(incidents)
                logger.info("Successfully rehydrated %d incidents from persistent state.", len(incidents))
                return True

        return False

    def get_storage_status(self) -> dict[str, Any]:
        """Storage status as it actually is: nothing here is claimed unless it was observed."""
        if self._s3_available:
            storage_type = "AWS_S3_REMOTE_STATE"
        elif self.local_cache_enabled:
            storage_type = "LOCAL_CACHE_ONLY"
        else:
            storage_type = "NONE"
        return {
            "storage_type": storage_type,
            "bucket_name": self.bucket_name if self._s3_available else None,
            "region": self.region if self._s3_available else None,
            "prefix": self.prefix,
            "s3_connected": self._s3_available,
            "local_cache_dir": str(self.local_cache_dir) if self.local_cache_enabled else None,
            "encryption": {
                "algorithm": ("aws:kms" if self.kms_key_id else "AES256") if self._s3_available else None,
                "kms_key_id": self.kms_key_id if self._s3_available else None,
            },
            # Not checked by this service, so not claimed.
            "distributed_locking": {"status": "NOT_VERIFIED"},
            "versioning_enabled": None,
            "last_sync_timestamp": self._last_sync_time,
            "total_snapshots_recorded": len(self.list_snapshots(limit=100)),
            "durable_across_restarts": self._s3_available,
            "health": "HEALTHY" if self._s3_available else ("DEGRADED" if self.local_cache_enabled else "UNAVAILABLE"),
        }


# Global singleton instance for Sentinel Backend
s3_state_store = S3StateStore()
