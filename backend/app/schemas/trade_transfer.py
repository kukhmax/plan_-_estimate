"""Carrying the answers of a craftsman over into the rooms (V2-14a): what the owner sends and the preview / the result he gets back."""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.payment import Out
from app.schemas.room_point import PointItemRead

Kind = Literal["NEW", "CHANGE", "SAME", "REMOVE"]
MaterialKind = Literal["NONE", "NEW", "CHANGE", "SAME", "REMOVE", "INVALID"]


class TransferPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The item of the price book each typical position goes to; a key that is not here takes the default (found by the name), `null` means "do not carry this position over".
    mapping: dict[str, uuid.UUID | None] = Field(default_factory=dict, max_length=20)


class TransferRequest(TransferPreviewRequest):
    points: bool = True
    materials: bool = True


class PositionPlan(BaseModel):
    key: str
    unit: Literal["PCS", "LM"]
    goes_to_points: bool  # False: the position has no item of the price book (circuits, outlets of the manifold): it goes to the materials only
    answered_rooms: int
    item_id: uuid.UUID | None  # the choice now in force (the owner's or the default)
    default_item_id: uuid.UUID | None
    candidates: list[PointItemRead]


class RowPlan(BaseModel):
    kind: Kind
    item_id: uuid.UUID
    quantity: Out
    was_quantity: Out | None
    note: str | None


class MaterialPlan(BaseModel):
    kind: MaterialKind
    package: Literal["ELECTRIC", "PLUMBING"]
    numbers: dict[str, str]  # what the calculation will hold (the names of `schemas/material.py`)


class RoomPlan(BaseModel):
    room_id: uuid.UUID
    room_name: str
    rows: list[RowPlan]
    material: MaterialPlan


class TransferPreview(BaseModel):
    trade: Literal["ELECTRIC", "PLUMBING"]
    positions: list[PositionPlan]
    rooms: list[RoomPlan]
    own_not_carried: int  # the positions the craftsman wrote himself: they have no item of the price book and stay in his answer
    nothing: bool  # no answer to carry over and nothing carried earlier to take away


class TransferResult(BaseModel):
    points_added: int
    points_changed: int
    points_removed: int
    materials_added: int
    materials_changed: int
    materials_removed: int
