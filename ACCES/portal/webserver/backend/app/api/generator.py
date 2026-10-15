from __future__ import annotations

import re

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import new_project_id, safe_filename
from app.jobqueue import default_queue
from app.models.job import JobType
from app.models.project import Project, ProjectStatus
from app.schemas.project import ProjectOut
from app.services import apk_service, appgen_service, generator_apks

router = APIRouter(prefix="/api/settings/generator-apks", tags=["generator-apks"])
settings = get_settings()

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@router.get("")
def list_apks():
    return generator_apks.list_generator_apks()


@router.post("/create")
async def create_apk(
    name: str = Form(...),
    url: str = Form(...),
    color: str = Form("#FFFFFF"),
    icon: UploadFile = File(...),
):
    """Starts generating a WebView-wrapper APK for `url` — mirrors the
    old PHP tool's build.php form (name/url/color/icon), but queues the
    actual build as a GENERATE_APP job instead of spawning a detached
    process, so it runs here (including on Railway)."""
    name = name.strip()
    if not (2 <= len(name) <= 40):
        raise HTTPException(400, "El nombre debe tener entre 2 y 40 caracteres.")
    if not re.match(r"^https?://", url):
        url = f"https://{url}"
    if not _HEX_COLOR_RE.match(color):
        color = "#FFFFFF"
    if icon.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(400, "El icono debe ser PNG o JPG.")

    icon_bytes = await icon.read()
    if not icon_bytes:
        raise HTTPException(400, "El icono está vacío.")
    icon_ext = (icon.filename or "icon.png").rsplit(".", 1)[-1]

    info = appgen_service.create_job(name, url, color, icon_bytes, icon_ext)
    job_id = default_queue.enqueue(JobType.GENERATE_APP, None, {"slug": info["slug"]})
    return {"slug": info["slug"], "job_id": job_id}


@router.get("/{slug}/icon")
def get_icon(slug: str):
    path = generator_apks.generator_icon_path(slug)
    if not path:
        raise HTTPException(404, "No icon for this app")
    return FileResponse(path)


@router.get("/{slug}/download")
def download_apk(slug: str):
    path = generator_apks.generator_apk_path(slug)
    if not path:
        raise HTTPException(404, "APK not found")
    return FileResponse(path, filename=f"{slug}.apk")


@router.post("/{slug}/import")
def import_apk(slug: str, body: dict = Body(default={}), db: Session = Depends(get_db)):
    """Creates a new APK-Lab project from a generator build without a
    client-side upload round-trip — the file is already on this disk."""
    source = generator_apks.generator_apk_path(slug)
    if not source:
        raise HTTPException(404, "Generator APK not found")

    entries = {e["slug"]: e for e in generator_apks.list_generator_apks()}
    info = entries.get(slug, {})
    name = (body or {}).get("name") or info.get("name") or slug

    project = Project(id=new_project_id(), name=name, status=ProjectStatus.CREATED)
    db.add(project)
    db.commit()
    db.refresh(project)
    apk_service.init_workspace(project.id)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        metadata = apk_service.save_original_from_path(project.id, source, max_bytes)
    except (ValueError, OSError) as exc:
        db.delete(project)
        db.commit()
        raise HTTPException(400, str(exc))

    project.original_filename = safe_filename(f"{slug}.apk")
    project.sha256 = metadata["sha256"]
    project.sha1 = metadata["sha1"]
    project.size_bytes = metadata["size_bytes"]
    project.status = ProjectStatus.UPLOADED
    db.commit()
    db.refresh(project)

    job_id = default_queue.enqueue(JobType.DECODE, project.id, {})

    return {
        "project": ProjectOut.model_validate(project).model_dump(mode="json"),
        "decode_job_id": job_id,
    }
