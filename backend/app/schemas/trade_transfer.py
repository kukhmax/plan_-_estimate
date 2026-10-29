"""Carrying the answers of a craftsman over into the rooms (V2-14a): what the owner sends and the preview / the result he gets back."""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.payment import Out
from app.schemas.room_point import PointItemRead

Kind = Literal["NEW", "CHANGE", "SAME", "REMOVE", "TAKE_OVER", "REMOVE_OWN", "SKIP"]
MaterialKind = Literal["NONE", "NEW", "CHANGE", "SAME", "REMOVE", "INVALID", "TAKE_OVER", "SKIP"]
OwnMode = Literal["REPLACE", "ADD", "SKIP"]


class TransferPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The item of the price book each typical position goes to; a key that is not here takes the default (found by the name), `null` means "do not carry this position over".
    mapping: dict[str, uuid.UUID | None] = Field(default_factory=dict, max_length=20)
    # What happens to a row the owner typed himself with the same item in the same room: REPLACE (the craftsman's number takes its place), ADD (both stay), SKIP (it stays alone).
    own: OwnMode = "REPLACE"


class TransferRequest(TransferPreviewRequest):
    points: bool = True
    materials: bool = True


class CandidateRead(PointItemRead):
    relevant: bool  # the category belongs to the trade (or is the universal "Punkty i trasy"): offered first, the rest only on request


class PositionPlan(BaseModel):
    key: str
    unit: Literal["PCS", "LM"]
    goes_to_points: bool  # False: the position has no item of the price book (circuits, outlets of the manifold): it goes to the materials only
    answered_rooms: int
    item_id: uuid.UUID | None  # the choice now in force (the owner's or the default)
    default_item_id: uuid.UUID | None
    candidates: list[CandidateRead]  # the relevant ones first


class RowPlan(BaseModel):
    kind: Kind
    item_id: uuid.UUID
    quantity: Out
    was_quantity: Out | None
    note: str | None
    own_quantity: Out | None = None  # the owner's own rows of this item in this room, together (None: he has none)


class MaterialPlan(BaseModel):
    kind: MaterialKind
    package: Literal["ELECTRIC", "PLUMBING"]
    numbers: dict[str, str]  # what the calculation will hold (the names of `schemas/material.py`)
    own: bool = False  # the room has the owner's own calculation of this package


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
    offer_pack: bool  # an answered position has no item of the price book: the typical items may be made
    own: OwnMode = "REPLACE"  # the choice the preview was made with
    own_conflicts: int = 0  # rows / calculations of the owner that name what the craftsman also gives (the choice matters only when this is above 0)


class TransferResult(BaseModel):
    points_added: int
    points_changed: int
    points_removed: int
    materials_added: int
    materials_changed: int
    materials_removed: int
