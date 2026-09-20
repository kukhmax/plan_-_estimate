"""create work recommendation catalog + persistence (Stage 11B.1)

Revision ID: 0022_work_recommendations
Revises: 0021_client_telegram
Create Date: 2026-09-20 14:00:00.000000

Adds the Stage 11 recommendation persistence foundation only:

- work_recommendation_rules: a small static mapping catalog (an already-known
  RiskRule.code or InspectionFinding.finding_key -> a suggested semantic
  PriceItem.code). It is not a second Rules Engine and stores no prices.
- work_recommendations: the materialized, actionable record, reusing the
  materialize-once / reconcile-by-identity / resolve-never-delete idiom
  already used by risks and communication_applications. Identity is
  (inspection_id, trigger_type, trigger_code, source_signature,
  recommended_work_code) -- extends risks' own (inspection_id, rule_code,
  source_signature) identity with trigger_type (a RiskRule.code and an
  InspectionFinding.finding_key are independent vocabularies and must never
  accidentally collide) and recommended_work_code (source_signature is a
  pure hash over source finding UUIDs with no knowledge of the suggested
  work, so one trigger firing that maps to several suggested works, e.g. a
  poor substrate recommending both a primer and a leveling compound, must
  produce one distinct row per suggested work, never collapsed into one).

No accepted_planned_work_id column exists on purpose: SurfacePlannedWork.id
and OpeningRevealPlannedWork.id were verified NOT durable across ordinary
WorkPlan edits (see docs/stage-11-architecture.md Sec 2), so acceptance
provenance is a semantic snapshot (surface_id + resolved_price_item_id +
accepted_at), never a row-level FK.

Purely additive. No existing table/column/enum is altered. No evaluation
endpoint, no accept-to-WorkPlan mutation, and no Estimate change are
introduced by this migration -- those are Stage 11B.2/11C.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0022_work_recommendations"
down_revision: Union[str, None] = "0021_client_telegram"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_recommendation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "trigger_type",
            sa.Enum("RISK_RULE", "FINDING", name="workrecommendationtriggertype"),
            nullable=False,
        ),
        sa.Column("trigger_code", sa.String(length=120), nullable=False),
        sa.Column("recommended_work_code", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "trigger_type",
            "trigger_code",
            "recommended_work_code",
            name="uq_work_recommendation_rules_trigger_work",
        ),
    )

    op.create_table(
        "work_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "trigger_type",
            postgresql.ENUM(
                "RISK_RULE",
                "FINDING",
                name="workrecommendationtriggertype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("trigger_code", sa.String(length=120), nullable=False),
        sa.Column("source_signature", sa.String(length=64), nullable=False),
        sa.Column(
            "inspection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_recommendation_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "risk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("risks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspection_findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "surface_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("surfaces.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_kind",
            sa.Enum("WALL", "FLOOR", "CEILING", "ROOM", name="workrecommendationtargetkind"),
            nullable=False,
        ),
        sa.Column("recommended_work_code", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACCEPTED", "DISMISSED", name="workrecommendationstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_price_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "inspection_id",
            "trigger_type",
            "trigger_code",
            "source_signature",
            "recommended_work_code",
            name="uq_work_recommendations_identity",
        ),
    )
    op.create_index(
        "ix_work_recommendations_inspection_id", "work_recommendations", ["inspection_id"]
    )
    op.create_index(
        "ix_work_recommendations_rule_id", "work_recommendations", ["rule_id"]
    )
    op.create_index(
        "ix_work_recommendations_risk_id", "work_recommendations", ["risk_id"]
    )
    op.create_index(
        "ix_work_recommendations_room_id", "work_recommendations", ["room_id"]
    )
    op.create_index(
        "ix_work_recommendations_surface_id", "work_recommendations", ["surface_id"]
    )
    op.create_index(
        "ix_work_recommendations_inspection_active",
        "work_recommendations",
        ["inspection_id", "is_active"],
    )
    op.create_index(
        "ix_work_recommendations_room_active",
        "work_recommendations",
        ["room_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_work_recommendations_room_active", table_name="work_recommendations"
    )
    op.drop_index(
        "ix_work_recommendations_inspection_active", table_name="work_recommendations"
    )
    op.drop_index(
        "ix_work_recommendations_surface_id", table_name="work_recommendations"
    )
    op.drop_index("ix_work_recommendations_room_id", table_name="work_recommendations")
    op.drop_index("ix_work_recommendations_risk_id", table_name="work_recommendations")
    op.drop_index("ix_work_recommendations_rule_id", table_name="work_recommendations")
    op.drop_index(
        "ix_work_recommendations_inspection_id", table_name="work_recommendations"
    )
    op.drop_table("work_recommendations")
    op.drop_table("work_recommendation_rules")
    op.execute("DROP TYPE IF EXISTS workrecommendationstatus")
    op.execute("DROP TYPE IF EXISTS workrecommendationtargetkind")
    op.execute("DROP TYPE IF EXISTS workrecommendationtriggertype")
