from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import PostObject


QUEUE_VERSION = 1
ACTIVE_STATUSES = {"collecting", "pending", "processing"}


@dataclass(frozen=True)
class QueueJob:
    job_id: int
    received_at: str
    update_type: str
    status: str
    attempts: int
    available_at: float
    last_error: str | None
    published_target_ids: list[int]
    post: PostObject


@dataclass(frozen=True)
class EnqueueResult:
    job_id: int
    action: str
    queue_depth: int

    @property
    def is_duplicate(self) -> bool:
        return self.action == "duplicate"


@dataclass(frozen=True)
class FailureResult:
    status: str
    attempts: int


class PersistentPostQueue:
    """A small, single-process FIFO queue persisted as one JSON file."""

    def __init__(
        self,
        path: Path,
        *,
        max_attempts: int = 3,
        retry_delay_seconds: float = 10.0,
    ) -> None:
        self.path = path
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._lock = asyncio.Lock()
        self._changed = asyncio.Event()

    async def initialize(
        self,
        *,
        collecting_recovery_delay_seconds: float = 0.0,
    ) -> tuple[int, int]:
        """Create the store and recover interrupted/unfinished jobs."""
        async with self._lock:
            data = self._read_data()
            recovered = 0
            for record in data["jobs"]:
                status = record.get("status")
                if status == "processing":
                    record["status"] = "pending"
                    record["available_at"] = 0.0
                    recovered += 1
                elif status == "collecting":
                    record["status"] = "pending"
                    record["available_at"] = time.time() + max(
                        0.0, collecting_recovery_delay_seconds
                    )
                    recovered += 1
            self._write_data(data)
            depth = self._queue_depth(data)
            if depth:
                self._changed.set()
            return recovered, depth

    async def enqueue(
        self,
        post: PostObject,
        *,
        update_type: str,
        collecting: bool = False,
    ) -> EnqueueResult:
        async with self._lock:
            data = self._read_data()
            identity = self._identity(post, update_type)
            existing = self._find_by_identity(data, identity)
            if existing is not None:
                can_resume_collecting = (
                    collecting
                    and existing.get("status") in {"collecting", "pending"}
                    and int(existing.get("attempts", 0)) == 0
                )
                if can_resume_collecting:
                    existing["post"] = post.to_dict()
                    existing["status"] = "collecting"
                    existing["available_at"] = 0.0
                    self._write_data(data)
                    return EnqueueResult(
                        job_id=int(existing["job_id"]),
                        action="updated",
                        queue_depth=self._queue_depth(data),
                    )
                return EnqueueResult(
                    job_id=int(existing["job_id"]),
                    action="duplicate",
                    queue_depth=self._queue_depth(data),
                )

            job_id = int(data["next_job_id"])
            data["next_job_id"] = job_id + 1
            data["jobs"].append(
                {
                    "job_id": job_id,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "update_type": update_type,
                    "status": "collecting" if collecting else "pending",
                    "attempts": 0,
                    "available_at": 0.0,
                    "last_error": None,
                    "published_target_ids": [],
                    "post": post.to_dict(),
                }
            )
            self._write_data(data)
            self._changed.set()
            return EnqueueResult(
                job_id=job_id,
                action="created",
                queue_depth=self._queue_depth(data),
            )

    async def finalize_collecting(
        self,
        post: PostObject,
        *,
        update_type: str,
    ) -> EnqueueResult:
        async with self._lock:
            data = self._read_data()
            identity = self._identity(post, update_type)
            existing = self._find_by_identity(data, identity)
            if existing is None:
                job_id = int(data["next_job_id"])
                data["next_job_id"] = job_id + 1
                data["jobs"].append(
                    {
                        "job_id": job_id,
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "update_type": update_type,
                        "status": "pending",
                        "attempts": 0,
                        "available_at": 0.0,
                        "last_error": None,
                        "published_target_ids": [],
                        "post": post.to_dict(),
                    }
                )
                action = "created"
            elif existing.get("status") == "collecting":
                job_id = int(existing["job_id"])
                existing["post"] = post.to_dict()
                existing["status"] = "pending"
                existing["available_at"] = 0.0
                action = "finalized"
            else:
                return EnqueueResult(
                    job_id=int(existing["job_id"]),
                    action="duplicate",
                    queue_depth=self._queue_depth(data),
                )

            self._write_data(data)
            self._changed.set()
            return EnqueueResult(
                job_id=job_id,
                action=action,
                queue_depth=self._queue_depth(data),
            )

    async def claim_next(self) -> QueueJob | None:
        async with self._lock:
            data = self._read_data()
            now = time.time()
            ordered = sorted(data["jobs"], key=lambda item: int(item["job_id"]))
            for record in ordered:
                status = str(record.get("status", "pending"))
                if status == "failed":
                    continue
                if status in {"collecting", "processing"}:
                    return None
                if status != "pending":
                    continue
                if float(record.get("available_at", 0.0)) > now:
                    return None

                record["status"] = "processing"
                record["attempts"] = int(record.get("attempts", 0)) + 1
                self._write_data(data)
                return self._to_job(record)
            return None

    async def mark_target_published(self, job_id: int, target_channel_id: int) -> None:
        async with self._lock:
            data = self._read_data()
            record = self._find_by_job_id(data, job_id)
            if record is None:
                return
            published = [int(item) for item in record.get("published_target_ids", [])]
            if target_channel_id not in published:
                published.append(target_channel_id)
                record["published_target_ids"] = published
                self._write_data(data)

    async def complete(self, job_id: int) -> int:
        async with self._lock:
            data = self._read_data()
            data["jobs"] = [
                record for record in data["jobs"] if int(record["job_id"]) != job_id
            ]
            self._write_data(data)
            self._changed.set()
            return self._queue_depth(data)

    async def fail(self, job_id: int, error: str) -> FailureResult:
        async with self._lock:
            data = self._read_data()
            record = self._find_by_job_id(data, job_id)
            if record is None:
                return FailureResult(status="missing", attempts=0)

            attempts = int(record.get("attempts", 0))
            record["last_error"] = error[:2000]
            if attempts < self.max_attempts:
                record["status"] = "pending"
                record["available_at"] = time.time() + self.retry_delay_seconds
                status = "pending"
            else:
                record["status"] = "failed"
                record["available_at"] = 0.0
                status = "failed"
            self._write_data(data)
            self._changed.set()
            return FailureResult(status=status, attempts=attempts)

    async def wait_for_change(self, timeout_seconds: float) -> None:
        try:
            await asyncio.wait_for(self._changed.wait(), timeout=max(0.1, timeout_seconds))
        except TimeoutError:
            pass
        finally:
            self._changed.clear()

    def _read_data(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": QUEUE_VERSION, "next_job_id": 1, "jobs": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read post queue file {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise RuntimeError(f"Invalid post queue file structure: {self.path}")
        payload.setdefault("version", QUEUE_VERSION)
        payload.setdefault(
            "next_job_id",
            max((int(item.get("job_id", 0)) for item in payload["jobs"]), default=0) + 1,
        )
        return payload

    def _write_data(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f"{self.path.name}.tmp")
        serialized = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            raise RuntimeError(f"Cannot write post queue file {self.path}: {exc}") from exc

    @staticmethod
    def _identity(post: PostObject, update_type: str) -> tuple[int, str, str]:
        post_identity = post.media_group_id or str(post.message_id)
        return post.source_channel_id, str(post_identity), update_type

    def _find_by_identity(
        self,
        data: dict[str, Any],
        identity: tuple[int, str, str],
    ) -> dict[str, Any] | None:
        for record in data["jobs"]:
            post = PostObject.from_dict(record["post"])
            if self._identity(post, str(record["update_type"])) == identity:
                return record
        return None

    @staticmethod
    def _find_by_job_id(data: dict[str, Any], job_id: int) -> dict[str, Any] | None:
        for record in data["jobs"]:
            if int(record["job_id"]) == job_id:
                return record
        return None

    @staticmethod
    def _queue_depth(data: dict[str, Any]) -> int:
        return sum(1 for item in data["jobs"] if item.get("status") in ACTIVE_STATUSES)

    @staticmethod
    def _to_job(record: dict[str, Any]) -> QueueJob:
        return QueueJob(
            job_id=int(record["job_id"]),
            received_at=str(record["received_at"]),
            update_type=str(record["update_type"]),
            status=str(record["status"]),
            attempts=int(record.get("attempts", 0)),
            available_at=float(record.get("available_at", 0.0)),
            last_error=(
                str(record["last_error"])
                if record.get("last_error") is not None
                else None
            ),
            published_target_ids=[
                int(item) for item in record.get("published_target_ids", [])
            ],
            post=PostObject.from_dict(record["post"]),
        )
