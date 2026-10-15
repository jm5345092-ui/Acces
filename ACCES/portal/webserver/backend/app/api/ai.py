from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.provider import get_provider
from app.core.config import get_settings
from app.core.db import get_db
from app.models.modification import Modification, ModificationStatus
from app.models.project import Project
from app.services import apk_service, manifest_service, modification_engine, smali_service

router = APIRouter(prefix="/api/projects", tags=["ai"])
settings = get_settings()


def _project_context(project_id: str, project: Project) -> dict:
    decoded_dir = apk_service.project_root(project_id) / "decoded"
    manifest_path = decoded_dir / "AndroidManifest.xml"
    context: dict = {
        "package": project.package_name,
        "smali_modules": smali_service.list_smali_modules(decoded_dir) if decoded_dir.exists() else [],
    }
    if manifest_path.exists():
        main_activity = manifest_service.find_main_activity(manifest_path)
        context["main_activity"] = main_activity
        if main_activity:
            context["main_activity_class"] = manifest_service.resolve_activity_class(
                project.package_name, main_activity
            )
    return context


@router.post("/{project_id}/ai/plan")
def ai_plan(project_id: str, body: dict = Body(...), db: Session = Depends(get_db)):
    """Section 13: the AI only ever produces a plan of structured
    Modification Engine operations — it never writes a file itself. Each
    step is immediately turned into a normal PENDING Modification (via the
    same `modification_engine.propose()` manual edits use), so the
    frontend's existing diff/confirm/apply/cancel UI handles AI-proposed
    and hand-authored changes identically."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    instruction = body.get("instruction")
    if not instruction:
        raise HTTPException(400, "Missing 'instruction'")

    provider = get_provider(settings.ai_provider)
    try:
        plan = provider.plan(_project_context(project_id, project), instruction)
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    decoded_dir = apk_service.project_root(project_id) / "decoded"
    proposed_modifications = []
    errors = []
    for step in plan.steps:
        if step.operation == "clarify":
            proposed_modifications.append(
                {"operation": "clarify", "rationale": step.rationale, "params": step.params}
            )
            continue
        try:
            change = modification_engine.propose(decoded_dir, step.operation, step.params)
        except Exception as exc:
            errors.append({"operation": step.operation, "params": step.params, "error": str(exc)})
            continue

        mod = Modification(
            project_id=project_id,
            file=change.file,
            operation=change.operation,
            description=f"[AI] {change.description} — {step.rationale}".strip(" —"),
            before_hash=change.before_hash,
            after_hash=change.after_hash,
            before_content=change.before_content,
            after_content=change.after_content,
            status=ModificationStatus.PENDING,
        )
        db.add(mod)
        db.commit()
        db.refresh(mod)
        proposed_modifications.append({"modification_id": mod.id, "diff": change.diff})

    return {"summary": plan.summary, "proposed": proposed_modifications, "errors": errors}
