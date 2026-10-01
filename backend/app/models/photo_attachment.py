"""Photo attachment: one PhotoAsset placed in one business context (Stage 14C.2).

Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §4–§7.

The asset carries immutable file facts; the attachment carries everything
context-specific and editable (category, caption, report inclusion, position,
archive state). One asset may be attached to several contexts.

Targets are leaf-only typed nullable FKs selected by `context` and enforced
by one row-local CHECK (no polymorphic entity_type/entity_id). The schema
already contains the INSPECTION / FINDING / WORK columns for forward
compatibility; that does NOT enable them -- the Stage 14C service accepts
only PROJECT, ROOM, SURFACE and OPENING (INSPECTION/FINDING: 14F, WORK: 14H).

Every evidence parent is ON DELETE RESTRICT, including `question_id`
(owner decision R-2): deleting a parent must never silently drop evidence or
turn question-level evidence into inspection-level evidence. `occurrence_key`
has no FK by design (Stage 13 durable key, never SurfacePlannedWork.id).

Active-row uniqueness is one partial unique index per context
(`archived_at IS NULL`); every indexed column is non-NULL inside its branch,
so PostgreSQL's "NULLs are distinct" rule leaves no duplicate hole.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PhotoAttachmentContext(str, enum.Enum):
    PROJECT = "PROJECT"
    ROOM = "ROOM"
    SURFACE = "SURFACE"
    OPENING = "OPENING"
    INSPECTION = "INSPECTION"  # schema only until Stage 14F
    FINDING = "FINDING"  # schema only until Stage 14F
    WORK = "WORK"  # schema only until Stage 14H


class PhotoCategory(str, enum.Enum):
    GENERAL = "GENERAL"
    BEFORE = "BEFORE"
    DEFECT = "DEFECT"
    PREPARATION = "PREPARATION"
    IN_PROGRESS = "IN_PROGRESS"
    HIDDEN_WORK = "HIDDEN_WORK"
    AFTER = "AFTER"
    DAMAGE = "DAMAGE"


MAX_CAPTION_LENGTH = 1000

# Contract §5 / 14A §15.3 -- portable SQL (SQLite + PostgreSQL), no num_nonnulls.
CONTEXT_TARGETS_CHECK = (
    "(context = 'PROJECT' AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'ROOM' AND room_id IS NOT NULL AND surface_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'SURFACE' AND surface_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'OPENING' AND opening_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'INSPECTION' AND inspection_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND opening_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'FINDING' AND finding_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'WORK' AND surface_id IS NOT NULL AND occurrence_key IS NOT NULL"
    " AND price_item_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL)"
)

# (index name, columns, predicate without the shared "archived_at IS NULL").
ACTIVE_UNIQUE_INDEXES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("uq_photo_att_project_active", ("asset_id",), "context = 'PROJECT'"),
    ("uq_photo_att_room_active", ("asset_id", "room_id"), "context = 'ROOM'"),
    ("uq_photo_att_surface_active", ("asset_id", "surface_id"), "context = 'SURFACE'"),
    ("uq_photo_att_opening_active", ("asset_id", "opening_id"), "context = 'OPENING'"),
    (
        "uq_photo_att_inspection_active",
        ("asset_id", "inspection_id"),
        "context = 'INSPECTION' AND question_id IS NULL",
    ),
    (
        "uq_photo_att_inspection_question_active",
        ("asset_id", "inspection_id", "question_id"),
        "context = 'INSPECTION' AND question_id IS NOT NULL",
    ),
    ("uq_photo_att_finding_active", ("asset_id", "finding_id"), "context = 'FINDING'"),
    ("uq_photo_att_work_active", ("asset_id", "surface_id", "occurrence_key"), "context = 'WORK'"),
)


def _active_predicate(predicate: str) -> str:
    return f"{predicate} AND archived_at IS NULL"


def _active_unique_index(name: str, columns: tuple[str, ...], predicate: str) -> Index:
    where = text(_active_predicate(predicate))
    return Index(name, *columns, unique=True, sqlite_where=where, postgresql_where=where)


class PhotoAttachment(Base):
    __tablename__ = "photo_attachments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("photo_assets.id", ondelete="RESTRICT"), nullable=False
    )
    # = the asset's project (service-validated); ownership is project -> owner.
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    context: Mapped[PhotoAttachmentContext] = mapped_column(
        Enum(PhotoAttachmentContext, name="photoattachmentcontext"), nullable=False
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=True
    )
    surface_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("surfaces.id", ondelete="RESTRICT"), nullable=True
    )
    opening_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("openings.id", ondelete="RESTRICT"), nullable=True
    )
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=True
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("checklist_questions.id", ondelete="RESTRICT"), nullable=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("inspection_findings.id", ondelete="RESTRICT"), nullable=True
    )
    # Stage 13 durable occurrence identity; intentionally no FK.
    occurrence_key: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    price_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("price_items.id", ondelete="RESTRICT"), nullable=True
    )
    category: Mapped[PhotoCategory] = mapped_column(
        Enum(PhotoCategory, name="photocategory"), nullable=False, default=PhotoCategory.GENERAL
    )
    caption: Mapped[str | None] = mapped_column(String(MAX_CAPTION_LENGTH), nullable=True)
    include_in_report: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(CONTEXT_TARGETS_CHECK, name="ck_photo_attachments_context_targets"),
        CheckConstraint("position >= 0", name="ck_photo_attachments_position_nonneg"),
        *(_active_unique_index(name, cols, pred) for name, cols, pred in ACTIVE_UNIQUE_INDEXES),
        Index("ix_photo_attachments_project_context_archived", "project_id", "context", "archived_at"),
        Index("ix_photo_attachments_asset_id", "asset_id"),
        Index("ix_photo_attachments_room_id", "room_id"),
        Index("ix_photo_attachments_surface_id", "surface_id"),
        Index("ix_photo_attachments_opening_id", "opening_id"),
        Index("ix_photo_attachments_inspection_id", "inspection_id"),
        Index("ix_photo_attachments_finding_id", "finding_id"),
        Index("ix_photo_attachments_surface_occurrence", "surface_id", "occurrence_key"),
    )
