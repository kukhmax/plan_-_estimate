"""The link for the client (V2-8): a secret address of one object, the extra-work proposals the client decides, and the journal of consents.

`client_links` keeps only the SHA-256 of the secret (the link itself is shown once, when it is made); one unrevoked link per object.
`client_proposals` are immutable once made (to change one, withdraw it and make another); title and description are the owner's words about
the client's flat, so they are encrypted like the rest of the object. `client_consents` is the journal: rows are only ever added, and each
holds the exact text the client agreed to or refused, the hash of what was shown, and hashes (never raw values) of the address and the browser.
"""
import enum
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
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encrypted_text import EncryptedText


class ProposalStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"


class ConsentKind(str, enum.Enum):
    ESTIMATE_ACCEPTED = "ESTIMATE_ACCEPTED"
    ESTIMATE_DECLINED = "ESTIMATE_DECLINED"
    PROPOSAL_ACCEPTED = "PROPOSAL_ACCEPTED"
    PROPOSAL_DECLINED = "PROPOSAL_DECLINED"


def _now() -> datetime:
    return datetime.now(UTC)


class ClientLink(Base):
    __tablename__ = "client_links"
    __table_args__ = (
        CheckConstraint("language IN ('pl', 'ru', 'uk', 'en')", name="ck_client_links_language"),
        Index(
            "uq_client_links_active_project",
            "project_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="pl")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ClientProposal(Base):
    __tablename__ = "client_proposals"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'ACCEPTED', 'DECLINED', 'WITHDRAWN')", name="ck_client_proposals_status"),
        CheckConstraint("amount > 0", name="ck_client_proposals_amount_positive"),
        CheckConstraint("extra_days IS NULL OR extra_days >= 0", name="ck_client_proposals_days_not_negative"),
        UniqueConstraint("project_id", "sequence", name="uq_client_proposals_project_sequence"),
        Index("ix_client_proposals_project_status", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(EncryptedText("client_proposals.title"), nullable=False)
    description: Mapped[str | None] = mapped_column(EncryptedText("client_proposals.description"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN")
    extra_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=ProposalStatus.OPEN.value)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClientConsent(Base):
    __tablename__ = "client_consents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ESTIMATE_ACCEPTED', 'ESTIMATE_DECLINED', 'PROPOSAL_ACCEPTED', 'PROPOSAL_DECLINED')", name="ck_client_consents_kind"
        ),
        CheckConstraint(
            "(kind IN ('ESTIMATE_ACCEPTED', 'ESTIMATE_DECLINED') AND estimate_id IS NOT NULL AND proposal_id IS NULL)"
            " OR (kind IN ('PROPOSAL_ACCEPTED', 'PROPOSAL_DECLINED') AND proposal_id IS NOT NULL)",
            name="ck_client_consents_subject",
        ),
        CheckConstraint(
            "comment IS NULL OR kind IN ('ESTIMATE_DECLINED', 'PROPOSAL_DECLINED')", name="ck_client_consents_comment_on_decline"
        ),
        UniqueConstraint("estimate_id", name="uq_client_consents_estimate"),
        UniqueConstraint("proposal_id", name="uq_client_consents_proposal"),
        Index("ix_client_consents_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    link_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("client_links.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    estimate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estimate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)  # the exact Polish text the client agreed to (no personal data)
    statement_lang: Mapped[str] = mapped_column(String(2), nullable=False, default="pl")
    signer_name: Mapped[str] = mapped_column(EncryptedText("client_consents.signer_name"), nullable=False)
    comment: Mapped[str | None] = mapped_column(EncryptedText("client_consents.comment"), nullable=True)  # the reason of a refusal (V2-8b), optional
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
