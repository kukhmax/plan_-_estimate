"""The trades (packages of professions) of an owner (V2-13)."""
from pydantic import BaseModel, ConfigDict, Field


class TradeRead(BaseModel):
    key: str
    price_categories: list[str]
    material_packages: list[str]


class TradesRead(BaseModel):
    """What the app needs to hide what an owner does not do: the catalogue of the trades (what each one owns), what belongs to none (always offered) and what the owner has on."""

    trades: list[TradeRead]
    always_categories: list[str]
    enabled: list[str]


class TradesWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Items are checked by the rules (a stable reason per wrong entry), not by the type: a number in the list is `WRONG_TYPE`, a stranger is `UNKNOWN_TRADE`.
    enabled: list[object] = Field(max_length=32)
