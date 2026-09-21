"""Idempotent baseline data for the `CoefficientGroup`/`CoefficientOption`
catalog (Stage 12C).

Mirrors `app/domain/data/work_recommendation_rules.py`'s shape exactly: a
pure dataclass list, materialized lazily and idempotently per owner by
`PriceCoefficientService._ensure_bootstrapped` (never an Alembic data seed --
see `docs/stage-12-architecture.md` Sec 5 for the rationale).

This module intentionally ships with an EMPTY baseline. Stage 12B's
architecture explicitly forbids seeding any Q/S/PSG (or other) percentage
before Stage 12G defines and the owner approves real default values (Sec 2,
Sec 21, Sec 25 of the architecture document) -- seeding a guessed number here,
even a "safe-looking" one, would be exactly the mistake that gate exists to
prevent. `build_baseline_price_coefficients()` returning `[]` means the
bootstrap mechanism runs (and is fully tested) but currently installs
nothing; 12G will populate this list with owner-approved groups/options, and
every existing owner will receive them automatically the next time they list
or use the catalog, via the same lazy mechanism already proven in production
by Stage 11's `WorkRecommendationRule` bootstrap.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CoefficientOptionData:
    code: str
    percentage: str
    is_base: bool = False
    display_name: str | None = None
    name_key: str | None = None


@dataclass(frozen=True)
class CoefficientGroupData:
    code: str
    display_name: str | None = None
    name_key: str | None = None
    options: tuple[CoefficientOptionData, ...] = field(default_factory=tuple)


def build_baseline_price_coefficients() -> list[CoefficientGroupData]:
    """Return the initial deterministic catalog served by bootstrap.

    Intentionally empty until Stage 12G defines and the owner approves real
    default groups/options. Do not add entries here without an explicit,
    separate owner-approved specification -- see this module's own docstring.
    """
    return []
