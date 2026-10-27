"""The link for the electrician and the plumber (V2-14): what the owner sees and what the open page sends and receives. The open page gets a white list of fields:
the executor's name and contacts, the name of the object, the rooms with their sizes and the craftsman's own answers -- no prices, no client, no address, no other object."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Trade = Literal["ELECTRIC", "PLUMBING"]
Unit = Literal["PCS", "LM"]


class TypicalRead(BaseModel):
    key: str
    unit: Unit
    quantity: Decimal | None
    note: str | None


class OwnRead(BaseModel):
    name: str
    quantity: Decimal
    unit: Unit
    note: str | None


class PositionRead(BaseModel):
    key: str
    unit: Unit


# -- the owner's side -------------------------------------------------------------------------------------------------------------


class TradeLinkRead(BaseModel):
    trade: Trade
    language: str
    owner_note: str | None
    created_at: datetime
    expires_at: datetime
    last_viewed_at: datetime | None
    view_count: int
    expired: bool
    answers_count: int
    submissions_count: int
    last_submitted_at: datetime | None


class TradeLinksResponse(BaseModel):
    electric: TradeLinkRead | None
    plumbing: TradeLinkRead | None


class TradeLinkCreated(BaseModel):
    link: TradeLinkRead
    # The secret address of the page: shown once, when the link is made. Only its SHA-256 is kept.
    token: str


class TradeLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, max_length=5)
    note: str | None = Field(default=None, max_length=1200)


class TradeLinkNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=1200)


class OwnerRoomAnswers(BaseModel):
    room_id: uuid.UUID
    room_name: str
    typical: list[TypicalRead]
    own: list[OwnRead]
    updated_at: datetime | None


class SubmissionRead(BaseModel):
    id: uuid.UUID
    master_name: str
    answers_count: int
    created_at: datetime


class TradeAnswersResponse(BaseModel):
    trade: Trade
    positions: list[PositionRead]
    rooms: list[OwnerRoomAnswers]
    submissions: list[SubmissionRead]


# -- the open page ----------------------------------------------------------------------------------------------------------------


class PortalContractor(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    city: str | None = None


class PortalMarker(BaseModel):
    """A marker of the trade of the link on a photo: where (fractions of the picture), what it is and where it lies (cm) -- no outline, no caption."""

    x: float
    y: float
    label: str | None
    utility: str | None
    depth_cm: float | None
    from_floor_cm: float | None
    from_corner_cm: float | None


class PortalPhoto(BaseModel):
    """A photo of a room with links signed for a short time (`thumb_url` for the grid, `url` for the full picture)."""

    id: uuid.UUID
    thumb_url: str
    url: str
    width: int
    height: int
    place: str | None  # the wall the photo belongs to
    markers: list[PortalMarker]


class PortalRoom(BaseModel):
    id: uuid.UUID
    name: str
    length: Decimal | None
    width: Decimal | None
    height: Decimal | None
    floor_area: Decimal | None
    perimeter: Decimal | None
    typical: list[TypicalRead]
    own: list[OwnRead]
    photos: list[PortalPhoto] = []  # V2-14b: the photos of the room itself
    route_map: list[PortalPhoto] = []  # V2-14b: the photos with the markers of his trade


class PortalLinkInfo(BaseModel):
    expires_at: datetime
    language: str


class PortalTradePage(BaseModel):
    link: PortalLinkInfo
    lang: str
    trade: Trade
    contractor: PortalContractor
    project_name: str
    owner_note: str | None
    positions: list[PositionRead]
    rooms: list[PortalRoom]
    submissions_count: int
    last_submitted_at: datetime | None
    photos_expire_at: datetime | None = None  # V2-14b: when the links of the photos stop working


class TypicalWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(max_length=24)
    quantity: str | int | float | None = None
    note: str | None = Field(default=None, max_length=400)


class OwnWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=200)
    quantity: str | int | float | None = None
    unit: str = Field(max_length=3)
    note: str | None = Field(default=None, max_length=400)


class PortalRoomWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    typical: list[TypicalWrite] = Field(default_factory=list, max_length=20)
    own: list[OwnWrite] = Field(default_factory=list, max_length=60)


class PortalSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    master_name: str = Field(max_length=200)
