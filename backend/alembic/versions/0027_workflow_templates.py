"""workflow templates, provenance, breaks and occurrence identity (Stage 13B)

Revision ID: 0027_workflow_templates
Revises: 0026_coefficient_descriptions
Create Date: 2026-09-25 18:00:00.000000

See docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §14, §18, §22.

1. workflow_templates -- owner-scoped technological recipes.
2. workflow_template_steps -- ordered steps referencing price_items directly.
3. surface_work_plan_template_applications -- historical provenance on the
   durable surface_work_plans header (snapshot; template link SET NULL).
4. surface_planned_works.wait_after_hours -- nullable technological break
   (hours >= 1).
5. surface_planned_works.occurrence_key -- stable logical occurrence identity
   (D13): added nullable, every existing row backfilled with an independent
   uuid4 generated here in Python (not derived from any other column and not
   relying on ORM defaults or a database UUID extension), verified to leave no
   NULL, then made NOT NULL and globally UNIQUE.

The backfill writes only occurrence_key. No planned work is deleted or
reordered; PriceItem/WorkPlan references, Stage 12 coefficient assignments
and Estimate data are untouched.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0027_workflow_templates"
down_revision: Union[str, None] = "0026_coefficient_descriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BACKFILL_BATCH = 1000


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def _backfill_occurrence_keys() -> None:
    bind = op.get_bind()
    ids = bind.execute(
        sa.text("SELECT id FROM surface_planned_works WHERE occurrence_key IS NULL")
    ).scalars().all()
    update = sa.text(
        "UPDATE surface_planned_works SET occurrence_key = :key WHERE id = :id"
    ).bindparams(
        sa.bindparam("key", type_=postgresql.UUID(as_uuid=True)),
        sa.bindparam("id", type_=postgresql.UUID(as_uuid=True)),
    )
    for start in range(0, len(ids), _BACKFILL_BATCH):
        batch = ids[start : start + _BACKFILL_BATCH]
        bind.execute(update, [{"key": uuid.uuid4(), "id": row_id} for row_id in batch])
    remaining = bind.execute(
        sa.text("SELECT count(*) FROM surface_planned_works WHERE occurrence_key IS NULL")
    ).scalar_one()
    if remaining:
        raise RuntimeError(
            f"occurrence_key backfill left {remaining} surface_planned_works rows NULL"
        )


def upgrade() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name_key", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("applies_to_substrates", sa.JSON(), nullable=True),
        sa.Column("applies_to_quality", sa.JSON(), nullable=True),
        sa.Column("applies_to_surface_types", sa.JSON(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        sa.UniqueConstraint("owner_id", "code", name="uq_workflow_templates_owner_code"),
    )
    op.create_index("ix_workflow_templates_owner_id", "workflow_templates", ["owner_id"])
    op.create_index(
        "ix_workflow_templates_owner_archived",
        "workflow_templates",
        ["owner_id", "is_archived"],
    )

    op.create_table(
        "workflow_template_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "price_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("wait_after_hours", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "template_id", "position", name="uq_workflow_template_steps_template_position"
        ),
        sa.CheckConstraint(
            "wait_after_hours IS NULL OR wait_after_hours >= 1",
            name="ck_workflow_template_steps_wait_after_hours",
        ),
    )
    op.create_index(
        "ix_workflow_template_steps_template_id", "workflow_template_steps", ["template_id"]
    )
    op.create_index(
        "ix_workflow_template_steps_price_item_id", "workflow_template_steps", ["price_item_id"]
    )

    op.create_table(
        "surface_work_plan_template_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "work_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("surface_work_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("template_code", sa.String(length=120), nullable=False),
        sa.Column("template_name", sa.String(length=255), nullable=False),
        sa.Column(
            "mode",
            sa.Enum("APPEND", "REPLACE", name="templateapplicationmode"),
            nullable=False,
        ),
        sa.Column("steps_applied", sa.Integer(), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "steps_applied >= 0",
            name="ck_surface_work_plan_template_applications_steps_applied",
        ),
    )
    op.create_index(
        "ix_surface_work_plan_template_applications_work_plan_id",
        "surface_work_plan_template_applications",
        ["work_plan_id"],
    )
    op.create_index(
        "ix_surface_work_plan_template_applications_template_id",
        "surface_work_plan_template_applications",
        ["template_id"],
    )

    op.add_column(
        "surface_planned_works",
        sa.Column("wait_after_hours", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_surface_planned_works_wait_after_hours",
        "surface_planned_works",
        "wait_after_hours IS NULL OR wait_after_hours >= 1",
    )

    op.add_column(
        "surface_planned_works",
        sa.Column("occurrence_key", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _backfill_occurrence_keys()
    op.alter_column("surface_planned_works", "occurrence_key", nullable=False)
    op.create_index(
        "uq_surface_planned_works_occurrence_key",
        "surface_planned_works",
        ["occurrence_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_surface_planned_works_occurrence_key", table_name="surface_planned_works"
    )
    op.drop_column("surface_planned_works", "occurrence_key")
    op.drop_constraint(
        "ck_surface_planned_works_wait_after_hours",
        "surface_planned_works",
        type_="check",
    )
    op.drop_column("surface_planned_works", "wait_after_hours")

    op.drop_index(
        "ix_surface_work_plan_template_applications_template_id",
        table_name="surface_work_plan_template_applications",
    )
    op.drop_index(
        "ix_surface_work_plan_template_applications_work_plan_id",
        table_name="surface_work_plan_template_applications",
    )
    op.drop_table("surface_work_plan_template_applications")
    op.execute("DROP TYPE IF EXISTS templateapplicationmode")

    op.drop_index(
        "ix_workflow_template_steps_price_item_id", table_name="workflow_template_steps"
    )
    op.drop_index(
        "ix_workflow_template_steps_template_id", table_name="workflow_template_steps"
    )
    op.drop_table("workflow_template_steps")

    op.drop_index("ix_workflow_templates_owner_archived", table_name="workflow_templates")
    op.drop_index("ix_workflow_templates_owner_id", table_name="workflow_templates")
    op.drop_table("workflow_templates")
