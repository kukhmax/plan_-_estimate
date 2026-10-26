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
    kind: str  # CONCEALED_WORKS | PRESSURE_TEST | DOWNTIME | ACCEPTANCE
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


# -- the final deletion of an object (archive cleanup AC-5b) ----------------------------------------------------------------------------

# What an object keeps once a document has gone out to the client: an issued or signed contract, an issued protocol, a downtime notice
# that was given or closed. They are evidence (the warranty, a dispute over quality), so such an object is only archived, never deleted.
# DRAFT and ARCHIVED documents do not block: they are deleted with the object. The set is the owner's decision Q2 of the plan.
OBJECT_BLOCKING_STATUSES: dict[str, frozenset[str]] = {
    "CONTRACT": frozenset({"ISSUED", "SIGNED"}),
    "HANDOVER": frozenset({"ISSUED"}),
    "CONCEALED_WORKS": frozenset({"ISSUED"}),
    "PRESSURE_TEST": frozenset({"ISSUED"}),
    "DECISION": frozenset({"ISSUED"}),
    "ACCEPTANCE": frozenset({"ISSUED"}),
    "DOWNTIME": frozenset({"NOTICED", "CLOSED"}),
}


@dataclass(frozen=True, slots=True)
class DocumentRef:
    kind: str  # a key of OBJECT_BLOCKING_STATUSES
    id: uuid.UUID
    status: str


def object_blockers(documents: Iterable[DocumentRef]) -> list[Blocker]:
    """The documents of an object that forbid deleting it (an unknown kind blocks nothing: the caller names only the known kinds)."""
    return [
        Blocker(ref.kind, ref.id, ref.status)
        for ref in documents
        if ref.status in OBJECT_BLOCKING_STATUSES.get(ref.kind, frozenset())
    ]


# -- the final deletion of a room or a surface (archive cleanup AC-4b) ---------------------------------------------------------------------

def structure_blockers(documents: Iterable[DocumentRef]) -> list[Blocker]:
    """The documents that still point to the room / surface and so forbid deleting it: every one that is not ARCHIVED (a draft, an issued
    protocol, a notice, a work of an adjacent trade that is in force). The caller gives only the documents that point to it. An archived
    document keeps its snapshot and no longer holds anything -- the same rule as for the photos of a protocol (AC-2)."""
    seen: set[tuple[str, uuid.UUID]] = set()
    found: list[Blocker] = []
    for ref in documents:
        if ref.status == BLOCKING_EXCEPT_STATUS or (ref.kind, ref.id) in seen:
            continue
        seen.add((ref.kind, ref.id))
        found.append(Blocker(ref.kind, ref.id, ref.status))
    return found
