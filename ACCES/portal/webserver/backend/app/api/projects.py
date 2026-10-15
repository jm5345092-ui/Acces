from __future__ import annotations

import shutil

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import (
    InvalidIdentifierError,
    PathTraversalError,
    new_project_id,
    resolve_safe_path,
    validate_simple_name,
)
from app.models.job import Job
from app.models.project import Project, ProjectStatus
from app.schemas.project import ProjectCreate, ProjectOut
from app.services import apk_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _resolve_in_decoded(project_id: str, subdir: str, path: str):
    if subdir != "decoded":
        raise HTTPException(400, "Only the decoded workspace can be edited")
    root = apk_service.project_root(project_id)
    try:
        return resolve_safe_path(root, subdir, path)
    except PathTraversalError:
        raise HTTPException(400, "Invalid path")


def _is_same_or_inside(candidate, ancestor) -> bool:
    """True if `candidate` is `ancestor` itself or lives anywhere under it —
    used to refuse moving/copying a folder into its own subtree."""
    candidate = candidate.resolve()
    ancestor = ancestor.resolve()
    return candidate == ancestor or ancestor in candidate.parents


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(id=new_project_id(), name=body.name, status=ProjectStatus.CREATED)
    db.add(project)
    db.commit()
    db.refresh(project)
    apk_service.init_workspace(project.id)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("/{project_id}/tree")
def get_tree(project_id: str, subdir: str = "decoded", db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    root = apk_service.project_root(project_id)
    try:
        base = resolve_safe_path(root, subdir)
    except PathTraversalError:
        raise HTTPException(400, "Invalid subdir")
    if not base.exists():
        return {"name": subdir, "type": "directory", "children": []}
    return _build_tree(base, base)


def _build_tree(path, base) -> dict:
    node = {"name": path.name or str(path), "path": str(path.relative_to(base))}
    if path.is_dir():
        node["type"] = "directory"
        node["children"] = sorted(
            (_build_tree(child, base) for child in path.iterdir()),
            key=lambda n: (n["type"] != "directory", n["name"]),
        )
    else:
        node["type"] = "file"
    return node


@router.get("/{project_id}/file")
def read_file(project_id: str, path: str, subdir: str = "decoded", db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    root = apk_service.project_root(project_id)
    try:
        target = resolve_safe_path(root, subdir, path)
    except PathTraversalError:
        raise HTTPException(400, "Invalid path")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    try:
        content = target.read_text()
    except UnicodeDecodeError:
        raise HTTPException(415, "Binary file; cannot display as text")
    return {"path": path, "content": content}


@router.get("/{project_id}/jobs/latest")
def get_latest_job(project_id: str, type: str, db: Session = Depends(get_db)):
    """Lets the UI find the right job_id to poll for a live progress bar
    (decode/analyze/build) without having to be the one that triggered it
    — e.g. decode starts automatically right after upload, before the
    project page has necessarily mounted yet."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    job = (
        db.query(Job)
        .filter(Job.project_id == project_id, Job.type == type)
        .order_by(Job.created_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(404, "No job of that type for this project yet")
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
    }


@router.post("/{project_id}/tree/rename")
def rename_tree_entry(project_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    """Renames a file or folder in place (same parent directory) — the
    file explorer's right-click "Renombrar"."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    path = body.get("path", "")
    new_name = body.get("new_name", "")
    subdir = body.get("subdir", "decoded")
    if not path or path in (".", ""):
        raise HTTPException(400, "Cannot rename the project root")
    try:
        validate_simple_name(new_name)
    except InvalidIdentifierError:
        raise HTTPException(400, "Invalid name — use only letters, numbers, '-', '_' or '.'")
    target = _resolve_in_decoded(project_id, subdir, path)
    if not target.exists():
        raise HTTPException(404, "Not found")
    destination = target.parent / new_name
    if destination.exists():
        raise HTTPException(409, f"Already exists: {new_name}")
    target.rename(destination)
    return {"renamed": True, "name": new_name}


@router.post("/{project_id}/tree/copy")
def copy_tree_entry(project_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    """Copies a file or folder (recursively) into another directory — the
    file explorer's right-click "Copiar" + "Pegar"."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    source_path = body.get("source_path", "")
    dest_dir = body.get("dest_dir", "")
    subdir = body.get("subdir", "decoded")
    if not source_path or source_path in (".", ""):
        raise HTTPException(400, "Invalid source")
    source = _resolve_in_decoded(project_id, subdir, source_path)
    if not source.exists():
        raise HTTPException(404, "Source not found")
    dest_parent = _resolve_in_decoded(project_id, subdir, dest_dir)
    if not dest_parent.exists() or not dest_parent.is_dir():
        raise HTTPException(404, "Destination folder not found")
    destination = dest_parent / source.name
    if source.is_dir() and _is_same_or_inside(dest_parent, source):
        raise HTTPException(400, "Cannot copy a folder into itself")
    if destination.exists():
        raise HTTPException(409, f"Already exists in destination: {source.name}")
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return {"copied": True}


@router.post("/{project_id}/tree/move")
def move_tree_entry(project_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    """Moves a file or folder into another directory — the file explorer's
    right-click "Cortar" + "Pegar"."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    source_path = body.get("source_path", "")
    dest_dir = body.get("dest_dir", "")
    subdir = body.get("subdir", "decoded")
    if not source_path or source_path in (".", ""):
        raise HTTPException(400, "Cannot move the project root")
    source = _resolve_in_decoded(project_id, subdir, source_path)
    if not source.exists():
        raise HTTPException(404, "Source not found")
    dest_parent = _resolve_in_decoded(project_id, subdir, dest_dir)
    if not dest_parent.exists() or not dest_parent.is_dir():
        raise HTTPException(404, "Destination folder not found")
    destination = dest_parent / source.name
    if source.is_dir() and _is_same_or_inside(dest_parent, source):
        raise HTTPException(400, "Cannot move a folder into itself")
    if destination == source:
        return {"moved": True}
    if destination.exists():
        raise HTTPException(409, f"Already exists in destination: {source.name}")
    shutil.move(str(source), str(destination))
    return {"moved": True}


@router.delete("/{project_id}/tree")
def delete_tree_entry(project_id: str, path: str, subdir: str = "decoded", db: Session = Depends(get_db)):
    """Deletes a file or folder (recursively) from the decoded workspace —
    used by the file explorer's right-click "Eliminar carpeta". Scoped to
    `decoded` only: `original`/`rebuild`/`signed` are pipeline-managed and
    never user-editable."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if subdir != "decoded":
        raise HTTPException(400, "Only the decoded workspace can be edited")
    if not path or path in (".", ""):
        raise HTTPException(400, "Cannot delete the project root")
    root = apk_service.project_root(project_id)
    try:
        target = resolve_safe_path(root, subdir, path)
    except PathTraversalError:
        raise HTTPException(400, "Invalid path")
    if not target.exists():
        raise HTTPException(404, "Not found")
    import shutil

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"deleted": True}


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    import shutil

    root = apk_service.project_root(project_id)
    if root.exists():
        shutil.rmtree(root)
    db.delete(project)
    db.commit()
    return {"deleted": True}
