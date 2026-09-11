"""create inspection engine tables

Revision ID: 0011_create_inspection_engine
Revises: 0010_create_area_segments_table
Create Date: 2026-09-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_create_inspection_engine"
down_revision: Union[str, None] = "0010_create_area_segments_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "checklist_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "substrate",
            sa.Enum(
                "CONCRETE",
                "GYPSUM_PLASTER",
                "CEMENT_LIME_PLASTER",
                "GYPSUM_BOARD",
                "PAINTED",
                "OTHER",
                name="substrate",
            ),
            nullable=True,
        ),
        sa.Column("title_key", sa.String(length=255), nullable=False),
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
        sa.UniqueConstraint("code", "version", name="uq_checklist_templates_code_version"),
    )
    op.create_table(
        "checklist_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title_key", sa.String(length=255), nullable=False),
        sa.Column("description_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_checklist_sections_template_id", "checklist_sections", ["template_id"]
    )
    op.create_index(
        "ix_checklist_sections_template_position",
        "checklist_sections",
        ["template_id", "position"],
    )
    op.create_table(
        "checklist_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_sections.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("text_key", sa.String(length=255), nullable=False),
        sa.Column("hint_key", sa.String(length=255), nullable=True),
        sa.Column("unit_key", sa.String(length=50), nullable=True),
        sa.Column(
            "answer_type",
            sa.Enum(
                "BOOLEAN",
                "SINGLE_CHOICE",
                "MULTI_CHOICE",
                "NUMBER",
                "TEXT",
                name="answertype",
            ),
            nullable=False,
        ),
        sa.Column("finding_key", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_checklist_questions_template_id", "checklist_questions", ["template_id"]
    )
    op.create_index(
        "ix_checklist_questions_section_id", "checklist_questions", ["section_id"]
    )
    op.create_index(
        "ix_checklist_questions_template_section_position",
        "checklist_questions",
        ["template_id", "section_id", "position"],
    )
    op.create_table(
        "checklist_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("label_key", sa.String(length=255), nullable=False),
        sa.Column("finding_key", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_checklist_options_question_id", "checklist_options", ["question_id"])
    op.create_index(
        "ix_checklist_options_question_position",
        "checklist_options",
        ["question_id", "position"],
    )
    op.create_table(
        "inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
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
            # The areaplane type is owned by revision 0010; do not re-create it.
            "plane",
            postgresql.ENUM("FLOOR", "CEILING", name="areaplane", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "substrate",
            sa.Enum(
                "CONCRETE",
                "GYPSUM_PLASTER",
                "CEMENT_LIME_PLASTER",
                "GYPSUM_BOARD",
                "PAINTED",
                "OTHER",
                name="substrate",
            ),
            nullable=False,
        ),
        sa.Column(
            "quality_target",
            sa.Enum("S1", "S2", "S3", "S4", "Q1", "Q2", "Q3", "Q4", name="qualitylevel"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "COMPLETED", name="inspectionstatus"),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column("notes", sa.String(length=4096), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
    )
    op.create_index("ix_inspections_room_id", "inspections", ["room_id"])
    op.create_index(
        "ix_inspections_room_archived", "inspections", ["room_id", "is_archived"]
    )
    op.create_index("ix_inspections_surface_id", "inspections", ["surface_id"])
    op.create_index(
        "ix_inspections_surface_room", "inspections", ["surface_id", "room_id"]
    )
    op.create_table(
        "inspection_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "inspection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.Column("value_number", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("value_text", sa.String(length=4096), nullable=True),
        sa.Column("option_key", sa.String(length=120), nullable=True),
        sa.Column("option_keys", sa.JSON(), nullable=True),
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
            "question_id",
            name="uq_inspection_answers_inspection_question",
        ),
    )
    op.create_index("ix_inspection_answers_inspection_id", "inspection_answers", ["inspection_id"])
    op.create_table(
        "inspection_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "inspection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "answer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inspection_answers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checklist_questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("finding_key", sa.String(length=120), nullable=False),
        sa.Column("label_key", sa.String(length=255), nullable=True),
        sa.Column("value_snapshot", sa.JSON(), nullable=True),
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
    )
    op.create_index(
        "ix_inspection_findings_inspection_id", "inspection_findings", ["inspection_id"]
    )
    op.create_index(
        "ix_inspection_findings_inspection_active",
        "inspection_findings",
        ["inspection_id", "is_active"],
    )
    op.create_index("ix_inspection_findings_key", "inspection_findings", ["finding_key"])


def downgrade() -> None:
    op.drop_index("ix_inspection_findings_key", table_name="inspection_findings")
    op.drop_index(
        "ix_inspection_findings_inspection_active", table_name="inspection_findings"
    )
    op.drop_index("ix_inspection_findings_inspection_id", table_name="inspection_findings")
    op.drop_table("inspection_findings")
    op.drop_index("ix_inspection_answers_inspection_id", table_name="inspection_answers")
    op.drop_table("inspection_answers")
    op.drop_index("ix_inspections_surface_room", table_name="inspections")
    op.drop_index("ix_inspections_surface_id", table_name="inspections")
    op.drop_index("ix_inspections_room_archived", table_name="inspections")
    op.drop_index("ix_inspections_room_id", table_name="inspections")
    op.drop_table("inspections")
    op.drop_index("ix_checklist_options_question_position", table_name="checklist_options")
    op.drop_index("ix_checklist_options_question_id", table_name="checklist_options")
    op.drop_table("checklist_options")
    op.drop_index(
        "ix_checklist_questions_template_section_position", table_name="checklist_questions"
    )
    op.drop_index("ix_checklist_questions_section_id", table_name="checklist_questions")
    op.drop_index("ix_checklist_questions_template_id", table_name="checklist_questions")
    op.drop_table("checklist_questions")
    op.drop_index(
        "ix_checklist_sections_template_position", table_name="checklist_sections"
    )
    op.drop_index("ix_checklist_sections_template_id", table_name="checklist_sections")
    op.drop_table("checklist_sections")
    op.drop_table("checklist_templates")
    op.execute("DROP TYPE IF EXISTS inspectionstatus")
    op.execute("DROP TYPE IF EXISTS qualitylevel")
    op.execute("DROP TYPE IF EXISTS answertype")
    op.execute("DROP TYPE IF EXISTS substrate")
    # NOTE: "areaplane" enum is owned by 0010 and intentionally left intact.