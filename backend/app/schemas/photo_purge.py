"""Schemas of the final deletion of photos (archive cleanup AC-2)."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class PurgeBlockerRead(BaseModel):
    kind: str  # CONCEALED_WORKS | DOWNTIME | ACCEPTANCE
    protocol_id: uuid.UUID
    status: str


class PhotoPurgePreview(BaseModel):
    """What the final deletion would remove -- computed by the server, no side effects."""

    attachment_id: uuid.UUID
    trashed: bool
    can_purge: bool
    annotations: int  # the markers of this photo
    other_attachments: int  # other uses of the same file (it is deleted only with its last use)
    deletes_files: bool
    files: int  # objects removed from the storage: 3 (original, display, thumbnail) or 0
    bytes: int
    may_be_in_backups: bool  # the copies in the backups are removed by the owner's separate step
    blockers: list[PurgeBlockerRead]


class PhotoPurgeResult(BaseModel):
    purged: bool
    deleted_files: bool  # the file set was removed with this photo
    storage_pending: bool  # the storage did not answer: the rows are gone, the objects are removed by a retry


class PhotoPurgeStatus(BaseModel):
    storage_pending: int  # deleted photos whose objects are not yet removed from the working storage
    backup_pending: int  # deleted photos whose copies are not yet removed from the backups
    last_purged_at: datetime | None
