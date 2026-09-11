import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.area_segment import AreaPlane
from app.models.checklist import QualityLevel, Substrate


class InspectionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    surface_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("surfaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Targeted surface when the inspection targets a specific wall",
    )
    plane: Mapped[AreaPlane | None] = mapped_column(
        Enum(AreaPlane, name="areaplane"),
        nullable=True,
        comment=(
            "Targeted plane (FLOOR/CEILING) when no surface is targeted; "
            "null together with surface_id means a room-level inspection"
        ),
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("checklist_templates.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Immutable template snapshot chosen at inspection start",
    )
    substrate: Mapped[Substrate] = mapped_column(
        Enum(Substrate, name="substrate"),
        nullable=False,
    )
    quality_target: Mapped[QualityLevel | None] = mapped_column(
        Enum(QualityLevel, name="qualitylevel"),
        nullable=True,
    )
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="inspectionstatus"),
        nullable=False,
        default=InspectionStatus.DRAFT,
    )
    notes: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
        Index("ix_inspections_room_archived", "room_id", "is_archived"),
        Index("ix_inspections_surface_room", "surface_id", "room_id"),
    )


class InspectionAnswer(Base):
    __tablename__ = "inspection_answers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("checklist_questions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Exact immutable question row the answer refers to",
    )
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_number: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )
    value_text: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    option_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    option_keys: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Selected option keys for MULTI_CHOICE answers",
    )
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
        UniqueConstraint(
            "inspection_id",
            "question_id",
            name="uq_inspection_answers_inspection_question",
        ),
    )


class InspectionFinding(Base):
    __tablename__ = "inspection_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("inspection_answers.id", ondelete="SET NULL"),
        nullable=True,
        comment="Answer that produced this finding",
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("checklist_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    finding_key: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Stable machine-readable key consumed by Stage 7 / Stage 11",
    )
    label_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value_snapshot: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Factual value context at materialization time",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the finding was marked inactive (no longer confirmed)",
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
        Index("ix_inspection_findings_inspection_active", "inspection_id", "is_active"),
        Index("ix_inspection_findings_key", "finding_key"),
    )