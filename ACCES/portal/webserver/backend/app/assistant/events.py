"""Hooks called from the two places the system already mutates state
(`api/modifications.py` apply/revert, `workers/job_worker.py` on
failure/comparison) — not a new event bus. Every function here does
exactly one thing: insert a row into `AssistantEvent`. Nothing here ever
touches `Modification`/`Job`/`Project` (plan §6/§10).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.assistant import AssistantConfidence, AssistantEvent

_OPERATION_TO_KIND = {
    "create_smali_package": "package_added",
    "create_smali_class": "class_added",
    "insert_smali_instruction": "method_modified",
    "replace_smali_block": "method_modified",
    "modify_manifest": "manifest_modified",
    "add_resource": "resource_modified",
    "modify_resource": "resource_modified",
}


def record_modification_event(db: Session, modification) -> None:
    kind = _OPERATION_TO_KIND.get(modification.operation, "resource_modified")
    reverted = modification.status == "REVERTED"
    event = AssistantEvent(
        project_id=modification.project_id,
        kind=kind,
        source=f"modification:{modification.id}",
        confidence=AssistantConfidence.USER_ACTION,
        summary=(
            f"{'Revertida' if reverted else 'Aplicada'}: {modification.operation} en {modification.file}"
        ),
        detail_json=json.dumps(
            {"operation": modification.operation, "file": modification.file, "reverted": reverted}
        ),
        dedupe_key=f"modification:{modification.id}:{modification.status}",
    )
    db.add(event)
    db.commit()


def record_job_event(db: Session, job, error: str) -> None:
    kind_map = {
        "DECODE": "decode_failed",
        "ANALYZE": "analyze_failed",
        "BUILD_PIPELINE": "build_failed",
    }
    kind = kind_map.get(job.type, "build_failed")
    event = AssistantEvent(
        project_id=job.project_id,
        kind=kind,
        source=f"job:{job.id}",
        confidence=AssistantConfidence.CONFIRMED_FACT,
        summary=f"Job {job.type} falló: {error[:280]}",
        detail_json=json.dumps({"job_id": job.id, "job_type": job.type, "error": error[:4000]}),
        dedupe_key=f"job:{job.id}:failed",
    )
    db.add(event)
    db.commit()


def record_comparison_event(db: Session, project_id: str, job_id: str, important_differences: list[str]) -> None:
    if not important_differences:
        return
    event = AssistantEvent(
        project_id=project_id,
        kind="comparison_warning",
        source=f"job:{job_id}",
        confidence=AssistantConfidence.CONFIRMED_FACT,
        summary=f"La comparación encontró {len(important_differences)} diferencia(s) importante(s).",
        detail_json=json.dumps({"important_differences": important_differences}),
        dedupe_key=f"job:{job_id}:comparison_warning",
    )
    db.add(event)
    db.commit()
