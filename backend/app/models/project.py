import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encrypted_text import EncryptedText


class ProjectStatus(str, enum.Enum):
    PLANNING = "PLANNING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(EncryptedText("projects.name"), nullable=False)
    address: Mapped[str] = mapped_column(EncryptedText("projects.address"), nullable=False)
    city: Mapped[str] = mapped_column(EncryptedText("projects.city"), nullable=False)
    postal_code: Mapped[str] = mapped_column(EncryptedText("projects.postal_code"), nullable=False)
    description: Mapped[str | None] = mapped_column(EncryptedText("projects.description"), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="projectstatus"),
        nullable=False,
        default=ProjectStatus.PLANNING,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_projects_owner_archived", "owner_id", "is_archived"),
    )
