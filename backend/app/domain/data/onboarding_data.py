"""The first prices of a new contractor (V2-3; docs/V2_3_PLAN_RU.md): the five rows that most estimates need, in the order they are asked.

Only the choice of rows lives here; the prices are the owner's own (the market window of a row is shown as a hint, never filled in).
"""

STARTER_PRICE_CODES: tuple[str, ...] = (
    "CENNIK_PREP_PROT-01",  # protecting the floor and the joinery
    "CENNIK_PRIM_STD-01",  # penetrating primer
    "CENNIK_SKIM_2L-01",  # skim coat, two layers
    "CENNIK_SKIM_SAND-01",  # sanding with dust extraction
    "CENNIK_PAINT_2K-01",  # painting, two coats
)
