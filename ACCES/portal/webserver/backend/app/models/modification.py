import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ModificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    REVERTED = "REVERTED"
    FAILED = "FAILED"


class Modification(Base):
    __tablename__ = "modifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    file: Mapped[str] = mapped_column(String(1024))
    operation: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")

    before_hash: Mapped[str] = mapped_column(String(64), default="")
    after_hash: Mapped[str] = mapped_column(String(64), default="")
    before_content: Mapped[str] = mapped_column(Text, default="")
    after_content: Mapped[str] = mapped_column(Text, default="")
    # When True, before/after_content hold base64 — used for binary files
    # (images, audio, etc.) added via folder upload, where a text diff
    # doesn't make sense.
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(Enum(ModificationStatus), default=ModificationStatus.PENDING)
