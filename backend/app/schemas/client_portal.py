"""The open page for the client (V2-8): a white list of what the client sees, and the two things the client may do."""
import uuid
from datetime import datetime
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


class PortalLine(BaseModel):
    position: int
    room_name: str | None = None
    surface_name: str | None = None
    description: str
    unit: str
    quantity: Decimal
    unit_price: Decimal | None = None
    amount: Decimal | None = None


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
