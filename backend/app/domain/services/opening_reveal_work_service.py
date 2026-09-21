"""Opening reveal work planning service (Stage 10D / D19 / 12D).

Manages the per-opening ordered list of PriceCategory.REVEAL work items.
The Opening entity is the scope header; this service manages its child rows.

Rules:
- price_item must have category=REVEAL
- reveal must be enabled on the opening
- archived items cannot increase their count in a replacement (reduction only)
- duplicate price_item_id values within the same opening are allowed

Stage 12D adds an optional coefficient selection PER OCCURRENCE, mirroring
`SurfaceWorkPlanService` exactly: validated in full before any mutation, then
deleted/recreated atomically together with its parent
`OpeningRevealPlannedWork` row on every ordinary replace. The public
`set_works`/`apply_to_room_openings` signatures keep their original
`price_item_ids: list[uuid.UUID]` shape unchanged (dozens of existing tests
call them this way); coefficient selection is a purely additive parameter
that defaults to "none", so every existing caller is unaffected.
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
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.models.opening import Opening
from app.models.opening_reveal_planned_work import (
    OpeningRevealPlannedWork,
    OpeningRevealPlannedWorkCoefficientAssignment,
)
from app.models.price_coefficient import CoefficientOption
from app.models.price_item import PriceCategory, PriceItem

# One resolved planned-work occurrence: the validated PriceItem plus its
# validated, owner-scoped, order-preserved CoefficientOption selection.
ResolvedOccurrence = tuple[PriceItem, list[CoefficientOption]]


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
            .options(
                selectinload(OpeningRevealPlannedWork.price_item),
                selectinload(OpeningRevealPlannedWork.coefficient_assignments)
                .selectinload(
                    OpeningRevealPlannedWorkCoefficientAssignment.coefficient_option
                )
                .selectinload(CoefficientOption.group),
            )
            .order_by(OpeningRevealPlannedWork.position)
            .execution_options(populate_existing=True)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _resolve_items(
        self,
        owner_id: uuid.UUID,
        price_item_ids: list[uuid.UUID],
        existing_counts: Counter[uuid.UUID],
        coefficient_option_ids: list[list[uuid.UUID]] | None = None,
    ) -> list[ResolvedOccurrence]:
        """Validate all requested items and return them in order.

        Active REVEAL items are freely selectable. An archived item's requested
        count must not exceed its currently persisted count (reduction only).
        Duplicates are allowed.

        ``coefficient_option_ids`` (Stage 12D) is an optional parallel array,
        indexed exactly like ``price_item_ids``. When omitted, every
        occurrence gets an empty coefficient selection — this keeps every
        pre-Stage-12D caller unaffected.
        """
        if not price_item_ids:
            return []
        if coefficient_option_ids is None:
            coefficient_option_ids = [[] for _ in price_item_ids]
        elif len(coefficient_option_ids) != len(price_item_ids):
            raise OpeningRevealWorkValidationError(
                "coefficient_option_ids must be parallel to price_item_ids"
            )
        requested_counts: Counter[uuid.UUID] = Counter(price_item_ids)
        rows = (
            await self.db.execute(
                select(PriceItem).where(PriceItem.id.in_(set(price_item_ids)))
            )
        ).scalars().all()
        by_id = {item.id: item for item in rows}
        coefficient_service = PriceCoefficientService(self.db)

        validated: list[ResolvedOccurrence] = []
        for item_id, option_ids in zip(price_item_ids, coefficient_option_ids):
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
            options = await coefficient_service.resolve_assignment_options(
                owner_id, item, option_ids
            )
            validated.append((item, options))
        return validated

    async def _rewrite_works(
        self,
        opening_id: uuid.UUID,
        items: list[ResolvedOccurrence],
    ) -> None:
        """Atomically replace all work rows for this opening.

        Unlike SurfaceWorkPlan, Opening has no ORM relationship collection
        over OpeningRevealPlannedWork, so nothing here ever calls `.clear()`
        on a cascading parent collection -- any previously-loaded old work/
        assignment objects (e.g. from `_fetch_works` in `set_works`) simply
        stay as untouched, unflushed identity-mapped rows once the raw
        DELETE below removes them at the DB; no redundant ORM-issued DELETE
        is ever attempted for them.
        """
        await self.db.execute(
            delete(OpeningRevealPlannedWork).where(
                OpeningRevealPlannedWork.opening_id == opening_id
            )
        )
        for position, (item, options) in enumerate(items):
            work = OpeningRevealPlannedWork(
                opening_id=opening_id,
                price_item_id=item.id,
                position=position,
            )
            for option in options:
                work.coefficient_assignments.append(
                    OpeningRevealPlannedWorkCoefficientAssignment(
                        coefficient_option_id=option.id
                    )
                )
            self.db.add(work)

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
        coefficient_option_ids: list[list[uuid.UUID]] | None = None,
    ) -> list[OpeningRevealPlannedWork]:
        """Fully replace the reveal work list for an opening.

        The opening must have reveal_enabled=True. All items must be
        PriceCategory.REVEAL. Archived items may not increase in count.

        ``coefficient_option_ids`` (Stage 12D) is optional and, when given,
        must be parallel to ``price_item_ids``. Every existing caller passes
        only ``price_item_ids`` and is unaffected.
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
        items = await self._resolve_items(
            owner_id, price_item_ids, existing_counts, coefficient_option_ids
        )
        await self._rewrite_works(opening_id, items)
        await self.db.commit()
        return await self._fetch_works(opening_id)

    async def apply_to_room_openings(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        source_opening_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[Opening]:
        """Atomically copy a source opening's reveal work selection to every
        other reveal-enabled, non-archived opening in the same room
        (Stage 10G.4 — analogous to SurfaceWorkPlanService.apply_to_room_walls).

        Only the ordered PriceItem selection is copied. Geometry, reveal
        depth/sides, and every Estimate-derived quantity (REVEAL_LENGTH /
        REVEAL_AREA) stay entirely opening-specific and backend-authoritative
        — never copied from the source. The whole batch commits together or
        not at all: every source-side validation runs before any target
        mutation, so a failed apply cannot leave half the room updated.

        Precedent-consistent with apply_to_room_walls: the source opening
        itself is excluded from targets (it already holds this exact state).
        """
        from app.models.surface import Surface

        source = await self._fetch_opening(
            source_opening_id, owner_id,
            project_id=project_id, room_id=room_id,
        )
        if not source.reveal_enabled:
            raise OpeningRevealWorkValidationError(
                f"Opening {source_opening_id} does not have reveal enabled; "
                "enable reveal geometry before applying reveal works to the room"
            )
        if source.is_archived:
            raise OpeningRevealWorkValidationError(
                "an archived opening cannot start apply-to-room-openings"
            )

        source_works = await self._fetch_works(source.id)

        # New target rows must never silently reference an archived catalog
        # item — mirrors the existing SurfaceWorkPlan apply-to-room-walls
        # rule exactly, and rejects the whole batch atomically rather than
        # partially applying. The same rule applies to each occurrence's
        # coefficient selection (Stage 12D): an archived option or group is
        # rejected rather than silently copied.
        validated_items: list[ResolvedOccurrence] = []
        for work in source_works:
            item = work.price_item
            if item is None or item.is_archived:
                raise OpeningRevealWorkValidationError(
                    f"Source reveal work references an archived price item "
                    f"{work.price_item_id}; update the source selection first"
                )
            options = work.coefficient_options
            for option in options:
                if option.is_archived or option.group.is_archived:
                    raise OpeningRevealWorkValidationError(
                        "Source reveal work references an archived "
                        f"coefficient option {option.id}; update the source "
                        "selection first"
                    )
            validated_items.append((item, options))

        targets = (
            await self.db.execute(
                select(Opening)
                .join(Surface, Opening.surface_id == Surface.id)
                .where(
                    Surface.room_id == room_id,
                    Opening.id != source.id,
                    Opening.reveal_enabled.is_(True),
                    Opening.is_archived.is_(False),
                    Surface.is_archived.is_(False),
                )
                .order_by(Opening.created_at)
            )
        ).scalars().all()

        for target in targets:
            await self._rewrite_works(target.id, validated_items)

        await self.db.commit()
        return list(targets)

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
