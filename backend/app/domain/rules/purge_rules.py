"""Rules of the final deletion of a photo (archive cleanup AC-2) -- pure functions, no database.

A photo that a protocol of the object still points to is evidence and is not deleted: the protocol would lose it without a trace. The
protocols point to photos by the id of the attachment inside JSON (no foreign key), so the database cannot guard this; this rule does.
A protocol that is ARCHIVED no longer blocks. A DRAFT does (the owner removes the photo from the draft first, or archives the draft).
"""
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

BLOCKING_EXCEPT_STATUS = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class ProtocolRef:
    kind: str  # CONCEALED_WORKS | DOWNTIME | ACCEPTANCE
    id: uuid.UUID
    status: str
    photo_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class Blocker:
    kind: str
    protocol_id: uuid.UUID
    status: str


def acceptance_photo_ids(surfaces: Mapping[str, Any] | None) -> frozenset[str]:
    """The photo ids in the remarks of an acceptance protocol: `{surface_id: {"remarks": {remark_id: {"photo_ids": [...]}}}}`
    (a list of remarks is read too, so a change of the stored shape cannot silently stop the protection)."""
    found: set[str] = set()
    for surface in (surfaces or {}).values():
        remarks = surface.get("remarks") if isinstance(surface, Mapping) else None
        if isinstance(remarks, Mapping):
            remarks = list(remarks.values())
        for remark in remarks or []:
            if isinstance(remark, Mapping):
                found.update(str(p) for p in remark.get("photo_ids") or [])
    return frozenset(found)


def photo_blockers(attachment_id: uuid.UUID, protocols: Iterable[ProtocolRef]) -> list[Blocker]:
    wanted = str(attachment_id)
    return [
        Blocker(ref.kind, ref.id, ref.status)
        for ref in protocols
        if ref.status != BLOCKING_EXCEPT_STATUS and wanted in ref.photo_ids
    ]
