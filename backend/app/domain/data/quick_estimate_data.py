"""The quick estimate (V2-4; docs/V2_4_PLAN_RU.md): which works the owner ticks, in which order, and what is ticked by default.

Only the choice of rows lives here; every price comes from the owner's price book. A work on the ceiling may be a different row than on the
walls (painting a ceiling has its own row).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class QuickWork:
    code: str  # the price row used on the walls
    ceiling_code: str  # the price row used on the ceiling
    default_on: bool


QUICK_WORKS: tuple[QuickWork, ...] = (
    QuickWork("CENNIK_PREP_PROT-01", "CENNIK_PREP_PROT-01", False),
    QuickWork("CENNIK_PRIM_STD-01", "CENNIK_PRIM_STD-01", True),
    QuickWork("CENNIK_SKIM_2L-01", "CENNIK_SKIM_2L-01", True),
    QuickWork("CENNIK_SKIM_SAND-01", "CENNIK_SKIM_SAND-01", True),
    QuickWork("CENNIK_PAINT_2K-01", "CENNIK_PAINT_CEIL-01", True),
)

QUICK_WORK_CODES: tuple[str, ...] = tuple(work.code for work in QUICK_WORKS)
MAX_ROOMS = 30
MAX_DIMENSION_M = 100
