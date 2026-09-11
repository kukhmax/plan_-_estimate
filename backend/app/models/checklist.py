import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Substrate(str, enum.Enum):
    CONCRETE = "CONCRETE"
    GYPSUM_PLASTER = "GYPSUM_PLASTER"
    CEMENT_LIME_PLASTER = "CEMENT_LIME_PLASTER"
    GYPSUM_BOARD = "GYPSUM_BOARD"
    PAINTED = "PAINTED"
    OTHER = "OTHER"


class QualityLevel(str, enum.Enum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"


class AnswerType(str, enum.Enum):
    BOOLEAN = "BOOLEAN"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    NUMBER = "NUMBER"
    TEXT = "TEXT"


class ChecklistTemplate(Base):
    __tablename__ = "checklist_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    substrate: Mapped[Substrate | None] = mapped_column(
        Enum(Substrate, name="substrate"),
        nullable=True,
        comment="Primary substrate this template serves (null = generic)",
    )
    title_key: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
        UniqueConstraint("code", "version", name="uq_checklist_templates_code_version"),
    )


class ChecklistSection(Base):
    __tablename__ = "checklist_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("checklist_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title_key: Mapped[str] = mapped_column(String(255), nullable=False)
    description_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_checklist_sections_template_position", "template_id", "position"),
    )


class ChecklistQuestion(Base):
    __tablename__ = "checklist_questions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("checklist_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("checklist_sections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    text_key: Mapped[str] = mapped_column(String(255), nullable=False)
    hint_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    answer_type: Mapped[AnswerType] = mapped_column(
        Enum(AnswerType, name="answertype"),
        nullable=False,
    )
    finding_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment=(
            "Stable machine-readable finding key; only questions explicitly "
            "configured with one may materialize findings"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index(
            "ix_checklist_questions_template_section_position",
            "template_id",
            "section_id",
            "position",
        ),
    )


class ChecklistOption(Base):
    __tablename__ = "checklist_options"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("checklist_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    label_key: Mapped[str] = mapped_column(String(255), nullable=False)
    finding_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="Stable finding key produced when this option is selected",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_checklist_options_question_position", "question_id", "position"),
    )