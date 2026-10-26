"""The protocol of a pressure test of an installation (V2-12b, "Protokół próby ciśnieniowej"): a water, heating, gas or sewer installation is tested under pressure
**before** it is covered, with the manometer photographed as the evidence.

One row per test of one system (`sequence` counts them per object). The row holds the day and the people present -- or the fact that the customer did not come after being
notified on a given day (the same rule as the protocol of concealed works) --, the system, the place, the medium, the test pressure, the time held, the drop of the pressure,
the photos of the manometer (attachments of the object), the result and the remarks. The result is the owner's word: the application checks no norm. States: DRAFT (at most one
per object) -> ISSUED (frozen: the time, the snapshot, the exact page) -> ARCHIVED (an abandoned draft). Nothing is deleted.
"""
import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base
from app.core.encrypted_text import EncryptedJSON, EncryptedText

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class PressureStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    ARCHIVED = "ARCHIVED"


class PressureTestProtocol(Base):
    __tablename__ = "pressure_test_protocols"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PressureStatus.DRAFT.value)
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    held_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM", optional
    customer_absent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notified_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    attendees: Mapped[list] = mapped_column(EncryptedJSON("pressure_test_protocols.attendees"), nullable=False, default=list)
    system: Mapped[str | None] = mapped_column(String(16), nullable=True)  # COLD_WATER / HOT_WATER / HEATING / GAS / SEWER
    section: Mapped[str | None] = mapped_column(EncryptedText("pressure_test_protocols.section"), nullable=True)  # the part tested, in the owner's words
    medium: Mapped[str | None] = mapped_column(String(8), nullable=True)  # WATER / AIR
    test_pressure_bar: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pressure_drop_bar: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    photo_ids: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)  # the photos of the manometer
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)  # POSITIVE / NEGATIVE
    remarks: Mapped[str | None] = mapped_column(EncryptedText("pressure_test_protocols.remarks"), nullable=True)
    # what an issued protocol freezes
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(EncryptedJSON("pressure_test_protocols.snapshot"), nullable=True)
    document_html: Mapped[str | None] = mapped_column(EncryptedText("pressure_test_protocols.document_html"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_pressure_tests_status"),
        CheckConstraint("sequence >= 1", name="ck_pressure_tests_sequence_positive"),
        CheckConstraint("system IS NULL OR system IN ('COLD_WATER', 'HOT_WATER', 'HEATING', 'GAS', 'SEWER')", name="ck_pressure_tests_system"),
        CheckConstraint("medium IS NULL OR medium IN ('WATER', 'AIR')", name="ck_pressure_tests_medium"),
        CheckConstraint("result IS NULL OR result IN ('POSITIVE', 'NEGATIVE')", name="ck_pressure_tests_result"),
        CheckConstraint("test_pressure_bar IS NULL OR (test_pressure_bar > 0 AND test_pressure_bar <= 100)", name="ck_pressure_tests_pressure"),
        CheckConstraint("duration_min IS NULL OR (duration_min > 0 AND duration_min <= 1440)", name="ck_pressure_tests_duration"),
        CheckConstraint("pressure_drop_bar IS NULL OR (pressure_drop_bar >= 0 AND pressure_drop_bar <= 100)", name="ck_pressure_tests_drop"),
        CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_pressure_tests_frozen_when_issued",
        ),
        UniqueConstraint("project_id", "sequence", name="uq_pressure_tests_project_sequence"),
        Index(
            "uq_pressure_tests_one_draft", "project_id", unique=True,
            postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'"),
        ),
        Index("ix_pressure_tests_project", "project_id", "status"),
    )
