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
