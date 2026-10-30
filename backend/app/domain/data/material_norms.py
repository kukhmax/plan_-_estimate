"""The reference of the consumption norms for the packages "Płytki", "GKL" (V2-11), "Elektryka" and "Hydraulika" (V2-12): the starting numbers and the materials, one row each.

A row is either a **number** (`PARAM`: a waste in percent, a consumption per m², the size of a pack, a step) or a **material** (`MATERIAL`: the name the owner reads, the unit it is
bought in, and -- set by the owner -- the Price Book item that gives its price). The numbers here are the **starting** ones: typical figures to start from, to be checked against the
data sheets of the materials the owner really uses; the owner edits every number in the application and may return it to the starting one. Money never appears here.
"""
from dataclasses import dataclass
from decimal import Decimal

TILE, DRYWALL, ELECTRIC, PLUMBING = "TILE", "DRYWALL", "ELECTRIC", "PLUMBING"
PARAM, MATERIAL = "PARAM", "MATERIAL"


@dataclass(frozen=True)
class NormDef:
    code: str
    package: str
    kind: str
    name: str  # Polish: the name of a material is printed in the estimate, which is Polish for the client; a number carries its own explanation in the application
    unit_text: str  # how the number is read: "%", "kg/m²", "m", "pcs"... (a material: the unit of its pack in the statement)
    default: Decimal | None  # the starting number (None for a material)
    minimum: Decimal = Decimal(0)
    maximum: Decimal = Decimal(100000)
    billing_unit: str | None = None  # a material: the unit of its line in an estimate (M2 / PCS / LM)


def _p(code: str, package: str, unit_text: str, default: str, minimum: str = "0", maximum: str = "100000") -> NormDef:
    return NormDef(code, package, PARAM, code, unit_text, Decimal(default), Decimal(minimum), Decimal(maximum))


def _m(code: str, package: str, name: str, unit_text: str, billing_unit: str) -> NormDef:
    return NormDef(code, package, MATERIAL, name, unit_text, None, billing_unit=billing_unit)


NORMS: tuple[NormDef, ...] = (
    # --- the tile ---------------------------------------------------------------------------------------------------------------------------
    _p("TILE_WASTE_STRAIGHT", TILE, "%", "10", "0", "100"),
    _p("TILE_WASTE_DIAGONAL", TILE, "%", "15", "0", "100"),
    _p("TILE_ADHESIVE_LIMIT_SMALL_CM", TILE, "cm", "30", "1", "1000"),
    _p("TILE_ADHESIVE_LIMIT_MEDIUM_CM", TILE, "cm", "60", "1", "1000"),
    _p("TILE_ADHESIVE_KG_M2_SMALL", TILE, "kg/m²", "3.5", "0", "50"),
    _p("TILE_ADHESIVE_KG_M2_MEDIUM", TILE, "kg/m²", "5", "0", "50"),
    _p("TILE_ADHESIVE_KG_M2_LARGE", TILE, "kg/m²", "7", "0", "50"),
    _p("TILE_ADHESIVE_BAG_KG", TILE, "kg", "25", "0.1", "1000"),
    _p("TILE_GROUT_DENSITY", TILE, "kg/dm³", "1.6", "0.1", "10"),
    _p("TILE_GROUT_WASTE", TILE, "%", "15", "0", "100"),
    _p("TILE_GROUT_BAG_KG", TILE, "kg", "5", "0.1", "1000"),
    _p("TILE_WATERPROOF_KG_M2", TILE, "kg/m²", "1.5", "0", "50"),
    _p("TILE_WATERPROOF_LAYERS", TILE, "pcs", "2", "1", "10"),
    _p("TILE_WATERPROOF_PACK_KG", TILE, "kg", "15", "0.1", "1000"),
    _p("TILE_TAPE_ROLL_M", TILE, "m", "10", "0.1", "1000"),
    _p("TILE_SPACERS_PER_TILE", TILE, "pcs", "3", "0", "100"),  # UX walk: 2-4 crosses / wedges per tile in practice, not 1
    _p("TILE_SPACERS_PACK", TILE, "pcs", "200", "1", "100000"),
    _m("TILE_TILES", TILE, "Płytki", "m²", "M2"),
    _m("TILE_ADHESIVE", TILE, "Klej do płytek (worek)", "bag", "PCS"),
    _m("TILE_GROUT", TILE, "Fuga (worek)", "bag", "PCS"),
    _m("TILE_WATERPROOF", TILE, "Hydroizolacja (wiadro)", "pack", "PCS"),
    _m("TILE_WATERPROOF_TAPE", TILE, "Taśma uszczelniająca (rolka)", "roll", "PCS"),
    _m("TILE_SPACERS", TILE, "Krzyżyki dystansowe (opakowanie)", "pack", "PCS"),
    # --- the drywall ------------------------------------------------------------------------------------------------------------------------
    _p("GK_WASTE", DRYWALL, "%", "10", "0", "100"),
    _p("GK_SHEET_AREA_M2", DRYWALL, "m²", "3", "0.1", "20"),
    _p("GK_PROFILE_LEN_M", DRYWALL, "m", "3", "0.5", "10"),
    _p("GK_CD_STEP_WALL_M", DRYWALL, "m", "0.6", "0.1", "2"),
    _p("GK_CD_PER_M2_CEILING", DRYWALL, "m/m²", "3", "0", "20"),
    _p("GK_HANGERS_PER_M2", DRYWALL, "pcs/m²", "1.5", "0", "20"),
    _p("GK_SCREWS_PER_M2_LAYER", DRYWALL, "pcs/m²", "25", "0", "500"),
    _p("GK_SCREWS_BOX", DRYWALL, "pcs", "1000", "1", "100000"),
    _p("GK_FILLER_KG_M2", DRYWALL, "kg/m²", "0.5", "0", "20"),
    _p("GK_FILLER_BAG_KG", DRYWALL, "kg", "25", "0.1", "1000"),
    _p("GK_TAPE_M_PER_M2", DRYWALL, "m/m²", "1.5", "0", "20"),
    _p("GK_TAPE_ROLL_M", DRYWALL, "m", "90", "1", "1000"),
    _m("GK_SHEETS", DRYWALL, "Płyta g-k (arkusz)", "sheet", "PCS"),
    _m("GK_UD", DRYWALL, "Profil UD (sztuka)", "pc", "PCS"),
    _m("GK_CD", DRYWALL, "Profil CD (sztuka)", "pc", "PCS"),
    _m("GK_HANGERS", DRYWALL, "Wieszak do profili CD", "pc", "PCS"),
    _m("GK_SCREWS", DRYWALL, "Wkręty do płyt g-k (opakowanie)", "box", "PCS"),
    _m("GK_FILLER", DRYWALL, "Szpachla do spoin (worek)", "bag", "PCS"),
    _m("GK_TAPE", DRYWALL, "Taśma do spoin (rolka)", "roll", "PCS"),
    # --- the electrician (V2-12) ------------------------------------------------------------------------------------------------------------
    _p("ELEC_CABLE_M_SOCKET", ELECTRIC, "m", "6", "0", "100"),
    _p("ELEC_CABLE_M_SWITCH", ELECTRIC, "m", "4", "0", "100"),
    _p("ELEC_CABLE_M_LIGHT", ELECTRIC, "m", "5", "0", "100"),
    _p("ELEC_CABLE_WASTE", ELECTRIC, "%", "10", "0", "100"),
    _p("ELEC_CABLE_COIL_M", ELECTRIC, "m", "100", "1", "1000"),
    _p("ELEC_CONDUIT_SHARE", ELECTRIC, "%", "100", "0", "100"),
    _p("ELEC_CONDUIT_COIL_M", ELECTRIC, "m", "50", "1", "1000"),
    _p("ELEC_JBOX_PER_CIRCUIT", ELECTRIC, "pcs", "1", "0", "20"),
    _p("ELEC_TERMINALS_PER_POINT", ELECTRIC, "pcs", "3", "0", "50"),
    _p("ELEC_TERMINALS_PACK", ELECTRIC, "pcs", "50", "1", "10000"),
    _m("ELEC_CABLE", ELECTRIC, "Przewód elektryczny (kręg)", "coil", "PCS"),
    _m("ELEC_CONDUIT", ELECTRIC, "Rura osłonowa / peszel (kręg)", "coil", "PCS"),
    _m("ELEC_FLUSH_BOX", ELECTRIC, "Puszka podtynkowa", "pc", "PCS"),
    _m("ELEC_SOCKETS", ELECTRIC, "Gniazdo", "pc", "PCS"),
    _m("ELEC_SWITCHES", ELECTRIC, "Łącznik", "pc", "PCS"),
    _m("ELEC_BREAKERS", ELECTRIC, "Wyłącznik nadprądowy", "pc", "PCS"),
    _m("ELEC_JBOX", ELECTRIC, "Puszka rozgałęźna", "pc", "PCS"),
    _m("ELEC_TERMINALS", ELECTRIC, "Złączki instalacyjne (opakowanie)", "pack", "PCS"),
    # --- the plumber (V2-12) ----------------------------------------------------------------------------------------------------------------
    _p("PL_PIPE_M_POINT", PLUMBING, "m", "4", "0", "100"),
    _p("PL_PIPE_WASTE", PLUMBING, "%", "10", "0", "100"),
    _p("PL_PIPE_COIL_M", PLUMBING, "m", "100", "1", "1000"),
    _p("PL_FITTINGS_PER_POINT", PLUMBING, "pcs", "4", "0", "50"),
    _p("PL_VALVES_PER_POINT", PLUMBING, "pcs", "1", "0", "10"),
    _p("PL_CLIPS_PER_M", PLUMBING, "pcs/m", "2", "0", "20"),
    _p("PL_CLIPS_PACK", PLUMBING, "pcs", "100", "1", "10000"),
    _p("PL_DRAIN_M_POINT", PLUMBING, "m", "2", "0", "50"),
    _p("PL_DRAIN_BAR_M", PLUMBING, "m", "2", "0.5", "10"),
    _p("PL_DRAIN_FITTINGS_PER_POINT", PLUMBING, "pcs", "3", "0", "50"),
    _m("PL_PIPE", PLUMBING, "Rura wodna (kręg)", "coil", "PCS"),
    _m("PL_FITTINGS", PLUMBING, "Kształtki do rur wodnych", "pc", "PCS"),
    _m("PL_VALVES", PLUMBING, "Zawór kulowy", "pc", "PCS"),
    _m("PL_MANIFOLD", PLUMBING, "Rozdzielacz (wylot)", "pc", "PCS"),
    _m("PL_CLIPS", PLUMBING, "Uchwyty do rur (opakowanie)", "pack", "PCS"),
    _m("PL_DRAIN_PIPE", PLUMBING, "Rura kanalizacyjna (sztuka)", "bar", "PCS"),
    _m("PL_DRAIN_FITTINGS", PLUMBING, "Kształtki kanalizacyjne", "pc", "PCS"),
)

BY_CODE: dict[str, NormDef] = {n.code: n for n in NORMS}
assert len(BY_CODE) == len(NORMS)
