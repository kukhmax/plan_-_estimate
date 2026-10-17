"""Schemas of the archived rooms and surfaces across all objects (archive cleanup AC-4a)."""
import uuid

from pydantic import BaseModel

from app.models.surface import SurfaceType


class ArchivedRoomItem(BaseModel):
    id: uuid.UUID
    name: str
    project_id: uuid.UUID
    project_name: str


class ArchivedSurfaceItem(BaseModel):
    id: uuid.UUID
    name: str
    surface_type: SurfaceType
    room_id: uuid.UUID
    room_name: str
    project_id: uuid.UUID
    project_name: str


class ArchivedStructureResponse(BaseModel):
    rooms: list[ArchivedRoomItem]
    surfaces: list[ArchivedSurfaceItem]
    rooms_total: int  # the lists hold the first 200; the totals are whole
    surfaces_total: int
