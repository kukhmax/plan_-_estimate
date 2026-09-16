"""canonical floor/ceiling surfaces + area segment surface association

Revision ID: 0018_canonical_plane_surfaces
Revises: 0017_create_surface_work_plans
Create Date: 2026-09-16 12:00:00.000000

Owner architecture correction (10C.1A): FLOOR and CEILING become canonical
physical Surface entities for every room, because a stable Surface.id is the
shared physical target for Stage 10B WorkPlans and the planned
Inspection/Risk/Estimate/Photo chains. AreaSegment stays the geometry-adjustment
model and gains surface_id -> surfaces.id while keeping room_id; both columns
must agree (service validates), and measurement math is unchanged.

Staged, safe, reversible:
1. provision/reuse canonical FLOOR/CEILING Surface rows per room (abort on
   duplicate active same-plane surfaces so user rows are never merged silently)
2. add nullable area_segments.surface_id
3. backfill every existing area_segment to exactly one canonical Surface
4. add surviving FK/index and set NOT NULL (safe: every row backfilled)
5. add the partial unique index enforcing one active plane surface per room

Downgrade removes only rows the upgrade created mid-transaction (identified by
the canonical name/position/type signature), so reused user rows are preserved.
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision: str = "0018_canonical_plane_surfaces"
down_revision: Union[str, None] = "0017_create_surface_work_plans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CANONICAL_FLOOR_NAME = "Floor"
CANONICAL_CEILING_NAME = "Ceiling"
CANONICAL_FLOOR_POSITION = 100
CANONICAL_CEILING_POSITION = 101


def _provision_canonical_plane_surfaces() -> None:
    """Reuse or create exactly one active FLOOR/CEILING Surface per room.

    Rooms with multiple active same-plane surfaces abort the migration so the
    conflict can be reconciled manually instead of silently merging user rows.
    """
    bind = op.get_bind()
    room_ids = [
        row[0]
        for row in bind.execute(text("SELECT id FROM rooms ORDER BY created_at"))
    ]
    for room_id in room_ids:
        for surface_type, name, position in (
            ("FLOOR", CANONICAL_FLOOR_NAME, CANONICAL_FLOOR_POSITION),
            ("CEILING", CANONICAL_CEILING_NAME, CANONICAL_CEILING_POSITION),
        ):
            active = bind.execute(
                text(
                    "SELECT id FROM surfaces "
                    "WHERE room_id = :room_id AND surface_type = :stmt "
                    "AND is_archived = false ORDER BY position NULLS LAST, created_at"
                ),
                {"room_id": room_id, "stmt": surface_type},
            ).all()
            if len(active) > 1:
                raise RuntimeError(
                    f"Room {room_id} has {len(active)} active {surface_type} "
                    "surfaces; reconcile them manually before applying 0018"
                )
            if len(active) == 1:
                continue
            bind.execute(
                text(
                    "INSERT INTO surfaces "
                    "(id, room_id, name, surface_type, description, position, "
                    "is_archived, created_at, updated_at) "
                    "VALUES (:id, :room_id, :name, :surface_type, NULL, :position, "
                    "false, now(), now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "room_id": room_id,
                    "name": name,
                    "surface_type": surface_type,
                    "position": position,
                },
            )


def _backfill_area_segment_surface_ids() -> None:
    """Associate every area_segment with its room's canonical plane surface."""
    bind = op.get_bind()
    rows = bind.execute(
        text("SELECT id, room_id, plane FROM area_segments ORDER BY created_at")
    ).all()
    for segment_id, room_id, plane in rows:
        resolved = bind.execute(
            text(
                "SELECT id FROM surfaces "
                "WHERE room_id = :room_id AND surface_type = :plane "
                "AND is_archived = false ORDER BY position NULLS LAST, created_at"
            ),
            {"room_id": room_id, "plane": plane},
        ).first()
        if resolved is None:
            raise RuntimeError(
                f"Area segment {segment_id} has no canonical {plane} surface"
            )
        bind.execute(
            text("UPDATE area_segments SET surface_id = :surface_id WHERE id = :id"),
            {"surface_id": resolved[0], "id": segment_id},
        )


def upgrade() -> None:
    _provision_canonical_plane_surfaces()

    op.add_column(
        "area_segments",
        sa.Column("surface_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _backfill_area_segment_surface_ids()
    op.alter_column("area_segments", "surface_id", nullable=False)
    op.create_foreign_key(
        "fk_area_segments_surface_id",
        "area_segments",
        "surfaces",
        ["surface_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_area_segments_surface_id", "area_segments", ["surface_id"])
    op.create_index(
        "uq_surfaces_active_plane_per_room",
        "surfaces",
        ["room_id", "surface_type"],
        unique=True,
        postgresql_where=text(
            "surface_type IN ('FLOOR', 'CEILING') AND is_archived = false"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_surfaces_active_plane_per_room",
        table_name="surfaces",
    )
    op.drop_index("ix_area_segments_surface_id", table_name="area_segments")
    op.drop_constraint(
        "fk_area_segments_surface_id", "area_segments", type_="foreignkey"
    )
    op.drop_column("area_segments", "surface_id")
    # Remove only the canonical plane rows the upgrade just inserted; user rows
    # that the upgrade reused are identified by their non-canonical signatures
    # and therefore preserved.
    op.get_bind().execute(
        text(
            "DELETE FROM surfaces WHERE is_archived = false AND ("
            "(surface_type = 'FLOOR' AND name = :floor_name "
            "AND position = :floor_pos) OR "
            "(surface_type = 'CEILING' AND name = :ceiling_name "
            "AND position = :ceiling_pos))"
        ),
        {
            "floor_name": CANONICAL_FLOOR_NAME,
            "floor_pos": CANONICAL_FLOOR_POSITION,
            "ceiling_name": CANONICAL_CEILING_NAME,
            "ceiling_pos": CANONICAL_CEILING_POSITION,
        },
    )