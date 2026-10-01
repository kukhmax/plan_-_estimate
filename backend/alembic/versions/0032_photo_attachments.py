"""photo attachments (Stage 14C.2)

Revision ID: 0032_photo_attachments
Revises: 0031_photo_assets
Create Date: 2026-09-28 22:00:00.000000

Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §4–§8.

Creates photo_attachments -- one PhotoAsset placed in one business context
(leaf-only typed nullable FKs + context enum + one row-local seven-branch
CHECK). All seven contexts exist in the schema for forward compatibility;
the Stage 14C API enables only PROJECT/ROOM/SURFACE/OPENING.

Every evidence parent is ON DELETE RESTRICT, including question_id (owner
decision R-2, replaces the 14A SET NULL). occurrence_key has no FK (Stage 13
durable key). Active-row uniqueness uses one partial unique index per context
(two for INSPECTION: question-less and question-level).

Creates an EMPTY table; photo_assets and every other table are untouched.
Downgrade drops the table, its indexes and the two enum types only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0032_photo_attachments"
down_revision: Union[str, None] = "0031_photo_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTEXTS = ("PROJECT", "ROOM", "SURFACE", "OPENING", "INSPECTION", "FINDING", "WORK")
CATEGORIES = (
    "GENERAL",
    "BEFORE",
    "DEFECT",
    "PREPARATION",
    "IN_PROGRESS",
    "HIDDEN_WORK",
    "AFTER",
    "DAMAGE",
)

CONTEXT_TARGETS_CHECK = (
    "(context = 'PROJECT' AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'ROOM' AND room_id IS NOT NULL AND surface_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'SURFACE' AND surface_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'OPENING' AND opening_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'INSPECTION' AND inspection_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND opening_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'FINDING' AND finding_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'WORK' AND surface_id IS NOT NULL AND occurrence_key IS NOT NULL"
    " AND price_item_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL)"
)

ACTIVE_UNIQUE_INDEXES = (
    ("uq_photo_att_project_active", ["asset_id"], "context = 'PROJECT'"),
    ("uq_photo_att_room_active", ["asset_id", "room_id"], "context = 'ROOM'"),
    ("uq_photo_att_surface_active", ["asset_id", "surface_id"], "context = 'SURFACE'"),
    ("uq_photo_att_opening_active", ["asset_id", "opening_id"], "context = 'OPENING'"),
    (
        "uq_photo_att_inspection_active",
        ["asset_id", "inspection_id"],
        "context = 'INSPECTION' AND question_id IS NULL",
    ),
    (
        "uq_photo_att_inspection_question_active",
        ["asset_id", "inspection_id", "question_id"],
        "context = 'INSPECTION' AND question_id IS NOT NULL",
    ),
    ("uq_photo_att_finding_active", ["asset_id", "finding_id"], "context = 'FINDING'"),
    ("uq_photo_att_work_active", ["asset_id", "surface_id", "occurrence_key"], "context = 'WORK'"),
)

LOOKUP_INDEXES = (
    ("ix_photo_attachments_project_context_archived", ["project_id", "context", "archived_at"]),
    ("ix_photo_attachments_asset_id", ["asset_id"]),
    ("ix_photo_attachments_room_id", ["room_id"]),
    ("ix_photo_attachments_surface_id", ["surface_id"]),
    ("ix_photo_attachments_opening_id", ["opening_id"]),
    ("ix_photo_attachments_inspection_id", ["inspection_id"]),
    ("ix_photo_attachments_finding_id", ["finding_id"]),
    ("ix_photo_attachments_surface_occurrence", ["surface_id", "occurrence_key"]),
)


def _fk(table: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{table}.id", ondelete="RESTRICT")


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        "photo_attachments",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("asset_id", uuid_type, _fk("photo_assets"), nullable=False),
        sa.Column("project_id", uuid_type, _fk("projects"), nullable=False),
        sa.Column("context", sa.Enum(*CONTEXTS, name="photoattachmentcontext"), nullable=False),
        sa.Column("room_id", uuid_type, _fk("rooms"), nullable=True),
        sa.Column("surface_id", uuid_type, _fk("surfaces"), nullable=True),
        sa.Column("opening_id", uuid_type, _fk("openings"), nullable=True),
        sa.Column("inspection_id", uuid_type, _fk("inspections"), nullable=True),
        # R-2: RESTRICT, not SET NULL -- evidence must not silently change meaning.
        sa.Column("question_id", uuid_type, _fk("checklist_questions"), nullable=True),
        sa.Column("finding_id", uuid_type, _fk("inspection_findings"), nullable=True),
        # Stage 13 durable occurrence identity; intentionally no FK.
        sa.Column("occurrence_key", uuid_type, nullable=True),
        sa.Column("price_item_id", uuid_type, _fk("price_items"), nullable=True),
        sa.Column("category", sa.Enum(*CATEGORIES, name="photocategory"), nullable=False),
        sa.Column("caption", sa.String(1000), nullable=True),
        sa.Column(
            "include_in_report", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(CONTEXT_TARGETS_CHECK, name="ck_photo_attachments_context_targets"),
        sa.CheckConstraint("position >= 0", name="ck_photo_attachments_position_nonneg"),
    )
    for name, columns, predicate in ACTIVE_UNIQUE_INDEXES:
        where = sa.text(f"{predicate} AND archived_at IS NULL")
        op.create_index(
            name,
            "photo_attachments",
            columns,
            unique=True,
            sqlite_where=where,
            postgresql_where=where,
        )
    for name, columns in LOOKUP_INDEXES:
        op.create_index(name, "photo_attachments", columns)


def downgrade() -> None:
    for name, _columns in reversed(LOOKUP_INDEXES):
        op.drop_index(name, table_name="photo_attachments")
    for name, _columns, _predicate in reversed(ACTIVE_UNIQUE_INDEXES):
        op.drop_index(name, table_name="photo_attachments")
    op.drop_table("photo_attachments")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS photocategory")
        op.execute("DROP TYPE IF EXISTS photoattachmentcontext")
