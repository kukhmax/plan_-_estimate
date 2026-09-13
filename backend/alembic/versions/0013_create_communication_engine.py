"""create communication engine tables

Revision ID: 0013_create_communication_engine
Revises: 0012_create_risk_engine
Create Date: 2026-09-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013_create_communication_engine"
down_revision: Union[str, None] = "0012_create_risk_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "communication_phrases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "category",
            sa.Enum(
                "EXPLAIN_CONDITION",
                "EXPLAIN_CONSEQUENCE",
                "RECOMMEND_PREPARATION",
                "REQUIRE_CLIENT_DECISION",
                "SCOPE_CLARIFICATION",
                "QUALITY_EXPECTATION",
                "DOCUMENT_AGREEMENT",
                "GENERAL",
                name="communicationcategory",
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("risk_code", sa.String(length=120), nullable=True),
        sa.Column("finding_key", sa.String(length=120), nullable=True),
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
        sa.Column(
            "quality_level",
            # The qualitylevel type is owned by revision 0011; do not re-create it.
            postgresql.ENUM(
                "S1",
                "S2",
                "S3",
                "S4",
                "Q1",
                "Q2",
                "Q3",
                "Q4",
                name="qualitylevel",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("phrase_key", sa.String(length=255), nullable=False),
        sa.Column("why_key", sa.String(length=255), nullable=True),
        sa.Column("seed_key", sa.String(length=255), nullable=True),
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
        sa.UniqueConstraint("code", "version", name="uq_communication_phrases_code_version"),
    )
    op.create_index(
        "ix_communication_phrases_active_category",
        "communication_phrases",
        ["active", "category"],
    )
    op.create_table(
        "communication_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "inspection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phrase_code", sa.String(length=120), nullable=False),
        sa.Column("phrase_version", sa.Integer(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "EXPLAIN_CONDITION",
                "EXPLAIN_CONSEQUENCE",
                "RECOMMEND_PREPARATION",
                "REQUIRE_CLIENT_DECISION",
                "SCOPE_CLARIFICATION",
                "QUALITY_EXPECTATION",
                "DOCUMENT_AGREEMENT",
                "GENERAL",
                name="communicationcategory",
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("phrase_key", sa.String(length=255), nullable=False),
        sa.Column("why_key", sa.String(length=255), nullable=True),
        sa.Column("seed_key", sa.String(length=255), nullable=True),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_signature", sa.String(length=64), nullable=False),
        sa.Column(
            "risk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("risks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("finding_key_snapshot", sa.String(length=120), nullable=True),
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
            "phrase_code",
            "source_signature",
            name="uq_communication_applications_inspection_phrase_signature",
        ),
    )
    op.create_index(
        "ix_communication_applications_inspection_id",
        "communication_applications",
        ["inspection_id"],
    )
    op.create_index(
        "ix_communication_applications_inspection_active",
        "communication_applications",
        ["inspection_id", "is_active"],
    )
    op.create_index(
        "ix_communication_applications_risk_id",
        "communication_applications",
        ["risk_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_communication_applications_risk_id",
        table_name="communication_applications",
    )
    op.drop_index(
        "ix_communication_applications_inspection_active",
        table_name="communication_applications",
    )
    op.drop_index(
        "ix_communication_applications_inspection_id",
        table_name="communication_applications",
    )
    op.drop_table("communication_applications")
    op.drop_index(
        "ix_communication_phrases_active_category",
        table_name="communication_phrases",
    )
    op.drop_table("communication_phrases")
    op.execute("DROP TYPE IF EXISTS communicationcategory")
    # NOTE: "substrate" and "qualitylevel" enums are owned by 0011 and
    # intentionally left intact.