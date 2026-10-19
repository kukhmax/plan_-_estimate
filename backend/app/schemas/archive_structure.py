"""Schemas of the archived rooms and surfaces across all objects (archive cleanup AC-4a)."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.area_segment import AreaPlane
from app.models.checklist import QualityLevel, Substrate
from app.models.inspection import InspectionStatus
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


class ArchivedInspectionItem(BaseModel):
    """An archived inspection (Badanie podłoża) with the place it belongs to: the object, the room and the wall (or the floor / ceiling)."""

    id: uuid.UUID
    status: InspectionStatus
    substrate: Substrate
    quality_target: QualityLevel | None
    plane: AreaPlane | None  # FLOOR / CEILING when it targets one; null with no surface = the room itself
    created_at: datetime
    completed_at: datetime | None
    room_id: uuid.UUID
    room_name: str
    surface_id: uuid.UUID | None
    surface_name: str | None
    surface_type: SurfaceType | None
    project_id: uuid.UUID
    project_name: str


class ArchivedInspectionsResponse(BaseModel):
    items: list[ArchivedInspectionItem]
    total: int  # the list holds the first 200; the total is whole
