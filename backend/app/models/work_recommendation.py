"""Stage 11B.1 — recommendation catalog + materialized recommendation record.

`WorkRecommendationRule` is a small, static mapping catalog: it maps an
already-known Stage 6/7 result (a `RiskRule.code` or an
`InspectionFinding.finding_key` — never a condition it evaluates itself) to a
suggested semantic work code (a `PriceItem.code`, resolved against the
owner's *current* PriceBook only at acceptance time — Stage 11C, not here).
It is not a second Rules Engine, a workflow engine, or a price engine; Stage 7
remains the sole authority on condition/risk evaluation.

`WorkRecommendation` is the materialized, actionable record — reusing the
materialize-once / reconcile-by-identity / resolve-never-delete idiom already
used by `Risk` and `CommunicationApplication`. Its identity extends `Risk`'s
own `(inspection_id, rule_code, source_signature)` shape with two more
components: `trigger_type` (a `RiskRule.code` and an `InspectionFinding.
finding_key` are independent vocabularies and must never accidentally share
an identity merely by string coincidence) and `recommended_work_code` (one
trigger firing legitimately maps to several suggested works — e.g. a poor
substrate recommending both a primer and a leveling compound — and each
suggested work needs its own independent PENDING/ACCEPTED/DISMISSED
lifecycle, so each is its own row, never collapsed). Full identity:
`(inspection_id, trigger_type, trigger_code, source_signature,
recommended_work_code)`.

Per the verified Stage 10 finding that `SurfacePlannedWork.id` /
`OpeningRevealPlannedWork.id` are NOT durable across ordinary WorkPlan edits
(see docs/stage-11-architecture.md §2), this model deliberately has NO
`accepted_planned_work_id` FK. Provenance from an accepted recommendation to
"the resulting planned work" is semantic
(`surface_id` + `resolved_price_item_id` + `accepted_at`), not row-level.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkRecommendationTriggerType(str, enum.Enum):
    RISK_RULE = "RISK_RULE"
    FINDING = "FINDING"


class WorkRecommendationTargetKind(str, enum.Enum):
    WALL = "WALL"
    FLOOR = "FLOOR"
    CEILING = "CEILING"
    ROOM = "ROOM"


class WorkRecommendationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DISMISSED = "DISMISSED"


class WorkRecommendationRule(Base):
    """Pure lookup row: an already-known trigger -> a suggested work code.

    Never evaluates a condition itself — `trigger_code` is either an existing
    `RiskRule.code` (when a risk already fired) or an existing
    `InspectionFinding.finding_key` (when a plain recorded fact is enough,
    even below risk severity — not every useful recommendation is a risk).
    """

    __tablename__ = "work_recommendation_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    trigger_type: Mapped[WorkRecommendationTriggerType] = mapped_column(
        Enum(WorkRecommendationTriggerType, name="workrecommendationtriggertype"),
        nullable=False,
    )
    trigger_code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="RiskRule.code (RISK_RULE) or InspectionFinding.finding_key (FINDING)",
    )
    recommended_work_code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment=(
            "Semantic PriceItem.code to suggest — never a price_item_id; "
            "resolved against the owner's current PriceBook only at "
            "acceptance time (Stage 11C)"
        ),
    )
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
        UniqueConstraint(
            "trigger_type",
            "trigger_code",
            "recommended_work_code",
            name="uq_work_recommendation_rules_trigger_work",
        ),
    )


class WorkRecommendation(Base):
    """A materialized, actionable recommendation for exactly one suggested
    semantic work, for one inspection result.

    Identity is `(inspection_id, trigger_type, trigger_code, source_signature,
    recommended_work_code)` — see `uq_work_recommendations_identity` for the
    full rationale — so a re-evaluation (Stage 11B.2) reuses the same row
    (keeping its UUID and lifecycle) rather than duplicating it, exactly like
    `Risk` reconciliation, while still producing one independent row per
    suggested work when a single trigger recommends several.
    """

    __tablename__ = "work_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # --- Identity / trigger provenance -------------------------------------
    trigger_type: Mapped[WorkRecommendationTriggerType] = mapped_column(
        Enum(WorkRecommendationTriggerType, name="workrecommendationtriggertype"),
        nullable=False,
    )
    trigger_code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Copied from the rule's trigger_code at materialization time",
    )
    source_signature: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 over sorted source finding UUIDs (compute_source_signature)",
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("work_recommendation_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Catalog rule that produced this row (audit only; SET NULL preserves history)",
    )
    risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Source Risk when trigger_type = RISK_RULE (audit only)",
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("inspection_findings.id", ondelete="SET NULL"),
        nullable=True,
        comment="Source Finding when trigger_type = FINDING (audit only)",
    )

    # --- Target (denormalized snapshot, not re-derived via joins) ----------
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
        comment="WALL or canonical FLOOR/CEILING Surface; null for ROOM (advisory-only)",
    )
    target_kind: Mapped[WorkRecommendationTargetKind] = mapped_column(
        Enum(WorkRecommendationTargetKind, name="workrecommendationtargetkind"),
        nullable=False,
        comment="Mirrors derive_target_type()'s output verbatim",
    )

    # --- Suggested work (snapshot, immune to later catalog edits) ----------
    recommended_work_code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Copied from WorkRecommendationRule at materialization time",
    )

    # --- Lifecycle -----------------------------------------------------------
    status: Mapped[WorkRecommendationStatus] = mapped_column(
        Enum(WorkRecommendationStatus, name="workrecommendationstatus"),
        nullable=False,
        default=WorkRecommendationStatus.PENDING,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the underlying condition stopped being confirmed by re-evaluation",
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # --- Acceptance snapshot (no accepted_planned_work_id — see module docstring) ---
    resolved_price_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("price_items.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "PriceItem actually used at acceptance time (Stage 11C); NULL "
            "before acceptance and never implies current resolvability"
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
        # Identity is the full (inspection, trigger, source, suggested-work)
        # tuple, not just (inspection, trigger, source): compute_source_
        # signature() identifies ONLY the source evidence (a pure hash over
        # finding UUIDs) and has no knowledge of recommended_work_code, so a
        # single trigger firing that maps to several suggested work codes
        # (e.g. SUBSTRATE_POOR -> PRIMER_M2 + LEVELING_M2 + SKIM_Q3_M2) MUST
        # produce one distinct row per suggested work -- omitting
        # recommended_work_code here would silently collapse them into one
        # row instead of raising a constraint violation. trigger_type is
        # included so a RiskRule.code and an InspectionFinding.finding_key
        # can never accidentally collide into the same identity merely
        # because the two independent vocabularies happen to share a string
        # (this must be obvious from the DB constraint, not an accidental
        # consequence of the two code spaces never colliding in practice).
        UniqueConstraint(
            "inspection_id",
            "trigger_type",
            "trigger_code",
            "source_signature",
            "recommended_work_code",
            name="uq_work_recommendations_identity",
        ),
        Index("ix_work_recommendations_inspection_active", "inspection_id", "is_active"),
        Index("ix_work_recommendations_room_active", "room_id", "is_active"),
    )
