from __future__ import annotations

import difflib

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.assistant import events as assistant_events
from app.core.db import get_db
from app.models.modification import Modification, ModificationStatus
from app.models.project import Project
from app.schemas.modification import ModificationOut
from app.services import apk_service, modification_engine

router = APIRouter(prefix="/api/projects", tags=["modifications"])


def _decoded_dir(project_id: str):
    return apk_service.project_root(project_id) / "decoded"


@router.post("/{project_id}/modifications", response_model=ModificationOut)
def propose_modification(project_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    operation = body.get("operation")
    if operation not in modification_engine.OPERATIONS:
        raise HTTPException(400, f"Unknown or missing operation: {operation}")

    try:
        change = modification_engine.propose(_decoded_dir(project_id), operation, body)
    except Exception as exc:
        raise HTTPException(400, str(exc))

    mod = Modification(
        project_id=project_id,
        file=change.file,
        operation=change.operation,
        description=change.description,
        before_hash=change.before_hash,
        after_hash=change.after_hash,
        before_content=change.before_content,
        after_content=change.after_content,
        is_binary=change.is_binary,
        status=ModificationStatus.PENDING,
    )
    db.add(mod)
    db.commit()
    db.refresh(mod)
    return mod


@router.get("/{project_id}/modifications", response_model=list[ModificationOut])
def list_modifications(project_id: str, db: Session = Depends(get_db)):
    return (
        db.query(Modification)
        .filter(Modification.project_id == project_id)
        .order_by(Modification.timestamp.desc())
        .all()
    )


@router.get("/{project_id}/modifications/{mod_id}")
def get_modification(project_id: str, mod_id: str, db: Session = Depends(get_db)):
    mod = db.get(Modification, mod_id)
    if not mod or mod.project_id != project_id:
        raise HTTPException(404, "Modification not found")
    diff = "".join(
        difflib.unified_diff(
            mod.before_content.splitlines(keepends=True),
            mod.after_content.splitlines(keepends=True),
            fromfile=f"a/{mod.file}",
            tofile=f"b/{mod.file}",
        )
    )
    return {**ModificationOut.model_validate(mod).model_dump(), "diff": diff}


@router.post("/{project_id}/modifications/apply-pending")
def apply_all_pending(project_id: str, db: Session = Depends(get_db)):
    """Bulk-applies every PENDING modification for the project, in the
    order they were proposed — mainly for folder uploads, where reviewing
    and clicking Apply on dozens/hundreds of individual files one at a time
    isn't practical. Stops recording success per-file; a failure on one
    file doesn't block the rest."""
    pending = (
        db.query(Modification)
        .filter(Modification.project_id == project_id, Modification.status == ModificationStatus.PENDING)
        .order_by(Modification.timestamp.asc())
        .all()
    )
    from app.services.smali_service import ProposedChange

    applied, failed = [], []
    for mod in pending:
        change = ProposedChange(
            file=mod.file,
            operation=mod.operation,
            description=mod.description,
            before_content=mod.before_content,
            after_content=mod.after_content,
            is_binary=mod.is_binary,
        )
        try:
            modification_engine.apply(_decoded_dir(project_id), change)
        except Exception as exc:
            mod.status = ModificationStatus.FAILED
            db.commit()
            failed.append({"id": mod.id, "file": mod.file, "error": str(exc)})
            continue
        mod.status = ModificationStatus.APPLIED
        db.commit()
        db.refresh(mod)
        assistant_events.record_modification_event(db, mod)
        applied.append(mod.id)

    return {"applied": applied, "failed": failed}


@router.post("/{project_id}/modifications/{mod_id}/apply", response_model=ModificationOut)
def apply_modification(project_id: str, mod_id: str, db: Session = Depends(get_db)):
    mod = db.get(Modification, mod_id)
    if not mod or mod.project_id != project_id:
        raise HTTPException(404, "Modification not found")
    if mod.status != ModificationStatus.PENDING:
        raise HTTPException(409, f"Modification is {mod.status}, not PENDING")

    from app.services.smali_service import ProposedChange

    change = ProposedChange(
        file=mod.file,
        operation=mod.operation,
        description=mod.description,
        before_content=mod.before_content,
        after_content=mod.after_content,
        is_binary=mod.is_binary,
    )
    try:
        modification_engine.apply(_decoded_dir(project_id), change)
    except Exception as exc:
        mod.status = ModificationStatus.FAILED
        db.commit()
        raise HTTPException(400, str(exc))

    mod.status = ModificationStatus.APPLIED
    db.commit()
    db.refresh(mod)
    assistant_events.record_modification_event(db, mod)
    return mod


@router.post("/{project_id}/modifications/{mod_id}/revert", response_model=ModificationOut)
def revert_modification(project_id: str, mod_id: str, db: Session = Depends(get_db)):
    mod = db.get(Modification, mod_id)
    if not mod or mod.project_id != project_id:
        raise HTTPException(404, "Modification not found")
    if mod.status != ModificationStatus.APPLIED:
        raise HTTPException(409, f"Modification is {mod.status}, not APPLIED")

    # Reverting writes `before_content` over the whole file, which would
    # silently discard any LATER applied change to that same file. Instead
    # of risking that, require later changes on the same file to be
    # reverted first (in last-applied-first order) — reverting a single
    # change must only ever undo that change, never someone else's.
    blocking = (
        db.query(Modification)
        .filter(
            Modification.project_id == project_id,
            Modification.file == mod.file,
            Modification.status == ModificationStatus.APPLIED,
            Modification.timestamp > mod.timestamp,
        )
        .order_by(Modification.timestamp.asc())
        .first()
    )
    if blocking:
        raise HTTPException(
            409,
            f"No se puede revertir: hay un cambio más reciente sobre el mismo archivo "
            f"'{mod.file}' ({blocking.operation}, id={blocking.id}). Revierte primero ese "
            f"cambio más reciente.",
        )

    from app.services.smali_service import ProposedChange

    change = ProposedChange(
        file=mod.file,
        operation=mod.operation,
        description=mod.description,
        before_content=mod.before_content,
        after_content=mod.after_content,
        is_binary=mod.is_binary,
    )
    modification_engine.revert(_decoded_dir(project_id), change)
    mod.status = ModificationStatus.REVERTED
    db.commit()
    db.refresh(mod)
    assistant_events.record_modification_event(db, mod)
    return mod
