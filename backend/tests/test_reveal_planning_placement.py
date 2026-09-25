"""Owner walkthrough correction: reveal work is planned per opening.

Stage 10 D19 makes `OpeningRevealPlannedWork` the canonical place for
`PriceCategory.REVEAL` work; the Surface work plan never restricted it by
accident. Surface plans may now keep legacy reveal occurrences (never
deleted or moved) but cannot gain new ones, apply-to-all will not copy them,
and a legacy Surface reveal occurrence stays an unresolved quantity in the
Estimate (never the wall's net area, never an aggregate that could silently
double-count per-opening lines). Per-opening reveal coefficients stay
independent.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domain.exceptions import EstimateValidationError, SurfaceWorkPlanValidationError
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from app.models.estimate import QuantitySource
from app.models.opening import OpeningType
from app.models.price_item import PriceCategory, PriceUnit
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.schemas.work_plan import OrderedPriceItemSelection
from tests.test_estimates import (
    _make_opening,
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
    _make_user,
)
from tests.test_planned_work_coefficient_assignments import _make_group_with_options

Sel = OrderedPriceItemSelection


async def _scenario(db, telegram_id):
    """Wall with a window (5.500 mb / 1.100 m2) and a door (5.100 mb / 1.020 m2)."""
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    window = await _make_opening(
        db, surface.id, width="1.500", height="2.000", reveal_depth="0.200",
        reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
    )
    door = await _make_opening(
        db, surface.id, opening_type=OpeningType.DOOR, width="0.900", height="2.100",
        reveal_depth="0.200", reveal_left=True, reveal_right=True, reveal_top=True,
        reveal_bottom=False,
    )
    reveal_item = await _make_price_item(
        db, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM, price="20.00"
    )
    return user, project, room, surface, window, door, reveal_item


async def _set_plan(db, project, room, surface, user, selections):
    return await SurfaceWorkPlanService(db).set_plan(
        project.id, room.id, surface.id, user.id,
        substrate=Substrate.GYPSUM_PLASTER, planned_works=selections,
    )


async def _insert_legacy_surface_reveal(db, project, room, surface, user, item, other_item):
    """A plan created before the guard existed: persisted directly, as the old
    unrestricted Surface picker allowed."""
    plan = await _set_plan(db, project, room, surface, user, [Sel(price_item_id=other_item.id)])
    db.add(SurfacePlannedWork(work_plan_id=plan.id, price_item_id=item.id, position=1))
    await db.commit()
    return plan


async def _surface_items(db, surface_id):
    plan_id = (
        await db.execute(select(SurfaceWorkPlan.id).where(SurfaceWorkPlan.surface_id == surface_id))
    ).scalar_one_or_none()
    if plan_id is None:
        return None
    return list(
        (
            await db.execute(
                select(SurfacePlannedWork.price_item_id)
                .where(SurfacePlannedWork.work_plan_id == plan_id)
                .order_by(SurfacePlannedWork.position)
            )
        ).scalars()
    )


class TestSurfacePlacementGuard:
    async def test_new_reveal_item_on_a_surface_plan_is_rejected(self, db_session):
        user, project, room, surface, _, _, item = await _scenario(db_session, 1400001)
        ids = (project.id, room.id, surface.id, user.id, item.id)
        with pytest.raises(SurfaceWorkPlanValidationError, match="reveal work belongs under an opening"):
            await _set_plan(db_session, project, room, surface, user, [Sel(price_item_id=item.id)])
        await db_session.rollback()
        assert await _surface_items(db_session, ids[2]) is None

    async def test_legacy_surface_reveal_occurrence_is_kept_readable_and_resavable(self, db_session):
        user, project, room, surface, _, _, item = await _scenario(db_session, 1400002)
        paint = await _make_price_item(db_session, user.id, category=PriceCategory.PAINTING)
        await _insert_legacy_surface_reveal(db_session, project, room, surface, user, item, paint)

        plan = await SurfaceWorkPlanService(db_session).get_work_plan(
            project.id, room.id, surface.id, user.id
        )
        assert [w.price_item_id for w in plan.planned_works] == [paint.id, item.id]

        # Re-saving the unchanged plan (e.g. after editing another occurrence) works.
        await _set_plan(db_session, project, room, surface, user, [
            Sel(price_item_id=paint.id), Sel(price_item_id=item.id),
        ])
        assert await _surface_items(db_session, surface.id) == [paint.id, item.id]

        ids = SimpleIds(project.id, room.id, surface.id, user.id, paint.id, item.id)
        # A second copy would be a NEW surface reveal occurrence.
        with pytest.raises(SurfaceWorkPlanValidationError):
            await SurfaceWorkPlanService(db_session).set_plan(
                ids.project, ids.room, ids.surface, ids.user,
                substrate=Substrate.GYPSUM_PLASTER,
                planned_works=[Sel(price_item_id=ids.paint), Sel(price_item_id=ids.item),
                               Sel(price_item_id=ids.item)],
            )
        await db_session.rollback()
        assert await _surface_items(db_session, ids.surface) == [ids.paint, ids.item]

        # The owner can remove it explicitly.
        await SurfaceWorkPlanService(db_session).set_plan(
            ids.project, ids.room, ids.surface, ids.user,
            substrate=Substrate.GYPSUM_PLASTER, planned_works=[Sel(price_item_id=ids.paint)],
        )
        assert await _surface_items(db_session, ids.surface) == [ids.paint]

    async def test_apply_to_all_refuses_to_copy_a_legacy_reveal_occurrence(self, db_session):
        user, project, room, surface, _, _, item = await _scenario(db_session, 1400003)
        target = await _make_surface(db_session, room.id)
        paint = await _make_price_item(db_session, user.id, category=PriceCategory.PAINTING)
        await _insert_legacy_surface_reveal(db_session, project, room, surface, user, item, paint)
        ids = SimpleIds(project.id, room.id, surface.id, user.id, paint.id, item.id)
        target_id = target.id
        with pytest.raises(SurfaceWorkPlanValidationError, match="reveal work belongs under an opening"):
            await SurfaceWorkPlanService(db_session).apply_to_room_walls(
                ids.project, ids.room, ids.surface, ids.user,
            )
        await db_session.rollback()
        assert await _surface_items(db_session, target_id) is None
        assert await _surface_items(db_session, ids.surface) == [ids.paint, ids.item]


class SimpleIds:
    def __init__(self, project, room, surface, user, paint, item):
        self.project, self.room, self.surface, self.user = project, room, surface, user
        self.paint, self.item = paint, item


class TestLegacySurfaceRevealEstimate:
    @pytest.mark.parametrize("unit", [PriceUnit.LM, PriceUnit.M2])
    async def test_legacy_surface_reveal_stays_unresolved_and_blocks_finalize(self, db_session, unit):
        user, project, room, surface, _, _, _ = await _scenario(
            db_session, 1400010 if unit == PriceUnit.LM else 1400011
        )
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL, unit=unit, price="20.00"
        )
        paint = await _make_price_item(
            db_session, user.id, category=PriceCategory.PAINTING, unit=PriceUnit.M2, price="10.00"
        )
        await _insert_legacy_surface_reveal(db_session, project, room, surface, user, item, paint)
        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        reveal_line = next(line for line in estimate.lines if line.price_item_id == item.id)
        paint_line = next(line for line in estimate.lines if line.price_item_id == paint.id)
        # Never the wall net area (M2) and never an aggregate of opening reveals.
        assert reveal_line.quantity_source == QuantitySource.MANUAL
        assert reveal_line.source_quantity is None
        assert paint_line.quantity_source == QuantitySource.SURFACE_NET_AREA
        with pytest.raises(EstimateValidationError):
            await EstimateService(db_session).finalize(estimate.id, user.id, project.id)

    async def test_ordinary_lm_item_on_surface_unchanged(self, db_session):
        user, project, room, surface, _, _, _ = await _scenario(db_session, 1400012)
        crack = await _make_price_item(
            db_session, user.id, category=PriceCategory.SKIM_COAT, unit=PriceUnit.LM, price="8.00"
        )
        await _set_plan(db_session, project, room, surface, user, [Sel(price_item_id=crack.id)])
        line = (await EstimateService(db_session).generate_estimate(project.id, user.id)).lines[0]
        assert line.quantity_source == QuantitySource.MANUAL
        assert line.source_quantity is None


class TestPerOpeningRevealCoefficients:
    async def _plan_window_and_door(self, db_session, telegram_id):
        user, project, room, surface, window, door, item = await _scenario(db_session, telegram_id)
        _, height = await _make_group_with_options(db_session, user.id, percentages=["0", "15"])
        reveal = OpeningRevealWorkService(db_session)
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[height[1].id]])
        await reveal.set_works(door.id, user.id, [item.id])
        return user, project, room, surface, window, door, item, height, reveal

    async def test_window_plus_15_and_door_at_base_price(self, db_session):
        user, project, room, surface, window, door, item, height, _ = await self._plan_window_and_door(
            db_session, 1400020
        )
        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        by_opening = {line.opening_id: line for line in estimate.lines}
        w, d = by_opening[window.id], by_opening[door.id]
        assert w.quantity_source == QuantitySource.REVEAL_LENGTH
        assert (w.quantity, w.base_unit_price, w.unit_price, w.amount) == (
            Decimal("5.500"), Decimal("20.00"), Decimal("23.00"), Decimal("126.50"),
        )
        assert (d.quantity, d.unit_price, d.amount) == (
            Decimal("5.100"), Decimal("20.00"), Decimal("102.00"),
        )
        assert d.coefficient_snapshot == []

    async def test_changing_window_coefficient_leaves_door_and_surface_untouched(self, db_session):
        user, project, room, surface, window, door, item, height, reveal = await self._plan_window_and_door(
            db_session, 1400021
        )
        paint = await _make_price_item(
            db_session, user.id, category=PriceCategory.PAINTING, unit=PriceUnit.M2, price="10.00"
        )
        _, access = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        await _set_plan(db_session, project, room, surface, user, [
            Sel(price_item_id=paint.id, coefficient_option_ids=[access[1].id]),
        ])
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[height[0].id]])

        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        by_opening = {line.opening_id: line for line in estimate.lines}
        assert by_opening[window.id].unit_price == Decimal("20.00")
        assert by_opening[door.id].unit_price == Decimal("20.00")
        assert by_opening[door.id].coefficient_snapshot == []
        surface_line = by_opening[None]
        assert surface_line.unit_price == Decimal("11.00")

    async def test_historical_final_snapshot_unchanged(self, db_session):
        user, project, room, surface, window, door, item, height, reveal = await self._plan_window_and_door(
            db_session, 1400022
        )
        service = EstimateService(db_session)
        estimate = await service.generate_estimate(project.id, user.id)
        await service.finalize(estimate.id, user.id, project.id)
        await PriceCoefficientService(db_session).update_option(
            user.id, height[1].id, percentage=Decimal("50")
        )
        await reveal.set_works(window.id, user.id, [item.id])
        fresh = await service.get_estimate_detail(project.id, estimate.id, user.id)
        window_line = next(line for line in fresh.lines if line.opening_id == window.id)
        assert window_line.unit_price == Decimal("23.00")
        assert window_line.amount == Decimal("126.50")

    async def test_legacy_surface_and_opening_reveal_never_silently_double_price(self, db_session):
        user, project, room, surface, window, door, item, height, _ = await self._plan_window_and_door(
            db_session, 1400023
        )
        paint = await _make_price_item(db_session, user.id, category=PriceCategory.PAINTING)
        await _insert_legacy_surface_reveal(db_session, project, room, surface, user, item, paint)
        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        reveal_lines = [line for line in estimate.lines if line.price_item_id == item.id]
        assert len(reveal_lines) == 3  # window, door, legacy surface -- all kept honestly
        surface_reveal = next(line for line in reveal_lines if line.opening_id is None)
        assert surface_reveal.quantity_source == QuantitySource.MANUAL
        assert surface_reveal.amount == Decimal("0.00")
        with pytest.raises(EstimateValidationError):
            await EstimateService(db_session).finalize(estimate.id, user.id, project.id)
