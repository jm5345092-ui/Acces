"""Job queue abstraction.

The API process only ever talks to this interface — never to Android
tooling directly. Today it's backed by a SQLite `jobs` table (polled by the
worker) plus Redis pub/sub for live log fan-out to SSE clients. Swapping to
Celery/RQ later means writing a new class against this same interface;
nothing in api/ or services/ has to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator


class JobQueue(ABC):
    @abstractmethod
    def enqueue(self, job_type: str, project_id: str | None, payload: dict[str, Any]) -> str:
        """Create a QUEUED job row and return its id."""

    @abstractmethod
    def get_status(self, job_id: str) -> dict[str, Any] | None:
        """Return the current status/progress/result for a job."""

    @abstractmethod
    def append_log(self, job_id: str, line: str) -> None:
        """Append a log line and publish it to any live subscribers."""

    @abstractmethod
    def stream_log(self, job_id: str) -> Iterator[str]:
        """Yield log lines as they arrive (blocking generator), for SSE."""

    @abstractmethod
    def claim_next(self) -> dict[str, Any] | None:
        """Worker-side: atomically claim the oldest QUEUED job, mark RUNNING."""

    @abstractmethod
    def set_progress(self, job_id: str, progress: int) -> None: ...

    @abstractmethod
    def complete(self, job_id: str, result: dict[str, Any]) -> None: ...

    @abstractmethod
    def fail(self, job_id: str, error: str) -> None: ...
