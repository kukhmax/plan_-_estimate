"""Notes of the owner on an object (Stage 18)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project_note import MAX_NOTE_LENGTH
from app.schemas.client_id import ClientId


class ProjectNoteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_NOTE_LENGTH)


class ProjectNoteCreate(ProjectNoteWrite):
    id: ClientId


class ProjectNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime


class ProjectNoteListResponse(BaseModel):
    items: list[ProjectNoteRead]
    total: int
