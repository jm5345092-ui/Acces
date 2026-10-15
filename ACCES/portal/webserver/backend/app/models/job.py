import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class JobType(str, enum.Enum):
    DECODE = "DECODE"
    ANALYZE = "ANALYZE"
    BUILD_PIPELINE = "BUILD_PIPELINE"
    DEVICE_LIST = "DEVICE_LIST"
    DEVICE_INSTALL = "DEVICE_INSTALL"
    DEVICE_LAUNCH = "DEVICE_LAUNCH"
    DEVICE_LOGCAT = "DEVICE_LOGCAT"
    TOOL_CHECK = "TOOL_CHECK"
    GENERATE_APP = "GENERATE_APP"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id"), index=True, nullable=True
    )
    type: Mapped[str] = mapped_column(Enum(JobType))
    status: Mapped[str] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    log_path: Mapped[str] = mapped_column(String(1024), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
