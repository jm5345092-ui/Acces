import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProjectStatus(str, enum.Enum):
    CREATED = "CREATED"
    UPLOADED = "UPLOADED"
    DECODING = "DECODING"
    DECODED = "DECODED"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    BUILDING = "BUILDING"
    BUILT = "BUILT"
    SIGNED = "SIGNED"
    FAILED = "FAILED"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    original_filename: Mapped[str] = mapped_column(String(255), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    sha1: Mapped[str] = mapped_column(String(40), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    package_name: Mapped[str] = mapped_column(String(255), default="")
    version_code: Mapped[str] = mapped_column(String(64), default="")
    version_name: Mapped[str] = mapped_column(String(64), default="")
    min_sdk: Mapped[str] = mapped_column(String(16), default="")
    target_sdk: Mapped[str] = mapped_column(String(16), default="")

    status: Mapped[str] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.CREATED
    )
