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
from app.models.checklist import QualityLevel, Substrate


class CommunicationCategory(str, enum.Enum):
    EXPLAIN_CONDITION = "EXPLAIN_CONDITION"
    EXPLAIN_CONSEQUENCE = "EXPLAIN_CONSEQUENCE"
    RECOMMEND_PREPARATION = "RECOMMEND_PREPARATION"
    REQUIRE_CLIENT_DECISION = "REQUIRE_CLIENT_DECISION"
    SCOPE_CLARIFICATION = "SCOPE_CLARIFICATION"
    QUALITY_EXPECTATION = "QUALITY_EXPECTATION"
    DOCUMENT_AGREEMENT = "DOCUMENT_AGREEMENT"
    GENERAL = "GENERAL"


class CommunicationPhrase(Base):
    """A versioned, immutable phrase definition from the reference catalog."""

    __tablename__ = "communication_phrases"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    category: Mapped[CommunicationCategory] = mapped_column(
        Enum(CommunicationCategory, name="communicationcategory"),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Lower values are shown first within a category/selection",
    )
    risk_code: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="Trigger: a materialized active risk with this risk_code",
    )
    finding_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="Trigger: an active inspection finding with this finding_key",
    )
    substrate: Mapped[Substrate | None] = mapped_column(
        Enum(Substrate, name="substrate"),
        nullable=True,
        comment="Optional trigger refinement (null = any substrate)",
    )
    quality_level: Mapped[QualityLevel | None] = mapped_column(
        Enum(QualityLevel, name="qualitylevel"),
        nullable=True,
        comment="Optional trigger refinement (null = any quality target)",
    )
    phrase_key: Mapped[str] = mapped_column(String(255), nullable=False)
    why_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="i18n key for the traceability hint ('why is this phrase offered')",
    )
    seed_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment=(
            "For risk-derived phrases the Stage 7 risk.<slug>.communication key "
            "being reused; the catalog never duplicates risk.* locale content"
        ),
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
            "code", "version", name="uq_communication_phrases_code_version"
        ),
        Index("ix_communication_phrases_active_category", "active", "category"),
    )


class CommunicationApplication(Base):
    """A phrase materialized onto one COMPLETED inspection.

    Reused across evaluations by identity (phrase_code, source_signature), so a
    reapplied phrase keeps its UUID and its original version/catalog snapshot.
    Applications that stop applying are resolved, never deleted.
    """

    __tablename__ = "communication_applications"

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
    phrase_code: Mapped[str] = mapped_column(String(120), nullable=False)
    phrase_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Phrase version evaluated at materialization time",
    )
    category: Mapped[CommunicationCategory] = mapped_column(
        Enum(CommunicationCategory, name="communicationcategory"),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    phrase_key: Mapped[str] = mapped_column(String(255), nullable=False)
    why_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seed_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="RISK, FINDING or QUALITY — which deterministic source produced this",
    )
    source_signature: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "SHA-256 over sorted source finding UUIDs (constant for context-only "
            "quality phrases); part of the stable identity"
        ),
    )
    risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
        comment="Live link to the materialized risk for RISK-derived phrases",
    )
    finding_key_snapshot: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="Source finding key for FINDING-derived traceability",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the phrase stopped being confirmed by the latest evaluation",
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
        UniqueConstraint(
            "inspection_id",
            "phrase_code",
            "source_signature",
            name="uq_communication_applications_inspection_phrase_signature",
        ),
        Index(
            "ix_communication_applications_inspection_active",
            "inspection_id",
            "is_active",
        ),
        Index("ix_communication_applications_risk_id", "risk_id"),
    )