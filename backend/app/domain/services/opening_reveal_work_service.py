"""Opening reveal work planning service (Stage 10D / D19).

Manages the per-opening ordered list of PriceCategory.REVEAL work items.
The Opening entity is the scope header; this service manages its child rows.

Rules:
- price_item must have category=REVEAL
- reveal must be enabled on the opening
- archived items cannot increase their count in a replacement (reduction only)
- duplicate price_item_id values within the same opening are allowed
"""
import uuid
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.exceptions import (
    OpeningNotFoundError,
    OpeningRevealWorkValidationError,
    PriceItemNotFoundError,
)
from app.models.opening import Opening
from app.models.opening_reveal_planned_work import OpeningRevealPlannedWork
from app.models.price_item import PriceCategory, PriceItem


class OpeningRevealWorkService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _fetch_opening(
        self,
        opening_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        room_id: uuid.UUID | None = None,
        surface_id: uuid.UUID | None = None,
    ) -> Opening:
        """Return the opening if it belongs to the specified hierarchy and owner.

        When project_id / room_id / surface_id are provided the full path is
        validated to prevent cross-hierarchy access within the same owner.
        """
        from app.models.surface import Surface
        from app.models.room import Room
        from app.models.project import Project

        conditions = [Opening.id == opening_id, Project.owner_id == owner_id]
        if surface_id is not None:
            conditions.append(Opening.surface_id == surface_id)
        if room_id is not None:
            conditions.append(Surface.room_id == room_id)
        if project_id is not None:
            conditions.append(Room.project_id == project_id)

        stmt = (
            select(Opening)
            .join(Surface, Opening.surface_id == Surface.id)
            .join(Room, Surface.room_id == Room.id)
            .join(Project, Room.project_id == Project.id)
            .where(*conditions)
        )
        opening = (await self.db.execute(stmt)).scalar_one_or_none()
        if opening is None:
            raise OpeningNotFoundError(f"Opening {opening_id} not found")
        return opening

    async def _fetch_works(
        self, opening_id: uuid.UUID
    ) -> list[OpeningRevealPlannedWork]:
        stmt = (
            select(OpeningRevealPlannedWork)
            .where(OpeningRevealPlannedWork.opening_id == opening_id)
            .options(selectinload(OpeningRevealPlannedWork.price_item))
            .order_by(OpeningRevealPlannedWork.position)
            .execution_options(populate_existing=True)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _resolve_items(
        self,
        owner_id: uuid.UUID,
        price_item_ids: list[uuid.UUID],
        existing_counts: Counter[uuid.UUID],
    ) -> list[PriceItem]:
        """Validate all requested items and return them in order.

        Active REVEAL items are freely selectable. An archived item's requested
        count must not exceed its currently persisted count (reduction only).
        Duplicates are allowed.
        """
        if not price_item_ids:
            return []
        requested_counts: Counter[uuid.UUID] = Counter(price_item_ids)
        rows = (
            await self.db.execute(
                select(PriceItem).where(PriceItem.id.in_(set(price_item_ids)))
            )
        ).scalars().all()
        by_id = {item.id: item for item in rows}

        validated: list[PriceItem] = []
        for item_id in price_item_ids:
            item = by_id.get(item_id)
            if item is None or item.owner_id != owner_id:
                raise PriceItemNotFoundError(
                    f"Price item {item_id} not found"
                )
            if item.category != PriceCategory.REVEAL:
                raise OpeningRevealWorkValidationError(
                    f"Price item {item_id} is not a REVEAL category item"
                )
            if (
                item.is_archived
                and requested_counts[item.id] > existing_counts[item.id]
            ):
                raise OpeningRevealWorkValidationError(
                    f"Archived price item {item_id} cannot be added to reveal work"
                )
            validated.append(item)
        return validated

    async def _rewrite_works(
        self,
        opening_id: uuid.UUID,
        items: list[PriceItem],
    ) -> None:
        """Atomically replace all work rows for this opening."""
        await self.db.execute(
            delete(OpeningRevealPlannedWork).where(
                OpeningRevealPlannedWork.opening_id == opening_id
            )
        )
        for position, item in enumerate(items):
            self.db.add(
                OpeningRevealPlannedWork(
                    opening_id=opening_id,
                    price_item_id=item.id,
                    position=position,
                )
            )

    async def get_works(
        self,
        opening_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        room_id: uuid.UUID | None = None,
        surface_id: uuid.UUID | None = None,
    ) -> list[OpeningRevealPlannedWork]:
        """Return the ordered reveal work list for an opening."""
        await self._fetch_opening(
            opening_id, owner_id,
            project_id=project_id, room_id=room_id, surface_id=surface_id,
        )
        return await self._fetch_works(opening_id)

    async def set_works(
        self,
        opening_id: uuid.UUID,
        owner_id: uuid.UUID,
        price_item_ids: list[uuid.UUID],
        project_id: uuid.UUID | None = None,
        room_id: uuid.UUID | None = None,
        surface_id: uuid.UUID | None = None,
    ) -> list[OpeningRevealPlannedWork]:
        """Fully replace the reveal work list for an opening.

        The opening must have reveal_enabled=True. All items must be
        PriceCategory.REVEAL. Archived items may not increase in count.
        """
        opening = await self._fetch_opening(
            opening_id, owner_id,
            project_id=project_id, room_id=room_id, surface_id=surface_id,
        )
        if not opening.reveal_enabled:
            raise OpeningRevealWorkValidationError(
                f"Opening {opening_id} does not have reveal enabled; "
                "enable reveal geometry before selecting reveal works"
            )

        existing = await self._fetch_works(opening_id)
        existing_counts: Counter[uuid.UUID] = Counter(
            w.price_item_id for w in existing
        )
        items = await self._resolve_items(owner_id, price_item_ids, existing_counts)
        await self._rewrite_works(opening_id, items)
        await self.db.commit()
        return await self._fetch_works(opening_id)

    async def clear_works(
        self,
        opening_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        room_id: uuid.UUID | None = None,
        surface_id: uuid.UUID | None = None,
    ) -> None:
        """Remove all reveal work rows for an opening."""
        await self._fetch_opening(
            opening_id, owner_id,
            project_id=project_id, room_id=room_id, surface_id=surface_id,
        )
        await self.db.execute(
            delete(OpeningRevealPlannedWork).where(
                OpeningRevealPlannedWork.opening_id == opening_id
            )
        )
        await self.db.commit()
