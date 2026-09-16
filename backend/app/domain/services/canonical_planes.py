"""Canonical physical FLOOR/CEILING surface provisioning (Stage 10C.1A).

Every Room conceptually owns exactly one active canonical FLOOR Surface and
exactly one active canonical CEILING Surface. AreaSegments are geometry
adjustments attached to those physical targets (AreaSegment.surface_id), so
WorkPlans, inspections, risks, estimates and photos can all reference the same
stable Surface identity. Names follow the language-neutral WALL convention
("Wall 1" ... "Wall 4") used by generate_canonical_walls.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import CanonicalPlaneConflictError
from app.models.surface import Surface, SurfaceType

CANONICAL_FLOOR_NAME = "Floor"
CANONICAL_CEILING_NAME = "Ceiling"
# Positions past the canonical walls (0..3) and past normal manual surfaces.
CANONICAL_FLOOR_POSITION = 100
CANONICAL_CEILING_POSITION = 101


def canonical_name(surface_type: SurfaceType) -> str:
    if surface_type is SurfaceType.FLOOR:
        return CANONICAL_FLOOR_NAME
    if surface_type is SurfaceType.CEILING:
        return CANONICAL_CEILING_NAME
    raise ValueError(f"surface_type must be FLOOR or CEILING, got {surface_type}")


def canonical_position(surface_type: SurfaceType) -> int:
    if surface_type is SurfaceType.FLOOR:
        return CANONICAL_FLOOR_POSITION
    if surface_type is SurfaceType.CEILING:
        return CANONICAL_CEILING_POSITION
    raise ValueError(f"surface_type must be FLOOR or CEILING, got {surface_type}")


async def find_active_plane_surface(
    db: AsyncSession,
    room_id: uuid.UUID,
    surface_type: SurfaceType,
) -> Surface | None:
    """Return the room's first active surface of the given plane type, or None."""
    stmt = (
        select(Surface)
        .where(
            Surface.room_id == room_id,
            Surface.surface_type == surface_type,
            Surface.is_archived.is_(False),
        )
        .order_by(Surface.position.asc().nulls_last(), Surface.created_at.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def ensure_canonical_plane_surfaces(
    db: AsyncSession,
    room_id: uuid.UUID,
) -> tuple[Surface, Surface]:
    """Idempotently provision one active FLOOR and one active CEILING surface.

    A legitimate existing active plane surface is reused by identity; nothing
    is ever duplicated. Multi-surface rooms are data corruption and abort with
    CanonicalPlaneConflictError (the partial unique index is the backstop).
    """
    provisioned: list[Surface] = []
    for surface_type in (SurfaceType.FLOOR, SurfaceType.CEILING):
        existing = await find_active_plane_surface(db, room_id, surface_type)
        if existing is None:
            new_surface = Surface(
                room_id=room_id,
                name=canonical_name(surface_type),
                surface_type=surface_type,
                description=None,
                position=canonical_position(surface_type),
            )
            db.add(new_surface)
            provisioned.append(new_surface)
            continue
        duplicate = (
            await db.execute(
                select(Surface.id)
                .where(
                    Surface.room_id == room_id,
                    Surface.surface_type == surface_type,
                    Surface.is_archived.is_(False),
                    Surface.id != existing.id,
                )
                .limit(1)
            )
        ).first()
        if duplicate is not None:
            raise CanonicalPlaneConflictError(
                f"Room {room_id} has multiple active {surface_type.value} surfaces"
            )
        provisioned.append(existing)
    await db.flush()
    return tuple(provisioned)  # type: ignore[return-value]