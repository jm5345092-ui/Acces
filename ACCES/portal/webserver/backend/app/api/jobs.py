from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.jobqueue import default_queue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job(job_id: str):
    status = default_queue.get_status(job_id)
    if not status:
        raise HTTPException(404, "Job not found")
    return status


@router.get("/{job_id}/stream")
def stream_job_log(job_id: str):
    if not default_queue.get_status(job_id):
        raise HTTPException(404, "Job not found")

    def event_stream():
        for line in default_queue.stream_log(job_id):
            yield f"data: {line}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
