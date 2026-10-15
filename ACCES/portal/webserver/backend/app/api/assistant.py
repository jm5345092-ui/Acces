"""Read-only assistant API (plan §9): `/analysis`, `/events`, `/messages`
are strictly read-only from the project's point of view — they never write
anything. `/ask` is the one endpoint that writes, and only ever writes
`AssistantMessage`/`AssistantEvent` rows (never `Project`/`Modification`/
`Job`, never a project file).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.assistant.service import AssistantService
from app.core.db import get_db
from app.models.project import Project
from app.schemas.assistant import (
    AskRequest,
    AskResponse,
    AssistantEventOut,
    AssistantMessageOut,
    FindingOut,
)

router = APIRouter(prefix="/api/projects", tags=["assistant"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("/{project_id}/assistant/analysis", response_model=list[FindingOut])
def get_analysis(project_id: str, db: Session = Depends(get_db)):
    """Strictly read-only: runs the deterministic ProjectAnalyzer and
    returns its findings without writing anything — safe to poll
    frequently (e.g. for a UI warning badge) with zero LLM cost."""
    _get_project_or_404(db, project_id)
    service = AssistantService(db, project_id)
    return [
        FindingOut(
            observation=f.observation,
            analysis=f.analysis,
            possible_problem=f.possible_problem,
            evidence=f.evidence,
            suggestion=f.suggestion,
            confidence=f.confidence,
        )
        for f in service.get_findings()
    ]


@router.get("/{project_id}/assistant/events", response_model=list[AssistantEventOut])
def get_events(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    service = AssistantService(db, project_id)
    return service.list_events()


@router.get("/{project_id}/assistant/messages", response_model=list[AssistantMessageOut])
def get_messages(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    service = AssistantService(db, project_id)
    return service.list_messages()


@router.post("/{project_id}/assistant/ask", response_model=AskResponse)
def ask(project_id: str, body: AskRequest, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    service = AssistantService(db, project_id)
    try:
        answer = service.ask(body.question)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    findings = [
        FindingOut(
            observation=answer.observation,
            analysis=answer.analysis,
            possible_problem=answer.possible_problem,
            evidence=answer.evidence,
            suggestion=answer.suggestion,
            confidence=answer.confidence,
        )
    ] if answer.mode == "finding" else []

    return AskResponse(
        message=answer.message,
        mode=answer.mode,
        findings=findings,
        events=service.list_events(limit=10),
    )
