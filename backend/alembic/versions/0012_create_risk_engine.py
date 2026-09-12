"""create risk engine tables

Revision ID: 0012_create_risk_engine
Revises: 0011_create_inspection_engine
Create Date: 2026-09-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_create_risk_engine"
down_revision: Union[str, None] = "0011_create_inspection_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "severity",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="riskseverity"),
            nullable=False,
        ),
        sa.Column(
            "blocks_finishing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "warranty_exclusion_candidate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "substrate",
            # The substrate type is owned by revision 0011; do not re-create it.
            postgresql.ENUM(
                "CONCRETE",
                "GYPSUM_PLASTER",
                "CEMENT_LIME_PLASTER",
                "GYPSUM_BOARD",
                "PAINTED",
                "OTHER",
                name="substrate",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("title_key", sa.String(length=255), nullable=False),
        sa.Column("explanation_key", sa.String(length=255), nullable=False),
        sa.Column("consequence_key", sa.String(length=255), nullable=False),
        sa.Column("mitigation_key", sa.String(length=255), nullable=False),
        sa.Column("communication_key", sa.String(length=255), nullable=False),
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
        sa.UniqueConstraint("code", "version", name="uq_risk_rules_code_version"),
    )
    op.create_table(
        "risk_rule_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("risk_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "operator",
            sa.Enum(
                "FINDING_PRESENT",
                "FINDING_ABSENT",
                "NUMBER_AT_LEAST",
                "NUMBER_AT_MOST",
                "SUBSTRATE_IN",
                "SUBSTRATE_NOT_IN",
                "TARGET_IN",
                "QUALITY_IN",
                name="riskconditionoperator",
            ),
            nullable=False,
        ),
        sa.Column("finding_key", sa.String(length=120), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_risk_rule_conditions_rule_id", "risk_rule_conditions", ["rule_id"]
    )
    op.create_index(
        "ix_risk_rule_conditions_rule_position",
        "risk_rule_conditions",
        ["rule_id", "position"],
    )
    op.create_table(
        "risks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inspection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("risk_code", sa.String(length=120), nullable=False),
        sa.Column("rule_code", sa.String(length=120), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="riskseverity"),
            nullable=False,
        ),
        sa.Column("title_key", sa.String(length=255), nullable=False),
        sa.Column("explanation_key", sa.String(length=255), nullable=False),
        sa.Column("consequence_key", sa.String(length=255), nullable=False),
        sa.Column("mitigation_key", sa.String(length=255), nullable=False),
        sa.Column("communication_key", sa.String(length=255), nullable=False),
        sa.Column(
            "warranty_exclusion_candidate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "blocks_finishing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("source_signature", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
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
            "rule_code",
            "source_signature",
            name="uq_risks_inspection_rule_signature",
        ),
    )
    op.create_index("ix_risks_room_id", "risks", ["room_id"])
    op.create_index("ix_risks_inspection_id", "risks", ["inspection_id"])
    op.create_index("ix_risks_inspection_active", "risks", ["inspection_id", "is_active"])
    op.create_index("ix_risks_room_active", "risks", ["room_id", "is_active"])
    op.create_table(
        "risk_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "risk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("risks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspection_findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("finding_key_snapshot", sa.String(length=120), nullable=False),
        sa.Column("value_snapshot", sa.JSON(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "risk_id",
            "finding_id",
            name="uq_risk_findings_risk_finding",
        ),
    )
    op.create_index("ix_risk_findings_risk_id", "risk_findings", ["risk_id"])
    op.create_index("ix_risk_findings_risk_position", "risk_findings", ["risk_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_risk_findings_risk_position", table_name="risk_findings")
    op.drop_index("ix_risk_findings_risk_id", table_name="risk_findings")
    op.drop_table("risk_findings")
    op.drop_index("ix_risks_room_active", table_name="risks")
    op.drop_index("ix_risks_inspection_active", table_name="risks")
    op.drop_index("ix_risks_inspection_id", table_name="risks")
    op.drop_index("ix_risks_room_id", table_name="risks")
    op.drop_table("risks")
    op.drop_index(
        "ix_risk_rule_conditions_rule_position", table_name="risk_rule_conditions"
    )
    op.drop_index("ix_risk_rule_conditions_rule_id", table_name="risk_rule_conditions")
    op.drop_table("risk_rule_conditions")
    op.drop_table("risk_rules")
    op.execute("DROP TYPE IF EXISTS riskconditionoperator")
    op.execute("DROP TYPE IF EXISTS riskseverity")
    # NOTE: "substrate" enum is owned by 0011 and intentionally left intact.
