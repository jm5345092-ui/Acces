"""AssistantService.ask() — orchestrates Analyzer + Provider + memory
(plan §1/§13). The only writes anywhere in this call are `AssistantMessage`
and `AssistantEvent` rows (plan §6/§10).
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.assistant.analyzer import Finding, ProjectAnalyzer
from app.assistant.context import ReadOnlyProjectContext
from app.assistant.provider import AssistantAnswer, AssistantTurn, get_assistant_provider
from app.core.config import get_settings
from app.models.assistant import AssistantConfidence, AssistantEvent, AssistantMessage

settings = get_settings()

_MAX_HISTORY_MESSAGES = 10
_MAX_HISTORY_EVENTS = 20


def _finding_dedupe_key(project_id: str, finding: Finding) -> str:
    raw = f"{project_id}|{finding.observation}|{finding.evidence}"
    return "finding:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _build_whitelisted_context(ctx: ReadOnlyProjectContext, findings: list[Finding]) -> dict:
    """Explicit whitelist sent to the LLM — manifest summary, counts,
    findings, bounded history. Never `.env`, keystore passwords, or raw
    file dumps (plan §5/§7)."""
    project = ctx.get_project()
    manifest = ctx.get_manifest() or {}
    dex = ctx.get_dex_summary() or {}
    resources = ctx.get_resources() or {}
    assets = ctx.get_assets() or {}

    return {
        "project_name": project.name if project else "",
        "package": manifest.get("package", ""),
        "min_sdk": manifest.get("min_sdk", ""),
        "target_sdk": manifest.get("target_sdk", ""),
        "activity_count": len(manifest.get("activities", [])),
        "service_count": len(manifest.get("services", [])),
        "receiver_count": len(manifest.get("receivers", [])),
        "provider_count": len(manifest.get("providers", [])),
        "permission_count": len(manifest.get("permissions", [])),
        "class_count": dex.get("total_classes", 0),
        "method_count": dex.get("total_methods", 0),
        "resource_count": resources.get("count", 0),
        "asset_count": assets.get("count", 0),
        "findings": [
            {
                "observation": f.observation,
                "analysis": f.analysis,
                "possible_problem": f.possible_problem,
                "evidence": f.evidence,
                "confidence": f.confidence,
            }
            for f in findings
        ],
    }


class AssistantService:
    def __init__(self, db: Session, project_id: str) -> None:
        self._db = db
        self.project_id = project_id
        self._ctx = ReadOnlyProjectContext(db, project_id)

    def get_findings(self) -> list[Finding]:
        return ProjectAnalyzer(self._ctx).analyze()

    def list_events(self, *, limit: int = 50) -> list[AssistantEvent]:
        return (
            self._db.query(AssistantEvent)
            .filter(AssistantEvent.project_id == self.project_id)
            .order_by(AssistantEvent.timestamp.desc())
            .limit(limit)
            .all()
        )

    def list_messages(self, *, limit: int = 50) -> list[AssistantMessage]:
        return (
            self._db.query(AssistantMessage)
            .filter(AssistantMessage.project_id == self.project_id)
            .order_by(AssistantMessage.timestamp.asc())
            .limit(limit)
            .all()
        )

    def _log_new_findings(self, findings: list[Finding]) -> None:
        for finding in findings:
            dedupe_key = _finding_dedupe_key(self.project_id, finding)
            exists = (
                self._db.query(AssistantEvent)
                .filter(AssistantEvent.dedupe_key == dedupe_key)
                .first()
            )
            if exists:
                continue
            self._db.add(
                AssistantEvent(
                    project_id=self.project_id,
                    kind="finding",
                    source="analyzer",
                    confidence=AssistantConfidence(finding.confidence),
                    summary=finding.observation,
                    detail_json=json.dumps(
                        {
                            "analysis": finding.analysis,
                            "possible_problem": finding.possible_problem,
                            "evidence": finding.evidence,
                            "suggestion": finding.suggestion,
                            "related_modification_ids": finding.related_modification_ids,
                        }
                    ),
                    dedupe_key=dedupe_key,
                )
            )
        self._db.commit()

    def ask(self, question: str) -> AssistantAnswer:
        findings = self.get_findings()
        self._log_new_findings(findings)

        history_rows = (
            self._db.query(AssistantMessage)
            .filter(AssistantMessage.project_id == self.project_id)
            .order_by(AssistantMessage.timestamp.desc())
            .limit(_MAX_HISTORY_MESSAGES)
            .all()
        )
        history = [AssistantTurn(role=m.role, content=m.content) for m in reversed(history_rows)]

        context = _build_whitelisted_context(self._ctx, findings)
        provider = get_assistant_provider(settings.ai_provider)
        answer = provider.answer(project_context=context, history=history, question=question)

        self._db.add(AssistantMessage(project_id=self.project_id, role="user", content=question))
        self._db.add(
            AssistantMessage(project_id=self.project_id, role="assistant", content=answer.message)
        )
        self._db.commit()

        return answer
