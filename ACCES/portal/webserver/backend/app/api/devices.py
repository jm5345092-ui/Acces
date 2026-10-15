from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.jobqueue import default_queue
from app.models.job import JobType
from app.models.project import Project

router = APIRouter(prefix="/api", tags=["devices"])

# ADB only exists in the worker container (the API never runs Android
# tooling directly), so every device operation — even listing devices — is
# a Job the worker executes, polled via GET /api/jobs/{id}. An empty
# device list is the normal, expected state when nothing is attached.


@router.post("/devices/check")
def check_devices():
    job_id = default_queue.enqueue(JobType.DEVICE_LIST, None, {})
    return {"job_id": job_id}


@router.post("/projects/{project_id}/devices/{serial}/install")
def install_on_device(project_id: str, serial: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    job_id = default_queue.enqueue(JobType.DEVICE_INSTALL, project_id, {"serial": serial})
    return {"job_id": job_id}


@router.post("/projects/{project_id}/devices/{serial}/launch")
def launch_on_device(project_id: str, serial: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    job_id = default_queue.enqueue(JobType.DEVICE_LAUNCH, project_id, {"serial": serial})
    return {"job_id": job_id}


@router.post("/projects/{project_id}/devices/{serial}/logcat")
def logcat_from_device(project_id: str, serial: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    job_id = default_queue.enqueue(JobType.DEVICE_LOGCAT, project_id, {"serial": serial})
    return {"job_id": job_id}
