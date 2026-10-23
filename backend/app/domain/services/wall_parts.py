"""What a merged wall adds to a wall of the room: its parts, the summed area, and the wall sizes the totals of a room use (see wall_merge_service)."""

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.surface import Surface, SurfaceType
from app.models.surface_part import SurfacePart

AREA = Decimal("0.001")


def parts_gross_area(parts: list[SurfacePart]) -> Decimal:
    """The gross area of a merged wall: each part rounded like a wall of its own, then summed."""
    return sum(((part.width * part.height).quantize(AREA) for part in parts), Decimal("0.000"))


async def load_parts(db: AsyncSession, surface_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[SurfacePart]]:
    """The parts of the given walls, in order; a wall that is not merged has no entry."""
    if not surface_ids:
        return {}
    rows = (
        await db.execute(
            select(SurfacePart).where(SurfacePart.surface_id.in_(surface_ids)).order_by(SurfacePart.surface_id, SurfacePart.position)
        )
    ).scalars()
    found: dict[uuid.UUID, list[SurfacePart]] = defaultdict(list)
    for part in rows:
        found[part.surface_id].append(part)
    return dict(found)


async def merged_into(db: AsyncSession, surface_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """For each wall that was joined into another one: the merged wall it is part of."""
    if not surface_ids:
        return {}
    rows = (
        await db.execute(
            select(SurfacePart.source_surface_id, SurfacePart.surface_id).where(
                SurfacePart.source_surface_id.in_(surface_ids), SurfacePart.source_surface_id != SurfacePart.surface_id
            )
        )
    ).all()
    return {source: merged for source, merged in rows}


async def decorate(db: AsyncSession, surfaces: list[Surface]) -> None:
    """Add to the walls what the screen needs of a merge: `parts`, the summed `gross_area`, `merged_into_id` (plain attributes, as `deduction_area`)."""
    ids = [surface.id for surface in surfaces if surface.surface_type == SurfaceType.WALL]
    parts = await load_parts(db, ids)
    absorbed = await merged_into(db, ids)
    for surface in surfaces:
        surface.parts = parts.get(surface.id, [])
        surface.merged_into_id = absorbed.get(surface.id)
        # always set: the same object may carry the sum of parts of an earlier read in this session
        surface.gross_area = parts_gross_area(surface.parts) if surface.parts else None


async def effective_gross_area(db: AsyncSession, surface: Surface) -> Decimal | None:
    """The gross area of a wall as the rest of the application must use it: the sum of the parts of a merged wall, else width x height."""
    if surface.width is None or surface.height is None or surface.width <= 0 or surface.height <= 0:
        return None
    parts = (await load_parts(db, [surface.id])).get(surface.id) if surface.surface_type == SurfaceType.WALL else None
    if parts:
        return parts_gross_area(parts)
    return (surface.width * surface.height).quantize(AREA)


async def wall_size_pairs(db: AsyncSession, rows: list[tuple[uuid.UUID, Decimal, Decimal]]) -> list[tuple[Decimal, Decimal]]:
    """(width, height) pairs of the walls (`rows` = surface id, width, height); a merged wall gives one pair per part."""
    parts = await load_parts(db, [row[0] for row in rows])
    pairs: list[tuple[Decimal, Decimal]] = []
    for surface_id, width, height in rows:
        if surface_id in parts:
            pairs.extend((part.width, part.height) for part in parts[surface_id])
        else:
            pairs.append((Decimal(width), Decimal(height)))
    return pairs
