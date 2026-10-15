"""A note of the owner on an object (Stage 18): free words with the time they were written (Stage 18, owner request after acceptance tests).

Plain owner data: a thought on the site, a phone call, a thing to remember. It is not a reminder (it never sends a message) and not a
document (it never leaves the application). `created_at` is the moment it was written (UTC); `updated_at` moves when the words change.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

MAX_NOTE_LENGTH = 4000


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectNote(Base):
    __tablename__ = "project_notes"
    __table_args__ = (
        CheckConstraint("length(trim(body)) > 0", name="ck_project_notes_body_not_blank"),
        Index("ix_project_notes_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
