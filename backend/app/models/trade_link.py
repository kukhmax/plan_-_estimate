"""The link for the electrician and the plumber (V2-14): a secret address of one object and one trade, the answers of the craftsman for each room, the journal of what he sent.

`trade_links` keeps only the SHA-256 of the secret; one unrevoked link per (object, trade). `trade_answers` belong to the (object, trade) and not to a link, so a renewed link finds the
answers of the old one. A typical answer has a `position_key` (the checklist is in `domain/rules/trade_checklist.py`), an own one has a `custom_name`; never both. `trade_submissions` is the
journal: rows are only ever added; each holds a hash of what was sent and hashes (never raw values) of the address and the browser. The owner's word and everything the craftsman wrote
are encrypted like the rest of the object.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encrypted_text import EncryptedText


def _now() -> datetime:
    return datetime.now(UTC)


class TradeLink(Base):
    __tablename__ = "trade_links"
    __table_args__ = (
        CheckConstraint("trade IN ('ELECTRIC', 'PLUMBING')", name="ck_trade_links_trade"),
        CheckConstraint("language IN ('pl', 'ru', 'uk', 'en')", name="ck_trade_links_language"),
        Index(
            "uq_trade_links_active",
            "project_id",
            "trade",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    trade: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="pl")
    owner_note: Mapped[str | None] = mapped_column(EncryptedText("trade_links.owner_note"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TradeAnswer(Base):
    __tablename__ = "trade_answers"
    __table_args__ = (
        CheckConstraint("trade IN ('ELECTRIC', 'PLUMBING')", name="ck_trade_answers_trade"),
        CheckConstraint("unit IN ('PCS', 'LM')", name="ck_trade_answers_unit"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_trade_answers_quantity"),
        CheckConstraint(
            "(position_key IS NOT NULL AND custom_name IS NULL) OR (position_key IS NULL AND custom_name IS NOT NULL)",
            name="ck_trade_answers_typical_or_own",
        ),
        CheckConstraint("position_key IS NULL OR quantity IS NOT NULL OR note IS NOT NULL", name="ck_trade_answers_typical_has_content"),
        CheckConstraint("custom_name IS NULL OR quantity IS NOT NULL", name="ck_trade_answers_own_has_quantity"),
        UniqueConstraint("project_id", "trade", "room_id", "position_key", name="uq_trade_answers_position"),
        Index("ix_trade_answers_room", "project_id", "trade", "room_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    trade: Mapped[str] = mapped_column(String(16), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    position_key: Mapped[str | None] = mapped_column(String(24), nullable=True)
    custom_name: Mapped[str | None] = mapped_column(EncryptedText("trade_answers.custom_name"), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(3), nullable=False)
    note: Mapped[str | None] = mapped_column(EncryptedText("trade_answers.note"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class TradeSubmission(Base):
    __tablename__ = "trade_submissions"
    __table_args__ = (
        CheckConstraint("trade IN ('ELECTRIC', 'PLUMBING')", name="ck_trade_submissions_trade"),
        Index("ix_trade_submissions_project", "project_id", "trade", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    link_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("trade_links.id", ondelete="CASCADE"), nullable=False)
    trade: Mapped[str] = mapped_column(String(16), nullable=False)
    master_name: Mapped[str] = mapped_column(EncryptedText("trade_submissions.master_name"), nullable=False)
    answers_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    answers_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
