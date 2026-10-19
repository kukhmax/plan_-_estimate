"""Schemas of the final deletion of a room, a surface or an inspection (archive cleanup AC-4b, AC-7)."""
import uuid

from pydantic import BaseModel

from app.schemas.photo_purge import PurgeBlockerRead


class StructurePurgePreview(BaseModel):
    """What deleting the archived room / surface for good would remove -- computed by the server, no side effects."""

    kind: str  # ROOM | SURFACE | INSPECTION
    target_id: uuid.UUID
    name: str
    archived: bool
    can_purge: bool
    surfaces: int  # of a room; 0 for a surface
    openings: int
    inspections: int
    photos: int
    photo_files: int  # file sets (original, display, thumbnail) removed from the storage (those no other photo still uses)
    bytes: int
    annotations: int
    estimate_lines: int  # lines of the estimates that name it: they stay as a record and lose the link
    # what hangs on the inspections that go (of a room / surface: all of theirs)
    answers: int
    findings: int
    risks: int
    recommendations: int
    may_be_in_backups: bool
    # `kind`: CONCEALED_WORKS | ACCEPTANCE | DOWNTIME | ADJACENT_WORK (+ the protocols that use a photo as evidence); `protocol_id` is the id of the document
    blockers: list[PurgeBlockerRead]


class StructurePurgeResult(BaseModel):
    purged: bool
    photo_files: int
    storage_pending: int
