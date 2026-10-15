from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.jobqueue import default_queue
from app.models.job import JobType
from app.models.project import Project
from app.schemas.build import BuildRequest
from app.services import apk_service

router = APIRouter(prefix="/api/projects", tags=["builds"])


@router.post("/{project_id}/build")
def trigger_build(project_id: str, body: BuildRequest, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    job_id = default_queue.enqueue(JobType.BUILD_PIPELINE, project_id, body.model_dump())
    return {"job_id": job_id}


@router.get("/{project_id}/compare")
def get_comparison(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    report_path = apk_service.project_root(project_id) / "reports" / "comparison.json"
    if not report_path.exists():
        raise HTTPException(404, "No comparison yet; run a build first")
    return json.loads(report_path.read_text())


@router.get("/{project_id}/download")
def download_signed_apk(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    signed_apk = apk_service.project_root(project_id) / "signed" / "signed.apk"
    if not signed_apk.exists():
        raise HTTPException(404, "No signed APK yet; run a build first")
    return FileResponse(signed_apk, filename=f"{project.name}-signed.apk")
