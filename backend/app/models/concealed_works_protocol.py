"""The protocol of acceptance of concealed works (Stage 16G): work that the next layers will cover (priming, glass fleece, mesh,
repair of cracks, board joints ...) is accepted **before** it is covered, with photos as the evidence.

One row per acceptance of one kind of work on one surface (`sequence` counts them per object). The row holds the day, the people
present -- or the fact that the customer did not come after being notified on a given day (contract § 13 ust. 3: then a one-sided
protocol with photos is made and the work goes on) --, the material and its batch, the photos chosen as evidence (attachments of
the category HIDDEN_WORK of that surface), the result and the consent to cover. States: DRAFT (at most one per object) -> ISSUED
(frozen: the time, the snapshot, the exact page and the contract it was made under) -> ARCHIVED. Nothing is deleted.
"""
import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class ConcealedStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    ARCHIVED = "ARCHIVED"


class ConcealedWorksProtocol(Base):
    __tablename__ = "concealed_works_protocols"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ConcealedStatus.DRAFT.value)
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    held_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM", optional
    customer_absent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notified_on: Mapped[date | None] = mapped_column(Date, nullable=True)  # the day the customer was told the work is ready to be accepted
    attendees: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)
    surface_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # a plain value: the protocol outlives a changed surface
    work_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)  # a key of the catalogue of kinds
    work_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    material: Mapped[str | None] = mapped_column(String(500), nullable=True)
    batch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_ids: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)  # attachments chosen as the evidence
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)  # ACCEPTED / WITH_REMARKS
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_consent: Mapped[str | None] = mapped_column(String(16), nullable=True)  # GIVEN / WITHHELD
    # what an issued protocol freezes
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(_JSONVariant, nullable=True)
    document_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_concealed_works_status"),
        CheckConstraint("sequence >= 1", name="ck_concealed_works_sequence_positive"),
        CheckConstraint("result IS NULL OR result IN ('ACCEPTED', 'WITH_REMARKS')", name="ck_concealed_works_result"),
        CheckConstraint("cover_consent IS NULL OR cover_consent IN ('GIVEN', 'WITHHELD')", name="ck_concealed_works_cover_consent"),
        CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_concealed_works_frozen_when_issued",
        ),
        UniqueConstraint("project_id", "sequence", name="uq_concealed_works_project_sequence"),
        Index(
            "uq_concealed_works_one_draft", "project_id", unique=True,
            postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'"),
        ),
        Index("ix_concealed_works_project", "project_id", "status"),
    )
