from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import ReadOnlyViolationError, safe_filename
from app.jobqueue import default_queue
from app.models.job import JobType
from app.models.project import Project, ProjectStatus
from app.services import apk_service

router = APIRouter(prefix="/api/projects", tags=["uploads"])
settings = get_settings()


@router.post("/{project_id}/upload")
async def upload_apk(project_id: str, file: UploadFile, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if not (file.filename or "").lower().endswith(".apk"):
        raise HTTPException(400, "Only .apk files are accepted")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        metadata = apk_service.save_original_upload(project_id, file.file, max_bytes)
    except ReadOnlyViolationError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(413, str(exc))

    project.original_filename = safe_filename(file.filename or "upload.apk")
    project.sha256 = metadata["sha256"]
    project.sha1 = metadata["sha1"]
    project.size_bytes = metadata["size_bytes"]
    project.status = ProjectStatus.UPLOADED
    db.commit()

    job_id = default_queue.enqueue(JobType.DECODE, project_id, {})

    return {"project_id": project_id, "metadata": metadata, "decode_job_id": job_id}
