"""pressure_test_protocols: the protocol of a pressure test and its journal kind (V2-12b)

Revision ID: 0082_pressure_tests
Revises: 0081_installation_map_doc
Create Date: 2026-11-02 10:00:00.000000

One NEW table: a test of one installation (water, heating, gas, sewer) under pressure, recorded before it is covered: the day, the people present or the day the absent customer was
notified, the system and the place (the place is free text, so a TEXT column that the data encryption keeps, like the other texts of an object), the medium, the test pressure, the time
held, the drop of the pressure, the photos of the manometer (attachments of the object), the result and the remarks; the frozen columns of an issued protocol (time, snapshot, exact
page). At most one DRAFT per object, `sequence` unique per object, an ISSUED protocol always has its time, snapshot and page. Widens `ck_issued_documents_kind` with
'PRESSURE_TEST_PROTOCOL' (the number prefix PPC). It goes with its object (`ON DELETE CASCADE`). No existing row changes.

Reversible: the downgrade **refuses** (rather than deletes) while any protocol or a journal row of this kind exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0082_pressure_tests"
down_revision: str | None = "0081_installation_map_doc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT', 'MEASUREMENTS', 'PAYMENT_SCHEDULE', 'INSTALLATION_MAP', 'PRESSURE_TEST_PROTOCOL')"
)
KINDS_OLD = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT', 'MEASUREMENTS', 'PAYMENT_SCHEDULE', 'INSTALLATION_MAP')"
)


def upgrade() -> None:
    op.create_table(
        "pressure_test_protocols",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("held_on", sa.Date, nullable=True),
        sa.Column("held_time", sa.String(5), nullable=True),
        sa.Column("customer_absent", sa.Boolean, nullable=False),
        sa.Column("notified_on", sa.Date, nullable=True),
        sa.Column("attendees", JSON, nullable=False),
        sa.Column("system", sa.String(16), nullable=True),
        sa.Column("section", sa.Text, nullable=True),
        sa.Column("medium", sa.String(8), nullable=True),
        sa.Column("test_pressure_bar", sa.Numeric(6, 2), nullable=True),
        sa.Column("duration_min", sa.Integer, nullable=True),
        sa.Column("pressure_drop_bar", sa.Numeric(6, 2), nullable=True),
        sa.Column("photo_ids", JSON, nullable=False),
        sa.Column("result", sa.String(16), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", JSON, nullable=True),
        sa.Column("document_html", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_pressure_tests_status"),
        sa.CheckConstraint("sequence >= 1", name="ck_pressure_tests_sequence_positive"),
        sa.CheckConstraint("system IS NULL OR system IN ('COLD_WATER', 'HOT_WATER', 'HEATING', 'GAS', 'SEWER')", name="ck_pressure_tests_system"),
        sa.CheckConstraint("medium IS NULL OR medium IN ('WATER', 'AIR')", name="ck_pressure_tests_medium"),
        sa.CheckConstraint("result IS NULL OR result IN ('POSITIVE', 'NEGATIVE')", name="ck_pressure_tests_result"),
        sa.CheckConstraint("test_pressure_bar IS NULL OR (test_pressure_bar > 0 AND test_pressure_bar <= 100)", name="ck_pressure_tests_pressure"),
        sa.CheckConstraint("duration_min IS NULL OR (duration_min > 0 AND duration_min <= 1440)", name="ck_pressure_tests_duration"),
        sa.CheckConstraint("pressure_drop_bar IS NULL OR (pressure_drop_bar >= 0 AND pressure_drop_bar <= 100)", name="ck_pressure_tests_drop"),
        sa.CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_pressure_tests_frozen_when_issued",
        ),
        sa.UniqueConstraint("project_id", "sequence", name="uq_pressure_tests_project_sequence"),
    )
    op.create_index(
        "uq_pressure_tests_one_draft", "pressure_test_protocols", ["project_id"], unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"), sqlite_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index("ix_pressure_tests_project", "pressure_test_protocols", ["project_id", "status"])
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    protocols = bind.execute(sa.text("SELECT count(*) FROM pressure_test_protocols")).scalar_one()
    journal = bind.execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'PRESSURE_TEST_PROTOCOL'")).scalar_one()
    if protocols or journal:
        raise RuntimeError(
            f"cannot downgrade: {protocols} pressure test protocol(s) and {journal} journal row(s) exist; they are evidence and are never dropped silently"
        )
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
    op.drop_index("ix_pressure_tests_project", table_name="pressure_test_protocols")
    op.drop_index("uq_pressure_tests_one_draft", table_name="pressure_test_protocols")
    op.drop_table("pressure_test_protocols")
