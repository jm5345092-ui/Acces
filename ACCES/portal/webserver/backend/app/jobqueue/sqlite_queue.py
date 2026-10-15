from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterator

import redis

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobqueue.base import JobQueue
from app.models.job import Job, JobStatus

settings = get_settings()


class SqliteJobQueue(JobQueue):
    """SQLite-backed job table + Redis pub/sub for real-time log streaming.

    Deliberately simple (short-poll claim, append-only log file per job) —
    this is the piece designed to be swapped for Celery/RQ+Redis-as-broker
    without touching callers, once throughput actually needs it.
    """

    def __init__(self) -> None:
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    def _log_path(self, job_id: str) -> Path:
        path = settings.projects_root.parent / "job_logs" / f"{job_id}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def enqueue(self, job_type: str, project_id: str | None, payload: dict[str, Any]) -> str:
        db = SessionLocal()
        try:
            job = Job(
                project_id=project_id,
                type=job_type,
                status=JobStatus.QUEUED,
                payload_json=json.dumps(payload),
                log_path=str(self._log_path("placeholder")),
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            job.log_path = str(self._log_path(job.id))
            db.commit()
            self._redis.publish(f"job:{job.id}", json.dumps({"event": "queued"}))
            return job.id
        finally:
            db.close()

    def get_status(self, job_id: str) -> dict[str, Any] | None:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if not job:
                return None
            return {
                "id": job.id,
                "project_id": job.project_id,
                "type": job.type,
                "status": job.status,
                "progress": job.progress,
                "result": json.loads(job.result_json or "{}"),
            }
        finally:
            db.close()

    def append_log(self, job_id: str, line: str) -> None:
        with open(self._log_path(job_id), "a", encoding="utf-8") as fh:
            fh.write(line.rstrip("\n") + "\n")
        self._redis.publish(f"job:{job_id}", json.dumps({"event": "log", "line": line}))

    def stream_log(self, job_id: str) -> Iterator[str]:
        pubsub = self._redis.pubsub()
        pubsub.subscribe(f"job:{job_id}")
        log_path = self._log_path(job_id)
        if log_path.exists():
            with open(log_path, encoding="utf-8") as fh:
                for existing_line in fh:
                    yield existing_line.rstrip("\n")
        try:
            for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = json.loads(message["data"])
                if data["event"] == "log":
                    yield data["line"]
                elif data["event"] in ("completed", "failed"):
                    yield f"[job {data['event']}]"
                    break
        finally:
            pubsub.close()

    def claim_next(self) -> dict[str, Any] | None:
        db = SessionLocal()
        try:
            job = (
                db.query(Job)
                .filter(Job.status == JobStatus.QUEUED)
                .order_by(Job.created_at.asc())
                .first()
            )
            if not job:
                return None
            job.status = JobStatus.RUNNING
            db.commit()
            return {
                "id": job.id,
                "project_id": job.project_id,
                "type": job.type,
                "payload": json.loads(job.payload_json or "{}"),
            }
        finally:
            db.close()

    def set_progress(self, job_id: str, progress: int) -> None:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job:
                job.progress = progress
                db.commit()
        finally:
            db.close()

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job:
                job.status = JobStatus.SUCCESS
                job.progress = 100
                job.result_json = json.dumps(result)
                db.commit()
            self._redis.publish(f"job:{job_id}", json.dumps({"event": "completed"}))
        finally:
            db.close()

    def fail(self, job_id: str, error: str) -> None:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.result_json = json.dumps({"error": error})
                db.commit()
            self._redis.publish(f"job:{job_id}", json.dumps({"event": "failed", "error": error}))
        finally:
            db.close()

    def poll_loop_sleep(self) -> None:
        time.sleep(0.5)
