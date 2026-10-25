"""V2-9: the payment schedule by stages, the work hours and the hourly rate

Revision ID: 0075_payment_schedule
Revises: 0074_measurements_document
Create Date: 2026-10-28 10:00:00.000000

Two NEW tables: `payment_stages` (a line of the owner's schedule: a title, a share in percent OR a fixed amount, an optional due day) and `work_hours` (an entry of the
owner's work log of an object: a day, the hours, a note). Both go with their object (`ON DELETE CASCADE`); the titles and the notes are free text, so they are TEXT
columns that the data encryption keeps (like the other records of an object).
Two NEW nullable columns: `project_payments.stage_id` (the stage an advance or a payment was received for; `ON DELETE SET NULL`: deleting a stage never takes the money
with it; only an advance or a payment may have one) and `executor_profiles.hourly_rate` (the owner's rate per hour, optional, > 0).
No existing row changes.

Reversible: the downgrade **refuses** (rather than deletes) while a stage or an hour entry exists -- they are the owner's own input and are never dropped silently.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0075_payment_schedule"
down_revision: str | None = "0074_measurements_document"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_stages",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("due_on", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(percent IS NOT NULL AND amount IS NULL) OR (percent IS NULL AND amount IS NOT NULL)", name="ck_payment_stages_percent_xor_amount"
        ),
        sa.CheckConstraint("percent IS NULL OR (percent > 0 AND percent <= 100)", name="ck_payment_stages_percent_range"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_payment_stages_amount_positive"),
        sa.CheckConstraint("position >= 0", name="ck_payment_stages_position"),
    )
    op.create_index("ix_payment_stages_project", "payment_stages", ["project_id", "due_on"])
    op.create_table(
        "work_hours",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("worked_on", sa.Date, nullable=False),
        sa.Column("hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("hours > 0 AND hours <= 24", name="ck_work_hours_range"),
    )
    op.create_index("ix_work_hours_project", "work_hours", ["project_id", "worked_on"])
    with op.batch_alter_table("project_payments") as batch:
        batch.add_column(sa.Column("stage_id", sa.Uuid, nullable=True))
        batch.create_foreign_key("fk_project_payments_stage", "payment_stages", ["stage_id"], ["id"], ondelete="SET NULL")
        batch.create_check_constraint("ck_project_payments_stage_only_money_in", "stage_id IS NULL OR kind IN ('ADVANCE', 'PAYMENT')")
        batch.create_index("ix_project_payments_stage", ["stage_id"])
    with op.batch_alter_table("executor_profiles") as batch:
        batch.add_column(sa.Column("hourly_rate", sa.Numeric(8, 2), nullable=True))
        batch.create_check_constraint("ck_executor_profiles_hourly_rate", "hourly_rate IS NULL OR hourly_rate > 0")


def downgrade() -> None:
    bind = op.get_bind()
    stages = bind.execute(sa.text("SELECT count(*) FROM payment_stages")).scalar_one()
    hours = bind.execute(sa.text("SELECT count(*) FROM work_hours")).scalar_one()
    if stages or hours:
        raise RuntimeError(
            f"cannot downgrade: {stages} payment stage(s) and {hours} hour entr(ies) exist; they are the owner's own input and are never dropped silently"
        )
    with op.batch_alter_table("executor_profiles") as batch:
        batch.drop_constraint("ck_executor_profiles_hourly_rate", type_="check")
        batch.drop_column("hourly_rate")
    with op.batch_alter_table("project_payments") as batch:
        batch.drop_index("ix_project_payments_stage")
        batch.drop_constraint("ck_project_payments_stage_only_money_in", type_="check")
        batch.drop_constraint("fk_project_payments_stage", type_="foreignkey")
        batch.drop_column("stage_id")
    op.drop_index("ix_work_hours_project", table_name="work_hours")
    op.drop_table("work_hours")
    op.drop_index("ix_payment_stages_project", table_name="payment_stages")
    op.drop_table("payment_stages")
