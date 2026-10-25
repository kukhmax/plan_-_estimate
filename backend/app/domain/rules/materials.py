"""The consumption of materials for the packages "Płytki" and "GKL" (V2-11). Pure functions: the data of a calculation and the numbers of the owner's norms in, the quantities out.

No money here (the price of a material is the Price Book's, joined later) and no database. Every quantity is a `Decimal`; what is bought in packs is rounded **up** to whole packs
(`ceil`), and the packs of a whole object are rounded once over the sum of its calculations (`total`), not calculation by calculation. The numbers are the owner's norms
(`data/material_norms.py` holds the starting ones); a missing number is a programming error and raises `KeyError`.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal

HUNDRED = Decimal(100)
TWO_PLACES = Decimal("0.01")
THREE_PLACES = Decimal("0.001")

Norms = Mapping[str, Decimal]


@dataclass(frozen=True)
class MaterialQty:
    """One material of one calculation: the exact quantity in its natural unit and, when it is bought in packs, the size of a pack."""

    code: str  # the code of the material of the norms (TILE_ADHESIVE, GK_CD, ...)
    quantity: Decimal  # the exact need, in `unit_text`
    unit_text: str  # "m²", "kg", "pcs", "m"
    pack_size: Decimal | None = None  # the size of a pack in `unit_text`; None: bought by the quantity itself (the tile, in m²)
    pieces: int | None = None  # tile: how many tiles


@dataclass(frozen=True)
class TileInput:
    area_m2: Decimal
    length_cm: Decimal
    width_cm: Decimal
    thickness_mm: Decimal = Decimal(8)
    joint_mm: Decimal = Decimal(3)
    diagonal: bool = False
    waterproof: bool = False
    waterproof_area_m2: Decimal | None = None  # None: the tiled area
    tape_m: Decimal | None = None  # None: no tape


@dataclass(frozen=True)
class DrywallInput:
    ceiling: bool
    area_m2: Decimal
    layers: int = 1
    height_m: Decimal | None = None  # a wall
    perimeter_m: Decimal | None = None  # a ceiling


def ceil_to(value: Decimal, places: Decimal) -> Decimal:
    return value.quantize(places, rounding=ROUND_CEILING)


def packs(quantity: Decimal, size: Decimal) -> int:
    """Whole packs for a quantity: rounded up; nothing needed is no pack."""
    if quantity <= 0:
        return 0
    return int((quantity / size).to_integral_value(rounding=ROUND_CEILING))


def tile_materials(data: TileInput, norms: Norms) -> list[MaterialQty]:
    area = data.area_m2
    waste = norms["TILE_WASTE_DIAGONAL" if data.diagonal else "TILE_WASTE_STRAIGHT"]
    tiled = area * (1 + waste / HUNDRED)
    tile_area = (data.length_cm / 100) * (data.width_cm / 100)
    pieces = packs(tiled, tile_area)
    side = max(data.length_cm, data.width_cm)
    if side <= norms["TILE_ADHESIVE_LIMIT_SMALL_CM"]:
        adhesive_rate = norms["TILE_ADHESIVE_KG_M2_SMALL"]
    elif side <= norms["TILE_ADHESIVE_LIMIT_MEDIUM_CM"]:
        adhesive_rate = norms["TILE_ADHESIVE_KG_M2_MEDIUM"]
    else:
        adhesive_rate = norms["TILE_ADHESIVE_KG_M2_LARGE"]
    # the grout: the joints of a square metre are (a + b) / (a * b) of length, a joint is `joint` wide and `thickness` deep (a and b in mm), its mass is the volume (dm3) by the density
    a, b = data.length_cm * 10, data.width_cm * 10
    grout_rate = (a + b) / (a * b) * data.joint_mm * data.thickness_mm * norms["TILE_GROUT_DENSITY"] * (1 + norms["TILE_GROUT_WASTE"] / HUNDRED)
    found = [
        MaterialQty("TILE_TILES", ceil_to(tiled, TWO_PLACES), "m²", None, pieces),
        MaterialQty("TILE_ADHESIVE", area * adhesive_rate, "kg", norms["TILE_ADHESIVE_BAG_KG"]),
        MaterialQty("TILE_GROUT", area * grout_rate, "kg", norms["TILE_GROUT_BAG_KG"]),
        MaterialQty("TILE_SPACERS", Decimal(pieces) * norms["TILE_SPACERS_PER_TILE"], "pcs", norms["TILE_SPACERS_PACK"]),
    ]
    if data.waterproof:
        wet = data.waterproof_area_m2 if data.waterproof_area_m2 is not None else area
        found.append(MaterialQty("TILE_WATERPROOF", wet * norms["TILE_WATERPROOF_KG_M2"] * norms["TILE_WATERPROOF_LAYERS"], "kg", norms["TILE_WATERPROOF_PACK_KG"]))
        if data.tape_m is not None and data.tape_m > 0:
            found.append(MaterialQty("TILE_WATERPROOF_TAPE", data.tape_m, "m", norms["TILE_TAPE_ROLL_M"]))
    return found


def drywall_materials(data: DrywallInput, norms: Norms) -> list[MaterialQty]:
    area = data.area_m2
    waste = 1 + norms["GK_WASTE"] / HUNDRED
    profile = norms["GK_PROFILE_LEN_M"]
    if data.ceiling:
        if data.perimeter_m is None:
            raise ValueError("a ceiling needs its perimeter")
        ud_m = data.perimeter_m
        cd_m = area * norms["GK_CD_PER_M2_CEILING"]
    else:
        if data.height_m is None or data.height_m <= 0:
            raise ValueError("a wall needs its height")
        ud_m = 2 * area / data.height_m
        cd_m = area / norms["GK_CD_STEP_WALL_M"] + data.height_m
    found = [
        MaterialQty("GK_SHEETS", area * data.layers * waste, "m²", norms["GK_SHEET_AREA_M2"]),
        MaterialQty("GK_UD", ud_m * waste, "m", profile),
        MaterialQty("GK_CD", cd_m * waste, "m", profile),
    ]
    if data.ceiling:
        found.append(MaterialQty("GK_HANGERS", area * norms["GK_HANGERS_PER_M2"], "pcs", Decimal(1)))
    found += [
        MaterialQty("GK_SCREWS", area * data.layers * norms["GK_SCREWS_PER_M2_LAYER"], "pcs", norms["GK_SCREWS_BOX"]),
        MaterialQty("GK_FILLER", area * norms["GK_FILLER_KG_M2"], "kg", norms["GK_FILLER_BAG_KG"]),
        MaterialQty("GK_TAPE", area * norms["GK_TAPE_M_PER_M2"], "m", norms["GK_TAPE_ROLL_M"]),
    ]
    return found


@dataclass(frozen=True)
class MaterialTotal:
    """A material over many calculations: the exact need summed and the packs made once from the sum."""

    code: str
    quantity: Decimal
    unit_text: str
    pack_size: Decimal | None
    packs: int | None  # None: no pack (the tile: the quantity itself)
    pieces: int | None = None

    @property
    def billing_quantity(self) -> Decimal:
        """The quantity of the line of an estimate: whole packs, or the quantity itself (rounded up to 0.01) for what has no pack."""
        return Decimal(self.packs) if self.packs is not None else ceil_to(self.quantity, TWO_PLACES)


@dataclass
class _Sum:
    quantity: Decimal = Decimal(0)
    pieces: int = 0
    first: MaterialQty | None = field(default=None)


def total(calculations: Iterable[Iterable[MaterialQty]]) -> list[MaterialTotal]:
    """Sum the materials of several calculations by code, in the order the codes first appear, and make the packs once over each sum."""
    sums: dict[str, _Sum] = {}
    for materials in calculations:
        for item in materials:
            entry = sums.setdefault(item.code, _Sum(first=item))
            entry.quantity += item.quantity
            entry.pieces += item.pieces or 0
    result = []
    for code, entry in sums.items():
        first = entry.first
        assert first is not None
        count = packs(entry.quantity, first.pack_size) if first.pack_size is not None else None
        result.append(MaterialTotal(code, entry.quantity, first.unit_text, first.pack_size, count, entry.pieces if first.pieces is not None else None))
    return result
