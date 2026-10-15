from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.jobqueue import default_queue
from app.models.job import JobType
from app.models.project import Project
from app.services import apk_service

router = APIRouter(prefix="/api/projects", tags=["analysis"])


@router.post("/{project_id}/analysis/run")
def run_analysis(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    job_id = default_queue.enqueue(JobType.ANALYZE, project_id, {})
    return {"job_id": job_id}


@router.get("/{project_id}/analysis")
def get_analysis(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    report_path = apk_service.project_root(project_id) / "reports" / "analysis.json"
    if not report_path.exists():
        raise HTTPException(404, "No analysis yet; POST /analysis/run first")
    return json.loads(report_path.read_text())
