"""Schemas of the final deletion of an object (archive cleanup AC-5b)."""
import uuid

from pydantic import BaseModel

from app.schemas.photo_purge import PurgeBlockerRead


class ProjectPurgePreview(BaseModel):
    """What deleting the object for good would remove -- computed by the server, no side effects."""

    project_id: uuid.UUID
    name: str
    archived: bool
    can_purge: bool
    rooms: int
    surfaces: int
    openings: int
    inspections: int
    estimates: int
    documents: int  # contracts and protocols of every kind, drafts and archived ones included
    sent_documents: int  # documents given to the client: their copies in Telegram chats stay
    photos: int
    photo_files: int  # file sets (original, display, thumbnail) removed from the storage
    bytes: int
    annotations: int
    may_be_in_backups: bool
    blockers: list[PurgeBlockerRead]  # `kind` is a document kind: CONTRACT | HANDOVER | CONCEALED_WORKS | DECISION | ACCEPTANCE | DOWNTIME


class ProjectPurgeResult(BaseModel):
    purged: bool
    photo_files: int
    storage_pending: int  # file sets still to be removed from the storage: a retry finishes them
