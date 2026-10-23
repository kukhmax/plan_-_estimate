"""Merged walls: join several walls of a room into one, keep the size of each as a part, and take the walls apart again.

What "merge" does (decisions of the owner, 2026-10-23): the FIRST wall of the request stays; the sizes of all the walls become its parts
(the area is the sum of the parts); the photos and the openings of the other walls move to it; the other walls are archived, not deleted,
and their plans, inspections and history stay with them (the plan of the merged wall is the plan of the first wall). Nothing is merged
when work has started or an issued estimate relies on one of the walls. "Unmerge" gives the moved photos and openings back and restores
the walls; whatever was added to the merged wall afterwards stays on it.
"""

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import SurfaceNotFoundError, WallMergeError
from app.domain.services.surface_service import SurfaceService
from app.domain.services.wall_parts import AREA, load_parts, parts_gross_area
from app.models.estimate import Estimate, EstimateLine, EstimateStatus
from app.models.opening import Opening
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext
from app.models.surface import Surface, SurfaceType
from app.models.surface_part import MergeMoveKind, SurfaceMergeMove, SurfacePart
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfaceWorkPlan

MAX_WALLS = 12


class WallMergeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._surfaces = SurfaceService(db)

    async def _walls(self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID, surface_ids: list[uuid.UUID]) -> list[Surface]:
        await self._surfaces._ensure_room_owned(project_id, room_id, owner_id)
        found = {
            surface.id: surface
            for surface in (
                await self.db.execute(select(Surface).where(Surface.room_id == room_id, Surface.id.in_(surface_ids)))
            ).scalars()
        }
        if len(found) != len(set(surface_ids)):
            raise SurfaceNotFoundError("Surface not found")
        return [found[surface_id] for surface_id in surface_ids]

    async def _check_untouched(self, surfaces: list[Surface]) -> None:
        """No work started on, and no issued estimate relying on, any of the walls."""
        ids = [surface.id for surface in surfaces]
        started = (
            await self.db.execute(
                select(func.count())
                .select_from(SurfaceWorkExecution)
                .join(SurfaceWorkPlan, SurfaceWorkPlan.id == SurfaceWorkExecution.work_plan_id)
                .where(SurfaceWorkPlan.surface_id.in_(ids), SurfaceWorkExecution.status != WorkExecutionStatus.NOT_STARTED)
            )
        ).scalar_one()
        if started:
            raise WallMergeError("WALL_MERGE_WORK_STARTED", "Work has started on one of the walls")
        issued = (
            await self.db.execute(
                select(func.count())
                .select_from(EstimateLine)
                .join(Estimate, Estimate.id == EstimateLine.estimate_id)
                .where(EstimateLine.surface_id.in_(ids), Estimate.status.in_([EstimateStatus.FINAL, EstimateStatus.ACCEPTED]))
            )
        ).scalar_one()
        if issued:
            raise WallMergeError("WALL_MERGE_ESTIMATE_ISSUED", "An issued estimate relies on one of the walls")

    async def merge(self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID, surface_ids: list[uuid.UUID]) -> Surface:
        if len(set(surface_ids)) != len(surface_ids) or len(surface_ids) < 2:
            raise WallMergeError("WALL_MERGE_NEED_TWO", "Choose at least two different walls")
        if len(surface_ids) > MAX_WALLS:
            raise WallMergeError("WALL_MERGE_TOO_MANY", f"At most {MAX_WALLS} walls can be merged")
        walls = await self._walls(project_id, room_id, owner_id, surface_ids)
        for wall in walls:
            if wall.surface_type != SurfaceType.WALL:
                raise WallMergeError("WALL_MERGE_NOT_A_WALL", "Only walls can be merged")
            if wall.is_archived:
                raise WallMergeError("WALL_MERGE_ARCHIVED", "An archived wall cannot be merged")
            if wall.width is None or wall.height is None:
                raise WallMergeError("WALL_MERGE_NO_SIZE", "Every wall needs its width and height")
        involved = set(surface_ids)
        already = (
            await self.db.execute(
                select(func.count()).select_from(SurfacePart).where(
                    or_(SurfacePart.surface_id.in_(involved), SurfacePart.source_surface_id.in_(involved))
                )
            )
        ).scalar_one()
        if already:
            raise WallMergeError("WALL_MERGE_ALREADY_MERGED", "A merged wall cannot be merged again: separate it first")
        await self._check_untouched(walls)

        primary, others = walls[0], walls[1:]
        for position, wall in enumerate(walls):
            self.db.add(
                SurfacePart(surface_id=primary.id, source_surface_id=wall.id, position=position, width=wall.width, height=wall.height)
            )
        other_ids = [wall.id for wall in others]

        photos = (
            await self.db.execute(
                select(PhotoAttachment).where(
                    PhotoAttachment.context == PhotoAttachmentContext.SURFACE, PhotoAttachment.surface_id.in_(other_ids)
                )
            )
        ).scalars().all()
        already_on_primary = set(
            (
                await self.db.execute(
                    select(PhotoAttachment.asset_id).where(
                        PhotoAttachment.context == PhotoAttachmentContext.SURFACE,
                        PhotoAttachment.surface_id == primary.id,
                        PhotoAttachment.archived_at.is_(None),
                    )
                )
            ).scalars()
        )
        for photo in photos:
            # one photo cannot be attached to the same wall twice (active rows): a duplicate stays where it was
            if photo.archived_at is None and photo.asset_id in already_on_primary:
                continue
            self.db.add(SurfaceMergeMove(surface_id=primary.id, kind=MergeMoveKind.PHOTO, item_id=photo.id, from_surface_id=photo.surface_id))
            if photo.archived_at is None:
                already_on_primary.add(photo.asset_id)
            photo.surface_id = primary.id

        openings = (await self.db.execute(select(Opening).where(Opening.surface_id.in_(other_ids)))).scalars().all()
        for opening in openings:
            self.db.add(SurfaceMergeMove(surface_id=primary.id, kind=MergeMoveKind.OPENING, item_id=opening.id, from_surface_id=opening.surface_id))
            opening.surface_id = primary.id

        for wall in others:
            wall.is_archived = True
        await self.db.commit()
        return await self._surfaces.get_surface(project_id, room_id, primary.id, owner_id)

    async def unmerge(self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID, surface_id: uuid.UUID) -> Surface:
        (primary,) = await self._walls(project_id, room_id, owner_id, [surface_id])
        parts = (await load_parts(self.db, [primary.id])).get(primary.id)
        if not parts:
            raise WallMergeError("WALL_UNMERGE_NOT_MERGED", "The wall is not merged")
        if primary.is_archived:
            raise WallMergeError("WALL_UNMERGE_ARCHIVED", "Restore the wall before separating it")
        await self._check_untouched([primary])

        moves = (await self.db.execute(select(SurfaceMergeMove).where(SurfaceMergeMove.surface_id == primary.id))).scalars().all()
        photo_ids = [move.item_id for move in moves if move.kind == MergeMoveKind.PHOTO]
        opening_ids = [move.item_id for move in moves if move.kind == MergeMoveKind.OPENING]
        photos = {
            photo.id: photo
            for photo in (await self.db.execute(select(PhotoAttachment).where(PhotoAttachment.id.in_(photo_ids)))).scalars()
        } if photo_ids else {}
        openings = {
            opening.id: opening
            for opening in (await self.db.execute(select(Opening).where(Opening.id.in_(opening_ids)))).scalars()
        } if opening_ids else {}

        # what stays on the wall (its own openings, and those added after the merge) must still fit its own size
        returning = {move.item_id for move in moves if move.kind == MergeMoveKind.OPENING}
        staying = (
            await self.db.execute(
                select(func.coalesce(func.sum(Opening.width * Opening.height * Opening.quantity), 0)).where(
                    Opening.surface_id == primary.id, Opening.is_archived.is_(False), Opening.id.notin_(returning) if returning else True
                )
            )
        ).scalar_one()
        own_gross = (primary.width * primary.height).quantize(AREA)
        if Decimal(staying) > own_gross:
            raise WallMergeError("WALL_UNMERGE_OPENINGS_EXCEED", "The openings that stay on the wall are larger than the wall")

        for move in moves:
            item = photos.get(move.item_id) if move.kind == MergeMoveKind.PHOTO else openings.get(move.item_id)
            if item is not None and item.surface_id == primary.id:
                item.surface_id = move.from_surface_id
        restored = [part.source_surface_id for part in parts if part.source_surface_id and part.source_surface_id != primary.id]
        if restored:
            for wall in (await self.db.execute(select(Surface).where(Surface.id.in_(restored)))).scalars():
                wall.is_archived = False
        await self.db.execute(delete(SurfaceMergeMove).where(SurfaceMergeMove.surface_id == primary.id))
        await self.db.execute(delete(SurfacePart).where(SurfacePart.surface_id == primary.id))
        await self.db.commit()
        return await self._surfaces.get_surface(project_id, room_id, primary.id, owner_id)

    async def update_part(
        self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID, surface_id: uuid.UUID, part_id: uuid.UUID, width: Decimal, height: Decimal
    ) -> Surface:
        (primary,) = await self._walls(project_id, room_id, owner_id, [surface_id])
        parts = (await load_parts(self.db, [primary.id])).get(primary.id) or []
        part = next((candidate for candidate in parts if candidate.id == part_id), None)
        if part is None:
            raise SurfaceNotFoundError("Part not found")
        new_total = parts_gross_area([*(p for p in parts if p.id != part_id)]) + (width * height).quantize(AREA)
        taken = (
            await self.db.execute(
                select(func.coalesce(func.sum(Opening.width * Opening.height * Opening.quantity), 0)).where(
                    Opening.surface_id == primary.id, Opening.is_archived.is_(False)
                )
            )
        ).scalar_one()
        if Decimal(taken) > new_total:
            raise WallMergeError("WALL_PART_OPENINGS_EXCEED", "The openings of the wall are larger than its new area")
        part.width, part.height = width, height
        if part.source_surface_id == primary.id:
            primary.width, primary.height = width, height  # the first part is the wall's own size
        await self.db.commit()
        return await self._surfaces.get_surface(project_id, room_id, primary.id, owner_id)
