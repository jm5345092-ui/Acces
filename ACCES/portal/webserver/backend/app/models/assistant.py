"""The assistant's own tables — its entire write surface (plan §6/§10).

Nothing outside this module is ever written to by `app/assistant/*` or
`app/api/assistant.py`.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AssistantConfidence(str, enum.Enum):
    """The four categories the user must always be able to tell apart —
    never silently promoted into each other (e.g. a HYPOTHESIS must never
    be logged or phrased as a CONFIRMED_FACT)."""

    CONFIRMED_FACT = "CONFIRMED_FACT"
    HYPOTHESIS = "HYPOTHESIS"
    SUGGESTION = "SUGGESTION"
    USER_ACTION = "USER_ACTION"


class AssistantEventKind(str, enum.Enum):
    MANIFEST_MODIFIED = "manifest_modified"
    CLASS_ADDED = "class_added"
    PACKAGE_ADDED = "package_added"
    METHOD_MODIFIED = "method_modified"
    RESOURCE_MODIFIED = "resource_modified"
    MODIFICATION_REVERTED = "modification_reverted"
    DECODE_FAILED = "decode_failed"
    ANALYZE_FAILED = "analyze_failed"
    BUILD_FAILED = "build_failed"
    COMPARISON_WARNING = "comparison_warning"
    FINDING = "finding"


class AssistantEvent(Base):
    __tablename__ = "assistant_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(128))  # e.g. "modification:<id>", "job:<id>", "analyzer"
    confidence: Mapped[str] = mapped_column(Enum(AssistantConfidence))
    summary: Mapped[str] = mapped_column(Text, default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    dedupe_key: Mapped[str] = mapped_column(String(128), default="", index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
