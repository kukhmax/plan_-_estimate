from dataclasses import dataclass
from decimal import Decimal

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
