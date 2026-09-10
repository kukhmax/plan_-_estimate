from decimal import Decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    DeductionExceedsGrossAreaError,
    InvalidSurfaceTypeError,
    OpeningNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.models.opening import Opening
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.schemas.opening import OpeningCreate, OpeningUpdate


class OpeningService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_surface_owned(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Surface:
        project_stmt = select(Project.id).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
        )
        project_result = await self.db.execute(project_stmt)
        if project_result.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        room_stmt = select(Room.id).where(
            Room.id == room_id,
            Room.project_id == project_id,
        )
        room_result = await self.db.execute(room_stmt)
        if room_result.scalar_one_or_none() is None:
            raise RoomNotFoundError(f"Room {room_id} not found")

        surface_stmt = select(Surface).where(
            Surface.id == surface_id,
            Surface.room_id == room_id,
        )
        surface_result = await self.db.execute(surface_stmt)
        surface = surface_result.scalar_one_or_none()
        if surface is None:
            raise SurfaceNotFoundError(f"Surface {surface_id} not found")

        return surface

    async def _get_active_deductions_sum(
        self,
        surface_id: uuid.UUID,
        exclude_opening_id: uuid.UUID | None = None,
    ) -> Decimal:
        stmt = select(
            func.coalesce(
                func.sum(Opening.width * Opening.height * Opening.quantity), 0
            )
        ).where(
            Opening.surface_id == surface_id,
            Opening.is_archived.is_(False),
        )
        if exclude_opening_id is not None:
            stmt = stmt.where(Opening.id != exclude_opening_id)

        result = await self.db.execute(stmt)
        return Decimal(result.scalar_one()).quantize(Decimal("0.001"))

    async def list_openings(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> tuple[list[Opening], int]:
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)

        stmt = select(Opening).where(Opening.surface_id == surface_id)
        if not include_archived:
            stmt = stmt.where(Opening.is_archived.is_(False))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(Opening.created_at.desc())
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def create_opening(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        payload: OpeningCreate,
        owner_id: uuid.UUID,
    ) -> Opening:
        surface = await self._ensure_surface_owned(
            project_id, room_id, surface_id, owner_id
        )

        if surface.surface_type != SurfaceType.WALL:
            raise InvalidSurfaceTypeError(
                f"Openings can only be attached to WALL surfaces, got {surface.surface_type.value}"
            )

        new_opening_area = (
            payload.width * payload.height * Decimal(payload.quantity)
        ).quantize(Decimal("0.001"))

        current_deductions = await self._get_active_deductions_sum(surface_id)
        total_deductions = current_deductions + new_opening_area

        if surface.width is not None and surface.height is not None:
            gross_area = (surface.width * surface.height).quantize(Decimal("0.001"))
            if total_deductions > gross_area:
                raise DeductionExceedsGrossAreaError(
                    f"Total opening deductions ({total_deductions}) would exceed wall gross area ({gross_area})"
                )

        opening = Opening(
            surface_id=surface_id,
            opening_type=payload.opening_type,
            name=payload.name,
            width=payload.width,
            height=payload.height,
            quantity=payload.quantity,
            description=payload.description,
        )
        self.db.add(opening)
        await self.db.commit()
        await self.db.refresh(opening)
        return opening

    async def get_opening(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        opening_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Opening:
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)

        stmt = select(Opening).where(
            Opening.id == opening_id,
            Opening.surface_id == surface_id,
        )
        result = await self.db.execute(stmt)
        opening = result.scalar_one_or_none()
        if not opening:
            raise OpeningNotFoundError(f"Opening {opening_id} not found")
        return opening

    async def update_opening(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        opening_id: uuid.UUID,
        payload: OpeningUpdate,
        owner_id: uuid.UUID,
    ) -> Opening:
        surface = await self._ensure_surface_owned(
            project_id, room_id, surface_id, owner_id
        )
        opening = await self.get_opening(
            project_id, room_id, surface_id, opening_id, owner_id
        )

        target_width = payload.width if payload.width is not None else opening.width
        target_height = payload.height if payload.height is not None else opening.height
        target_quantity = (
            payload.quantity if payload.quantity is not None else opening.quantity
        )
        new_area = (target_width * target_height * Decimal(target_quantity)).quantize(
            Decimal("0.001")
        )

        if not opening.is_archived:
            other_deductions = await self._get_active_deductions_sum(
                surface_id, exclude_opening_id=opening_id
            )
            total_deductions = other_deductions + new_area
            if surface.width is not None and surface.height is not None:
                gross_area = (surface.width * surface.height).quantize(Decimal("0.001"))
                if total_deductions > gross_area:
                    raise DeductionExceedsGrossAreaError(
                        f"Total opening deductions ({total_deductions}) would exceed wall gross area ({gross_area})"
                    )

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(opening, field, value)

        await self.db.commit()
        await self.db.refresh(opening)
        return opening

    async def archive_opening(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        opening_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Opening:
        opening = await self.get_opening(
            project_id, room_id, surface_id, opening_id, owner_id
        )
        opening.is_archived = True
        await self.db.commit()
        await self.db.refresh(opening)
        return opening

    async def restore_opening(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        opening_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Opening:
        surface = await self._ensure_surface_owned(
            project_id, room_id, surface_id, owner_id
        )
        opening = await self.get_opening(
            project_id, room_id, surface_id, opening_id, owner_id
        )

        # Validate that restoring does not exceed gross area
        opening_area = (
            opening.width * opening.height * Decimal(opening.quantity)
        ).quantize(Decimal("0.001"))
        current_deductions = await self._get_active_deductions_sum(surface_id)
        total_deductions = current_deductions + opening_area

        if surface.width is not None and surface.height is not None:
            gross_area = (surface.width * surface.height).quantize(Decimal("0.001"))
            if total_deductions > gross_area:
                raise DeductionExceedsGrossAreaError(
                    f"Restoring opening with deduction ({opening_area}) would exceed wall gross area ({gross_area})"
                )

        opening.is_archived = False
        await self.db.commit()
        await self.db.refresh(opening)
        return opening
