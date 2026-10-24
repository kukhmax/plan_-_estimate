"""The link for the client, the owner's side (V2-8)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClientLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    language: str
    created_at: datetime
    expires_at: datetime
    last_viewed_at: datetime | None = None
    view_count: int
    expired: bool = False


class ClientLinkStatus(BaseModel):
    link: ClientLinkRead | None = None


class ClientLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Literal["pl", "ru", "uk", "en"] = "pl"


class ClientLinkIssued(BaseModel):
    link: ClientLinkRead
    token: str  # the secret, shown once; the address is `<origin>/c#<token>`


class ClientProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    amount: Decimal = Field(gt=0, le=Decimal(100000000))
    extra_days: int | None = Field(default=None, ge=0, le=3650)


class ClientProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    title: str
    description: str | None = None
    amount: Decimal
    currency: str
    extra_days: int | None = None
    status: str
    created_at: datetime
    decided_at: datetime | None = None


class ClientProposalList(BaseModel):
    items: list[ClientProposalRead]
    max_proposals: int


class ClientConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    estimate_id: uuid.UUID | None = None
    estimate_version: int | None = None
    proposal_id: uuid.UUID | None = None
    subject_hash: str
    amount: Decimal
    currency: str
    statement: str
    statement_lang: str
    signer_name: str
    created_at: datetime


class ClientJournal(BaseModel):
    items: list[ClientConsentRead]
