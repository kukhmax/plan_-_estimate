"""View models shared by every document layout (Stage 15B). Plain data: the template prints it, never computes it."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Party:
    """The executor or the client block of a document."""

    name: str
    tax_id: str | None = None
    address_lines: tuple[str, ...] = ()
    phone: str | None = None
    email: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentMeta:
    title: str
    issued_on: date
    number: str | None = None
    place: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentLayout:
    meta: DocumentMeta
    executor: Party | None = None
    client: Party | None = None
    signatures: bool = False
