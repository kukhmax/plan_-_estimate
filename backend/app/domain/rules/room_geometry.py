from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.models.area_segment import AreaOperation
from app.models.surface import SurfaceType

AREA_PRECISION = Decimal("0.001")


@dataclass(frozen=True)
class RoomGeometryResult:
    floor_area: Decimal
    ceiling_area: Decimal
    total_wall_area: Decimal
    wall_area_length: Decimal
    wall_area_width: Decimal
    perimeter: Decimal


@dataclass(frozen=True)
class OpeningAreaResult:
    single_area: Decimal
    total_area: Decimal


@dataclass(frozen=True)
class RoomAggregateTotals:
    floor_gross_area: Decimal
    ceiling_gross_area: Decimal
    total_wall_gross_area: Decimal
    total_opening_deduction_area: Decimal
    total_wall_net_area: Decimal
    perimeter: Decimal


@dataclass(frozen=True)
class WallDerivedTotals:
    """Totals aggregated from a room's measured WALL surfaces."""

    wall_count: int
    perimeter: Decimal
    total_wall_area: Decimal
    total_deduction_area: Decimal
    net_wall_area: Decimal


@dataclass(frozen=True)
class ResolvedRoomTotals:
    """Final room totals resolved from formula geometry and/or measured walls."""

    floor_area: Decimal | None
    ceiling_area: Decimal | None
    total_wall_area: Decimal | None
    wall_area_length: Decimal | None
    wall_area_width: Decimal | None
    perimeter: Decimal | None
    total_deduction_area: Decimal | None
    net_wall_area: Decimal | None
    wall_count: int | None


@dataclass(frozen=True)
class PlaneAreaTotals:
    """Aggregated area of active segments for a single FLOOR/CEILING plane."""

    additive_area: Decimal
    subtraction_area: Decimal
    net_area: Decimal


def calculate_room_geometry(
    length: Decimal | None,
    width: Decimal | None,
    height: Decimal | None,
) -> RoomGeometryResult | None:
    if length is None or width is None or height is None:
        return None
    if length <= 0 or width <= 0 or height <= 0:
        return None

    floor = (length * width).quantize(AREA_PRECISION)
    ceiling = (length * width).quantize(AREA_PRECISION)
    wall_len = (length * height).quantize(AREA_PRECISION)
    wall_wid = (width * height).quantize(AREA_PRECISION)
    total_wall = (2 * (length + width) * height).quantize(AREA_PRECISION)
    perimeter = (2 * (length + width)).quantize(AREA_PRECISION)

    return RoomGeometryResult(
        floor_area=floor,
        ceiling_area=ceiling,
        total_wall_area=total_wall,
        wall_area_length=wall_len,
        wall_area_width=wall_wid,
        perimeter=perimeter,
    )


def calculate_surface_gross_area(
    surface_type: SurfaceType | str,
    width: Decimal | None,
    height: Decimal | None,
    room_length: Decimal | None = None,
    room_width: Decimal | None = None,
) -> Decimal | None:
    if width is not None and height is not None:
        if width <= 0 or height <= 0:
            return None
        return (width * height).quantize(AREA_PRECISION)

    st = SurfaceType(surface_type) if isinstance(surface_type, str) else surface_type
    if st in (SurfaceType.FLOOR, SurfaceType.CEILING):
        if room_length is not None and room_width is not None and room_length > 0 and room_width > 0:
            return (room_length * room_width).quantize(AREA_PRECISION)

    return None


def calculate_opening_area(
    width: Decimal | None,
    height: Decimal | None,
    quantity: int = 1,
) -> OpeningAreaResult | None:
    if width is None or height is None:
        return None
    if width <= 0 or height <= 0 or quantity < 1:
        return None

    single = (width * height).quantize(AREA_PRECISION)
    total = (width * height * Decimal(quantity)).quantize(AREA_PRECISION)
    return OpeningAreaResult(single_area=single, total_area=total)


def calculate_segment_area(
    width: Decimal | None,
    height: Decimal | None,
) -> Decimal | None:
    """Area of a single ADD/SUBTRACT rectangle segment (width x height)."""
    if width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None
    return (width * height).quantize(AREA_PRECISION)


def calculate_plane_totals(
    segments: Sequence[tuple[AreaOperation | str, Decimal]],
) -> PlaneAreaTotals | None:
    """Aggregate active segments for one plane into additive/subtraction/net areas.

    `segments` items are (operation, segment_area). Returns None when there are
    no segments. Raises ValueError when the resulting net area would be negative.
    """
    additive = Decimal("0.000")
    subtraction = Decimal("0.000")
    for operation, area in segments:
        op = (
            AreaOperation(operation)
            if isinstance(operation, str)
            else operation
        )
        if op == AreaOperation.ADD:
            additive += area
        elif op == AreaOperation.SUBTRACT:
            subtraction += area

    net = (additive - subtraction).quantize(AREA_PRECISION)
    if net < 0:
        raise ValueError(
            f"Net area ({net}) cannot be negative for a plane with "
            f"additions {additive} and subtractions {subtraction}"
        )
    return PlaneAreaTotals(
        additive_area=additive.quantize(AREA_PRECISION),
        subtraction_area=subtraction.quantize(AREA_PRECISION),
        net_area=net,
    )


def calculate_wall_net_area(
    gross_area: Decimal | None,
    deduction_area: Decimal | None,
) -> Decimal | None:
    if gross_area is None:
        return None
    if gross_area < 0:
        return None

    deduction = deduction_area if deduction_area is not None else Decimal("0.000")
    if deduction < 0:
        return None
    if deduction > gross_area:
        raise ValueError(
            f"Deduction area ({deduction}) cannot exceed wall gross area ({gross_area})"
        )

    return (gross_area - deduction).quantize(AREA_PRECISION)


def calculate_room_aggregate_totals(
    room_geometry: RoomGeometryResult | None,
    total_opening_deduction_area: Decimal = Decimal("0.000"),
) -> RoomAggregateTotals | None:
    if room_geometry is None:
        return None

    deduction = total_opening_deduction_area.quantize(AREA_PRECISION)
    if deduction > room_geometry.total_wall_area:
        raise ValueError(
            f"Total opening deduction ({deduction}) cannot exceed room total wall area ({room_geometry.total_wall_area})"
        )

    net_wall = (room_geometry.total_wall_area - deduction).quantize(AREA_PRECISION)
    return RoomAggregateTotals(
        floor_gross_area=room_geometry.floor_area,
        ceiling_gross_area=room_geometry.ceiling_area,
        total_wall_gross_area=room_geometry.total_wall_area,
        total_opening_deduction_area=deduction,
        total_wall_net_area=net_wall,
        perimeter=room_geometry.perimeter,
    )


def generate_canonical_walls(
    length: Decimal,
    width: Decimal,
    height: Decimal,
) -> list[tuple[int, str, Decimal, Decimal]]:
    """Return the 4 canonical rectangle walls as (position, name, width, height).

    Wall1 pos 0 = length x height, Wall2 pos 1 = width x height,
    Wall3 pos 2 = length x height, Wall4 pos 3 = width x height.
    Names are language-neutral tokens; all surfaces are WALLs. Floor and
    ceiling are never generated here.
    """
    return [
        (0, "Wall 1", length, height),
        (1, "Wall 2", width, height),
        (2, "Wall 3", length, height),
        (3, "Wall 4", width, height),
    ]


def matches_canonical_wall_set(
    length: Decimal,
    width: Decimal,
    height: Decimal,
    walls: Sequence[
        tuple[int | None, SurfaceType | str, Decimal | None, Decimal | None]
    ],
) -> bool:
    """Return True only when active WALLs exactly reproduce the canonical rectangle.

    `walls` items are (position, surface_type, width, height). The set must
    contain exactly four active WALLs at positions 0..3 with the exact canonical
    dimensions for that room; otherwise the generation request must conflict.
    """
    if len(walls) != 4:
        return False

    by_position: dict[int, tuple[Decimal | None, Decimal | None]] = {}
    for position, surface_type, wall_width, wall_height in walls:
        st = (
            SurfaceType(surface_type)
            if isinstance(surface_type, str)
            else surface_type
        )
        if st != SurfaceType.WALL or position is None or position in by_position:
            return False
        by_position[position] = (wall_width, wall_height)

    if set(by_position) != {0, 1, 2, 3}:
        return False

    expected: dict[int, tuple[Decimal, Decimal]] = {
        0: (length, height),
        1: (width, height),
        2: (length, height),
        3: (width, height),
    }
    return all(
        by_position[p][0] == expected[p][0] and by_position[p][1] == expected[p][1]
        for p in (0, 1, 2, 3)
    )


def calculate_wall_derived_totals(
    walls: Sequence[tuple[Decimal | None, Decimal | None]],
    total_deduction_area: Decimal = Decimal("0.000"),
) -> WallDerivedTotals | None:
    """Aggregate wall totals from measured (width, height) pairs.

    Only walls with positive width and height contribute to the totals. Returns
    None when no measured walls exist. Perimeter equals the sum of wall widths.
    """
    measured = [
        (w, h)
        for w, h in walls
        if w is not None and h is not None and w > 0 and h > 0
    ]
    if not measured:
        return None

    gross = sum((w * h for w, h in measured), Decimal("0.000")).quantize(AREA_PRECISION)
    perimeter = sum((w for w, _ in measured), Decimal("0.000")).quantize(AREA_PRECISION)
    deduction = total_deduction_area.quantize(AREA_PRECISION)
    if deduction > gross:
        raise ValueError(
            f"Total opening deduction ({deduction}) cannot exceed measured wall area ({gross})"
        )

    net = (gross - deduction).quantize(AREA_PRECISION)
    return WallDerivedTotals(
        wall_count=len(measured),
        perimeter=perimeter,
        total_wall_area=gross,
        total_deduction_area=deduction,
        net_wall_area=net,
    )


def resolve_room_totals(
    geometry: RoomGeometryResult | None,
    wall_totals: WallDerivedTotals | None,
    total_opening_deduction_area: Decimal = Decimal("0.000"),
    floor_segments: PlaneAreaTotals | None = None,
    ceiling_segments: PlaneAreaTotals | None = None,
) -> ResolvedRoomTotals | None:
    """Resolve final room totals from formula geometry, measured walls, and segments.

    When measured walls exist, wall totals take precedence for every wall metric.
    When a plane has active area segments, the segment-derived net area takes
    precedence for that plane; otherwise the formula L x W is used when room
    length/width are known (irregular rooms without dims report None). With no
    measured walls, the formula-based geometry is reported unchanged for backward
    compatibility.
    """
    resolved_floor = (
        floor_segments.net_area if floor_segments is not None
        else (geometry.floor_area if geometry is not None else None)
    )
    resolved_ceiling = (
        ceiling_segments.net_area if ceiling_segments is not None
        else (geometry.ceiling_area if geometry is not None else None)
    )

    if wall_totals is not None:
        return ResolvedRoomTotals(
            floor_area=resolved_floor,
            ceiling_area=resolved_ceiling,
            total_wall_area=wall_totals.total_wall_area,
            wall_area_length=geometry.wall_area_length if geometry is not None else None,
            wall_area_width=geometry.wall_area_width if geometry is not None else None,
            perimeter=wall_totals.perimeter,
            total_deduction_area=wall_totals.total_deduction_area,
            net_wall_area=wall_totals.net_wall_area,
            wall_count=wall_totals.wall_count,
        )

    if geometry is not None:
        deduction = total_opening_deduction_area.quantize(AREA_PRECISION)
        if deduction > geometry.total_wall_area:
            raise ValueError(
                f"Total opening deduction ({deduction}) cannot exceed room total wall area ({geometry.total_wall_area})"
            )
        net = (geometry.total_wall_area - deduction).quantize(AREA_PRECISION)
        return ResolvedRoomTotals(
            floor_area=resolved_floor,
            ceiling_area=resolved_ceiling,
            total_wall_area=geometry.total_wall_area,
            wall_area_length=geometry.wall_area_length,
            wall_area_width=geometry.wall_area_width,
            perimeter=geometry.perimeter,
            total_deduction_area=deduction,
            net_wall_area=net,
            wall_count=0,
        )

    # No measured walls and no formula geometry, but segment-derived planes exist
    # (e.g. an irregular/custom room measured as composite FLOOR/CEILING segments).
    if floor_segments is not None or ceiling_segments is not None:
        return ResolvedRoomTotals(
            floor_area=resolved_floor,
            ceiling_area=resolved_ceiling,
            total_wall_area=None,
            wall_area_length=None,
            wall_area_width=None,
            perimeter=None,
            total_deduction_area=None,
            net_wall_area=None,
            wall_count=None,
        )

    return None
