"""The open page for the client (V2-8): a white list of what the client sees, and the two things the client may do."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PortalContractor(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    city: str | None = None


class PortalProject(BaseModel):
    name: str
    address: str
    city: str
    postal_code: str
    # UX walk: the name of the client of the object (a private person's first and last name), offered in the approval form; null for a company
    # or an object with no client
    client_name: str | None = None


class PortalLine(BaseModel):
    position: int
    room_name: str | None = None
    surface_name: str | None = None
    description: str
    unit: str
    quantity: Decimal
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    # UX walk: LABOR / MATERIAL / LABOR_AND_MATERIAL -- the materials of the object are shown under "Materiały", not "Pozostałe prace"
    scope: str | None = None


class PortalStatement(BaseModel):
    pl: str  # the text written to the journal
    text: str  # the same in the language of the page (equal to `pl` for Polish)


class PortalConsent(BaseModel):
    kind: str
    signer_name: str
    comment: str | None = None
    created_at: datetime


class PortalEstimate(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    name: str | None = None
    currency: str
    total: Decimal | None = None
    vat_mode: str | None = None
    vat_rate_percent: int | None = None
    vat_included: bool = False
    net_total: Decimal | None = None
    vat_amount: Decimal | None = None
    gross_total: Decimal | None = None
    hash: str
    lines: list[PortalLine]
    consent: PortalConsent | None = None
    accept_statement: PortalStatement | None = None  # only while the estimate is waiting for the client
    decline_statement: PortalStatement | None = None


class PortalProposal(BaseModel):
    id: uuid.UUID
    sequence: int
    title: str
    description: str | None = None
    amount: Decimal
    currency: str
    extra_days: int | None = None
    status: str
    hash: str
    created_at: datetime
    consent: PortalConsent | None = None
    accept_statement: PortalStatement | None = None  # only while the proposal is open
    decline_statement: PortalStatement | None = None


class PortalLinkInfo(BaseModel):
    expires_at: datetime
    language: str


class PortalPage(BaseModel):
    link: PortalLinkInfo
    lang: str
    contractor: PortalContractor
    project: PortalProject
    estimate: PortalEstimate | None = None
    proposals: list[PortalProposal]


class PortalDecideEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimate_id: uuid.UUID
    version: int = Field(ge=1)
    hash: str = Field(min_length=64, max_length=64)
    decision: Literal["ACCEPT", "DECLINE"]
    signer_name: str = Field(max_length=200)
    agree: bool
    comment: str | None = Field(default=None, max_length=2000)  # the reason of a refusal; refused with an approval


class PortalDecideProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["ACCEPT", "DECLINE"]
    hash: str = Field(min_length=64, max_length=64)
    signer_name: str = Field(max_length=200)
    agree: bool
    comment: str | None = Field(default=None, max_length=2000)


class PortalWhyPhoto(BaseModel):
    thumb_url: str
    url: str
    width: int
    height: int


class PortalWhyReason(BaseModel):
    surface_name: str | None = None
    work_name_key: str | None = None  # the catalogue name of the work (translated by the page) ...
    work_name: str | None = None  # ... or the owner's own name
    reason_key: str  # the risk or the finding the work answers (translated by the page)
    inspected_on: date | None = None
    photos: list[PortalWhyPhoto] = []


class PortalWhyRoom(BaseModel):
    room_name: str
    quality_target: str | None = None  # S1-S4 / Q1-Q4 most of its surfaces are planned to
    reasons: list[PortalWhyReason] = []


class PortalWhy(BaseModel):
    """Owner 2026-10-31: "Dlaczego te prace?" of the client's page -- the agreed standard of each room and the reasons from the inspections."""

    rooms: list[PortalWhyRoom]

