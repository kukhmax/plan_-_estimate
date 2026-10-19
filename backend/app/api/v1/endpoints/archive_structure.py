"""The archived rooms, surfaces and inspections across all objects (archive cleanup AC-4a): thin read-only routes over `ArchiveStructureService`."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.domain.services.archive_structure_service import ArchiveStructureService
from app.models.user import User
from app.schemas.archive_structure import (
    ArchivedInspectionItem,
    ArchivedInspectionsResponse,
    ArchivedRoomItem,
    ArchivedStructureResponse,
    ArchivedSurfaceItem,
)

router = APIRouter()


@router.get(
    "/archive/structure",
    response_model=ArchivedStructureResponse,
    summary="Archived rooms and surfaces of all objects in work, with the object (read-only)",
)
async def list_archived_structure(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArchivedStructureResponse:
    found = await ArchiveStructureService(db).list_archived(current_user.id)
    return ArchivedStructureResponse(
        rooms=[
            ArchivedRoomItem(id=item.room.id, name=item.room.name, project_id=item.project_id, project_name=item.project_name)
            for item in found.rooms
        ],
        surfaces=[
            ArchivedSurfaceItem(
                id=item.surface.id,
                name=item.surface.name,
                surface_type=item.surface.surface_type,
                room_id=item.surface.room_id,
                room_name=item.room_name,
                project_id=item.project_id,
                project_name=item.project_name,
            )
            for item in found.surfaces
        ],
        rooms_total=found.rooms_total,
        surfaces_total=found.surfaces_total,
    )


@router.get(
    "/archive/inspections",
    response_model=ArchivedInspectionsResponse,
    summary="Archived inspections (Badania podłoża) of all objects in work, with the object, room and wall (read-only)",
)
async def list_archived_inspections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArchivedInspectionsResponse:
    found = await ArchiveStructureService(db).list_archived_inspections(current_user.id)
    return ArchivedInspectionsResponse(
        items=[
            ArchivedInspectionItem(
                id=item.inspection.id,
                status=item.inspection.status,
                substrate=item.inspection.substrate,
                quality_target=item.inspection.quality_target,
                plane=item.inspection.plane,
                created_at=item.inspection.created_at,
                completed_at=item.inspection.completed_at,
                room_id=item.inspection.room_id,
                room_name=item.room_name,
                surface_id=item.inspection.surface_id,
                surface_name=item.surface.name if item.surface else None,
                surface_type=item.surface.surface_type if item.surface else None,
                project_id=item.project_id,
                project_name=item.project_name,
            )
            for item in found.items
        ],
        total=found.total,
    )
