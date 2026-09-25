"""Focused Stage 12E tests: Estimate coefficient snapshot, calculation,
preview/change-detection, regeneration, and override/reset integration.

Reuses Stage 10D fixtures from test_estimates.py and the Stage 12D
coefficient-catalog helper from test_planned_work_coefficient_assignments.py.
No coefficient modal/UI, no Q/S/PSG percentages, no fixed-surcharge catalog --
all deferred to later sub-stages.
"""
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.domain.exceptions import EstimateValidationError
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.models.checklist import Substrate
from app.models.estimate import EstimateLine, LineOrigin
from app.models.opening import Opening, OpeningType
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.work_plan import SurfacePlannedWork
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


async def _make_work_plan_with_coefficients(
    db,
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    owner_id: uuid.UUID,
    selections: list[OrderedPriceItemSelection],
):
    from app.domain.services.work_plan_service import SurfaceWorkPlanService

    service = SurfaceWorkPlanService(db)
    return await service.set_plan(
        project_id, room_id, surface_id, owner_id,
        substrate=Substrate.GYPSUM_PLASTER,
        planned_works=selections,
    )


async def _current_keys(db, surface_id):
    """occurrence_keys of the surface's current plan, in position order --
    what the editor echoes on an ordinary (key-preserving) save (13E.2B)."""
    from sqlalchemy import select as _select

    from app.models.work_plan import SurfacePlannedWork as _SPW, SurfaceWorkPlan as _SWP

    rows = await db.execute(
        _select(_SPW.occurrence_key)
        .join(_SWP, _SPW.work_plan_id == _SWP.id)
        .where(_SWP.surface_id == surface_id)
        .order_by(_SPW.position)
    )
    return list(rows.scalars().all())


async def _generate(db, project_id, owner_id):
    return await EstimateService(db).generate_estimate(project_id, owner_id)


# ---------------------------------------------------------------------------
# TestA — calculation matrix (additive, no compounding, exact Decimal)
# ---------------------------------------------------------------------------

class TestA_Calculation:
    async def test_base_40_plus_10_equals_44(self, db_session):
        user = await _make_user(db_session, 5000001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        assert line.base_unit_price == Decimal("40.00")
        assert line.unit_price == Decimal("44.00")

    async def test_base_40_plus_10_plus_20_equals_52(self, db_session):
        user = await _make_user(db_session, 5000002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        g1, g1_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        g2, g2_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "20"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id,
                coefficient_option_ids=[g1_opts[1].id, g2_opts[1].id],
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("52.00")

    async def test_base_40_plus_10_plus_20_plus_10_equals_56(self, db_session):
        user = await _make_user(db_session, 5000003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        g1, g1_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        g2, g2_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "20"]
        )
        g3, g3_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id,
                coefficient_option_ids=[g1_opts[1].id, g2_opts[1].id, g3_opts[1].id],
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("56.00")

    async def test_base_40_minus_10_equals_36(self, db_session):
        user = await _make_user(db_session, 5000004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "-10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("36.00")

    async def test_base_40_plus_0_equals_40(self, db_session):
        user = await _make_user(db_session, 5000005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[0].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("40.00")

    async def test_zero_base_plus_20_equals_zero(self, db_session):
        user = await _make_user(db_session, 5000006)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="0.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "20"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        assert line.base_unit_price == Decimal("0.00")
        assert line.unit_price == Decimal("0.00")

    async def test_null_base_plus_20_stays_null(self, db_session):
        user = await _make_user(db_session, 5000007)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price=None)
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "20"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        assert line.base_unit_price is None
        assert line.unit_price is None
        # Coefficient configuration is still captured (Sec 9).
        assert len(line.coefficient_snapshot) == 1
        assert line.coefficient_snapshot[0]["percentage"] == "20.000"

    async def test_negative_groups_summing_exactly_minus_100_is_zero(self, db_session):
        user = await _make_user(db_session, 5000008)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        g1, g1_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "-60"]
        )
        g2, g2_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "-40"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id,
                coefficient_option_ids=[g1_opts[1].id, g2_opts[1].id],
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("0.00")

    async def test_negative_groups_below_minus_100_rejected(self, db_session):
        user = await _make_user(db_session, 5000009)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        g1, g1_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "-70"]
        )
        g2, g2_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "-40"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id,
                coefficient_option_ids=[g1_opts[1].id, g2_opts[1].id],
            )],
        )
        with pytest.raises(EstimateValidationError):
            await _generate(db_session, project.id, user.id)

    async def test_large_positive_adjustment(self, db_session):
        user = await _make_user(db_session, 5000010)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "300"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("160.00")

    async def test_rounding_boundary_half_up(self, db_session):
        """12.345 * 1.155 = 14.258475 -> rounds to 14.26 (ROUND_HALF_UP)."""
        user = await _make_user(db_session, 5000011)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="12.35")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "15.5"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        # 12.35 * 1.155 = 14.26425 -> 14.26
        assert estimate.lines[0].unit_price == Decimal("14.26")

    async def test_no_float_leakage(self, db_session):
        user = await _make_user(db_session, 5000012)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        assert isinstance(line.unit_price, Decimal)
        assert isinstance(line.base_unit_price, Decimal)
        assert isinstance(line.coefficient_snapshot[0]["percentage"], str)

    async def test_coefficient_less_line_unchanged(self, db_session):
        user = await _make_user(db_session, 5000013)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(price_item_id=item.id)],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        assert line.base_unit_price == Decimal("40.00")
        assert line.unit_price == Decimal("40.00")
        assert line.coefficient_snapshot == []


# ---------------------------------------------------------------------------
# TestB — snapshot content & immutability from live catalog
# ---------------------------------------------------------------------------

class TestB_SnapshotImmutability:
    async def test_snapshot_captures_group_option_facts(self, db_session):
        user = await _make_user(db_session, 5000020)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        group, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        entry = estimate.lines[0].coefficient_snapshot[0]
        assert entry["group_id"] == str(group.id)
        assert entry["group_code"] == group.code
        assert entry["option_id"] == str(options[1].id)
        assert entry["option_code"] == options[1].code
        assert entry["percentage"] == "10.000"
        assert entry["is_base"] is False

    async def test_snapshot_deterministic_order(self, db_session):
        user = await _make_user(db_session, 5000021)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        service = PriceCoefficientService(db_session)
        g1, g1_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        g2, g2_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "20"]
        )
        await service.update_group(user.id, g1.id, position=0)
        await service.update_group(user.id, g2.id, position=1)
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id,
                coefficient_option_ids=[g2_opts[1].id, g1_opts[1].id],
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        snapshot = estimate.lines[0].coefficient_snapshot
        assert [e["option_id"] for e in snapshot] == [
            str(g1_opts[1].id), str(g2_opts[1].id)
        ]

    async def test_snapshot_survives_catalog_rename(self, db_session):
        user = await _make_user(db_session, 5000022)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        original_entry = dict(estimate.lines[0].coefficient_snapshot[0])

        service = PriceCoefficientService(db_session)
        await service.update_option(user.id, options[1].id, display_name="Renamed")

        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].coefficient_snapshot[0] == original_entry

    async def test_snapshot_survives_catalog_percentage_change(self, db_session):
        user = await _make_user(db_session, 5000023)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        original_price = estimate.lines[0].unit_price

        service = PriceCoefficientService(db_session)
        await service.update_option(user.id, options[1].id, percentage=Decimal("90"))

        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].unit_price == original_price == Decimal("44.00")

    async def test_snapshot_survives_catalog_archive(self, db_session):
        user = await _make_user(db_session, 5000024)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        original_price = estimate.lines[0].unit_price

        await PriceCoefficientService(db_session).archive_option(user.id, options[1].id)

        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].unit_price == original_price == Decimal("44.00")


# ---------------------------------------------------------------------------
# TestC — LABOR-only defense in depth
# ---------------------------------------------------------------------------

class TestC_LaborDefenseInDepth:
    async def test_material_scope_change_after_assignment_blocks_generation(
        self, db_session
    ):
        """12D prevents assigning to non-LABOR at write time, but price_scope
        is mutable afterward -- 12E must not silently price the corrupt state."""
        user = await _make_user(db_session, 5000030)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        item.price_scope = PriceScope.MATERIAL
        await db_session.commit()

        with pytest.raises(EstimateValidationError):
            await _generate(db_session, project.id, user.id)


# ---------------------------------------------------------------------------
# TestD — Surface / Reveal parity
# ---------------------------------------------------------------------------

class TestD_SurfaceRevealParity:
    async def test_reveal_coefficient_pricing(self, db_session):
        user = await _make_user(db_session, 5000040)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL,
            unit=PriceUnit.LM, price="40.00",
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        reveal_service = OpeningRevealWorkService(db_session)
        await reveal_service.set_works(
            opening.id, user.id, [item.id],
            coefficient_option_ids=[[options[1].id]],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        assert line.base_unit_price == Decimal("40.00")
        assert line.unit_price == Decimal("44.00")
        assert len(line.coefficient_snapshot) == 1

    async def test_reveal_quantity_unaffected_by_coefficients(self, db_session):
        user = await _make_user(db_session, 5000041)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item_a = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL,
            unit=PriceUnit.LM, price="40.00",
        )
        item_b = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL,
            unit=PriceUnit.LM, price="40.00",
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "50"]
        )
        reveal_service = OpeningRevealWorkService(db_session)
        await reveal_service.set_works(
            opening.id, user.id, [item_a.id, item_b.id],
            coefficient_option_ids=[[options[1].id], []],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].quantity == estimate.lines[1].quantity
        assert estimate.lines[0].unit_price == Decimal("60.00")
        assert estimate.lines[1].unit_price == Decimal("40.00")

    async def test_duplicate_price_item_occurrences_independent_pricing(
        self, db_session
    ):
        user = await _make_user(db_session, 5000042)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "25"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [
                OrderedPriceItemSelection(
                    price_item_id=item.id, coefficient_option_ids=[options[1].id]
                ),
                OrderedPriceItemSelection(price_item_id=item.id),
            ],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("50.00")
        assert estimate.lines[1].unit_price == Decimal("40.00")
        assert estimate.lines[0].planned_work_id != estimate.lines[1].planned_work_id


# ---------------------------------------------------------------------------
# TestE — preview / change detection
# ---------------------------------------------------------------------------

class TestE_Preview:
    async def _setup_draft(self, db_session, telegram_id: int):
        user = await _make_user(db_session, telegram_id)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        group, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        return user, project, room, surface, item, group, options, estimate

    async def test_preview_detects_base_price_change(self, db_session):
        user, project, room, surface, item, group, options, estimate = (
            await self._setup_draft(db_session, 5000050)
        )
        item.price = Decimal("50.00")
        await db_session.commit()
        result = await EstimateService(db_session).preview_regeneration(
            project.id, estimate.id, user.id
        )
        assert result.updated == 1
        change = result.changes[0]
        assert change.old_base_unit_price == Decimal("40.00")
        assert change.new_base_unit_price == Decimal("50.00")
        # Existing estimate is untouched.
        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].base_unit_price == Decimal("40.00")

    async def test_preview_detects_percentage_change(self, db_session):
        user, project, room, surface, item, group, options, estimate = (
            await self._setup_draft(db_session, 5000051)
        )
        await PriceCoefficientService(db_session).update_option(
            user.id, options[1].id, percentage=Decimal("30")
        )
        result = await EstimateService(db_session).preview_regeneration(
            project.id, estimate.id, user.id
        )
        assert result.updated == 1
        assert Decimal(
            result.changes[0].new_coefficient_snapshot[0]["percentage"]
        ) == Decimal("30")
        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].unit_price == Decimal("44.00")

    async def test_preview_detects_selection_change(self, db_session):
        """Changing a selection requires a full WorkPlan replace, which (per
        Stage 12D Option C) recreates the occurrence row with a new id. An
        ordinary save keeps the occurrence_key (13E.2B), so regeneration pairs
        the line with the re-created occurrence by key: one UPDATED entry --
        never ADDED + REMOVED, which would drop manual overrides."""
        user, project, room, surface, item, group, options, estimate = (
            await self._setup_draft(db_session, 5000052)
        )
        _, more_options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "50"]
        )
        from app.domain.services.work_plan_service import SurfaceWorkPlanService

        (key,) = await _current_keys(db_session, surface.id)
        await SurfaceWorkPlanService(db_session).replace_planned_works(
            project.id, room.id, surface.id, user.id,
            planned_works=[OrderedPriceItemSelection(
                price_item_id=item.id, occurrence_key=key,
                coefficient_option_ids=[options[1].id, more_options[1].id],
            )],
        )
        result = await EstimateService(db_session).preview_regeneration(
            project.id, estimate.id, user.id
        )
        assert (result.added, result.removed, result.updated) == (0, 0, 1)
        updated = next(c for c in result.changes if c.change_type == "UPDATED")
        assert len(updated.new_coefficient_snapshot) == 2

    async def test_preview_detects_coefficient_removed(self, db_session):
        """Removing the coefficient is also a full replace; the line is
        paired by occurrence_key and surfaces as one UPDATED entry."""
        user, project, room, surface, item, group, options, estimate = (
            await self._setup_draft(db_session, 5000053)
        )
        from app.domain.services.work_plan_service import SurfaceWorkPlanService

        (key,) = await _current_keys(db_session, surface.id)
        await SurfaceWorkPlanService(db_session).replace_planned_works(
            project.id, room.id, surface.id, user.id,
            planned_works=[OrderedPriceItemSelection(price_item_id=item.id, occurrence_key=key)],
        )
        result = await EstimateService(db_session).preview_regeneration(
            project.id, estimate.id, user.id
        )
        assert (result.added, result.removed, result.updated) == (0, 0, 1)
        updated = next(c for c in result.changes if c.change_type == "UPDATED")
        assert updated.new_coefficient_snapshot == []

    async def test_preview_detects_coefficient_added(self, db_session):
        user = await _make_user(db_session, 5000054)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(price_item_id=item.id)],
        )
        estimate = await _generate(db_session, project.id, user.id)
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        from app.domain.services.work_plan_service import SurfaceWorkPlanService

        (key,) = await _current_keys(db_session, surface.id)
        await SurfaceWorkPlanService(db_session).replace_planned_works(
            project.id, room.id, surface.id, user.id,
            planned_works=[OrderedPriceItemSelection(
                price_item_id=item.id, occurrence_key=key, coefficient_option_ids=[options[1].id]
            )],
        )
        result = await EstimateService(db_session).preview_regeneration(
            project.id, estimate.id, user.id
        )
        assert (result.added, result.removed, result.updated) == (0, 0, 1)
        updated = next(c for c in result.changes if c.change_type == "UPDATED")
        assert len(updated.new_coefficient_snapshot) == 1

    async def test_preview_invalid_aggregate_rejected_safely(self, db_session):
        user, project, room, surface, item, group, options, estimate = (
            await self._setup_draft(db_session, 5000055)
        )
        _, more_options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "-95"]
        )
        await PriceCoefficientService(db_session).update_option(
            user.id, options[1].id, percentage=Decimal("-90")
        )
        from app.domain.services.work_plan_service import SurfaceWorkPlanService

        await SurfaceWorkPlanService(db_session).replace_planned_works(
            project.id, room.id, surface.id, user.id,
            planned_works=[OrderedPriceItemSelection(
                price_item_id=item.id,
                coefficient_option_ids=[options[1].id, more_options[1].id],
            )],
        )
        with pytest.raises(EstimateValidationError):
            await EstimateService(db_session).preview_regeneration(
                project.id, estimate.id, user.id
            )
        # Existing estimate is untouched.
        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].unit_price == Decimal("44.00")

    async def test_preview_does_not_mutate_estimate(self, db_session):
        user, project, room, surface, item, group, options, estimate = (
            await self._setup_draft(db_session, 5000056)
        )
        item.price = Decimal("99.00")
        await db_session.commit()
        await EstimateService(db_session).preview_regeneration(
            project.id, estimate.id, user.id
        )
        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].base_unit_price == Decimal("40.00")
        assert refetched.total == estimate.total


# ---------------------------------------------------------------------------
# TestF — regeneration
# ---------------------------------------------------------------------------

class TestF_Regeneration:
    async def test_regenerate_captures_current_configuration(self, db_session):
        user = await _make_user(db_session, 5000060)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(price_item_id=item.id)],
        )
        estimate = await _generate(db_session, project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("40.00")

        from app.domain.services.work_plan_service import SurfaceWorkPlanService

        (key,) = await _current_keys(db_session, surface.id)
        await SurfaceWorkPlanService(db_session).replace_planned_works(
            project.id, room.id, surface.id, user.id,
            planned_works=[OrderedPriceItemSelection(
                price_item_id=item.id, occurrence_key=key, coefficient_option_ids=[options[1].id]
            )],
        )
        service = EstimateService(db_session)
        result = await service.regenerate_draft(estimate.id, user.id, project.id)
        # The WorkPlan replace recreated the occurrence with a new id
        # (Stage 12D Option C) but kept its occurrence_key; regeneration pairs
        # it by key, so the existing line is UPDATED in place.
        assert (result.added, result.removed, result.updated) == (0, 0, 1)
        refetched = await service.get_estimate_detail(project.id, estimate.id, user.id)
        assert len(refetched.lines) == 1
        assert refetched.lines[0].base_unit_price == Decimal("40.00")
        assert refetched.lines[0].unit_price == Decimal("44.00")
        assert len(refetched.lines[0].coefficient_snapshot) == 1

    async def test_no_silent_mutation_before_regenerate(self, db_session):
        user = await _make_user(db_session, 5000061)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(price_item_id=item.id)],
        )
        estimate = await _generate(db_session, project.id, user.id)
        item.price = Decimal("999.00")
        await db_session.commit()
        # Merely fetching does not mutate.
        refetched = await EstimateService(db_session).get_estimate_detail(
            project.id, estimate.id, user.id
        )
        assert refetched.lines[0].unit_price == Decimal("40.00")


# ---------------------------------------------------------------------------
# TestG — manual price override
# ---------------------------------------------------------------------------

class TestG_Override:
    async def test_override_preserves_base_and_coefficient_snapshot(self, db_session):
        user = await _make_user(db_session, 5000070)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        g1, g1_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        g2, g2_opts = await _make_group_with_options(
            db_session, user.id, percentages=["0", "20"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id,
                coefficient_option_ids=[g1_opts[1].id, g2_opts[1].id],
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        assert line.unit_price == Decimal("52.00")

        service = EstimateService(db_session)
        updated = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"}, unit_price=Decimal("47.00"),
        )
        assert updated.unit_price == Decimal("47.00")
        assert updated.price_override is True
        assert updated.base_unit_price == Decimal("40.00")
        assert len(updated.coefficient_snapshot) == 2

    async def test_override_survives_live_coefficient_change(self, db_session):
        user = await _make_user(db_session, 5000071)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        service = EstimateService(db_session)
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"}, unit_price=Decimal("47.00"),
        )
        await PriceCoefficientService(db_session).update_option(
            user.id, options[1].id, percentage=Decimal("90")
        )
        refetched = await service.get_estimate_detail(project.id, estimate.id, user.id)
        assert refetched.lines[0].unit_price == Decimal("47.00")
        assert refetched.lines[0].price_override is True


# ---------------------------------------------------------------------------
# TestH — reset price override
# ---------------------------------------------------------------------------

class TestH_Reset:
    async def _setup_overridden(self, db_session, telegram_id: int):
        user = await _make_user(db_session, telegram_id)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        group, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        service = EstimateService(db_session)
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"}, unit_price=Decimal("47.00"),
        )
        return user, project, room, surface, item, group, options, estimate, line, service

    async def test_reset_unchanged_configuration(self, db_session):
        (user, project, room, surface, item, group, options, estimate, line,
         service) = await self._setup_overridden(db_session, 5000080)
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.price_override is False
        assert reset.unit_price == Decimal("44.00")
        assert reset.base_unit_price == Decimal("40.00")

    async def test_reset_uses_current_price_item_price(self, db_session):
        (user, project, room, surface, item, group, options, estimate, line,
         service) = await self._setup_overridden(db_session, 5000081)
        item.price = Decimal("100.00")
        await db_session.commit()
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.base_unit_price == Decimal("100.00")
        assert reset.unit_price == Decimal("110.00")

    async def test_reset_uses_current_percentage_value(self, db_session):
        (user, project, room, surface, item, group, options, estimate, line,
         service) = await self._setup_overridden(db_session, 5000083)
        await PriceCoefficientService(db_session).update_option(
            user.id, options[1].id, percentage=Decimal("20")
        )
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.unit_price == Decimal("48.00")

    async def test_reset_with_null_current_base(self, db_session):
        (user, project, room, surface, item, group, options, estimate, line,
         service) = await self._setup_overridden(db_session, 5000084)
        item.price = None
        await db_session.commit()
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.base_unit_price is None
        assert reset.unit_price is None
        assert reset.price_override is False
        assert len(reset.coefficient_snapshot) == 1

    async def test_reset_with_zero_current_base(self, db_session):
        (user, project, room, surface, item, group, options, estimate, line,
         service) = await self._setup_overridden(db_session, 5000085)
        item.price = Decimal("0.00")
        await db_session.commit()
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.base_unit_price == Decimal("0.00")
        assert reset.unit_price == Decimal("0.00")

    async def test_reset_surface_provenance(self, db_session):
        (user, project, room, surface, item, group, options, estimate, line,
         service) = await self._setup_overridden(db_session, 5000086)
        assert line.opening_id is None
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.unit_price == Decimal("44.00")

    async def test_reset_reveal_provenance(self, db_session):
        user = await _make_user(db_session, 5000087)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL,
            unit=PriceUnit.LM, price="40.00",
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        reveal_service = OpeningRevealWorkService(db_session)
        await reveal_service.set_works(
            opening.id, user.id, [item.id],
            coefficient_option_ids=[[options[1].id]],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        service = EstimateService(db_session)
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"}, unit_price=Decimal("1.00"),
        )
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.unit_price == Decimal("44.00")
        assert reset.price_override is False

    async def test_reset_base_option_zero_percent(self, db_session):
        """The occurrence's assigned option stays the 0% base throughout --
        reset must keep it (never optimize it away) and preserve is_base."""
        user = await _make_user(db_session, 5000088)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        _, base_options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[base_options[0].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        line = estimate.lines[0]
        service = EstimateService(db_session)
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"}, unit_price=Decimal("999.00"),
        )
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.unit_price == Decimal("40.00")
        assert reset.coefficient_snapshot[0]["is_base"] is True

    async def test_reset_when_occurrence_recreated_falls_back_honestly(
        self, db_session
    ):
        """WorkPlan edited since generation: the OLD planned_work_id is gone
        (Stage 10/12D occurrence ids are not durable). Reset must not crash
        or fabricate a coefficient snapshot it cannot determine."""
        (user, project, room, surface, item, group, options, estimate, line,
         service) = await self._setup_overridden(db_session, 5000089)
        from app.domain.services.work_plan_service import SurfaceWorkPlanService

        other_item = await _make_price_item(db_session, user.id, price="55.00")
        await SurfaceWorkPlanService(db_session).set_plan(
            project.id, room.id, surface.id, user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[OrderedPriceItemSelection(price_item_id=other_item.id)],
        )
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.price_override is False
        assert reset.base_unit_price == Decimal("40.00")
        assert reset.unit_price == Decimal("40.00")
        assert reset.coefficient_snapshot is None


# ---------------------------------------------------------------------------
# TestI — MANUAL / PRICE_BOOK lines unaffected
# ---------------------------------------------------------------------------

class TestI_ManualPriceBookUnaffected:
    async def test_manual_line_no_coefficient_fields(self, db_session):
        user = await _make_user(db_session, 5000090)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(price_item_id=item.id)],
        )
        estimate = await _generate(db_session, project.id, user.id)
        service = EstimateService(db_session)
        manual = await service.add_manual_line(
            estimate.id, user.id,
            description="Dodatkowa robota",
            scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT,
            quantity=Decimal("1.000"),
            unit_price=Decimal("100.00"),
            project_id=project.id,
        )
        assert manual.base_unit_price is None
        assert manual.coefficient_snapshot is None

    async def test_manual_line_reset_rejected(self, db_session):
        user = await _make_user(db_session, 5000091)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(price_item_id=item.id)],
        )
        estimate = await _generate(db_session, project.id, user.id)
        service = EstimateService(db_session)
        manual = await service.add_manual_line(
            estimate.id, user.id,
            description="Dodatkowa robota",
            scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT,
            quantity=Decimal("1.000"),
            unit_price=Decimal("100.00"),
            project_id=project.id,
        )
        with pytest.raises(EstimateValidationError):
            await service.patch_line(
                project.id, estimate.id, user.id, manual.id,
                provided_fields=set(), reset_price_override=True,
            )


# ---------------------------------------------------------------------------
# TestJ — FINAL/ACCEPTED immutability and finalization regression
# ---------------------------------------------------------------------------

class TestJ_FinalizationRegression:
    async def test_finalize_blocked_by_null_unit_price_with_coefficients(
        self, db_session
    ):
        user = await _make_user(db_session, 5000100)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price=None)
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        service = EstimateService(db_session)
        with pytest.raises(EstimateValidationError):
            await service.finalize(estimate.id, user.id, project.id)

    async def test_finalize_zero_unit_price_not_blocked(self, db_session):
        user = await _make_user(db_session, 5000101)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="0.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "20"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        service = EstimateService(db_session)
        finalized = await service.finalize(estimate.id, user.id, project.id)
        assert finalized.status.value == "FINAL"

    async def test_final_estimate_never_mutated_by_live_catalog_change(
        self, db_session
    ):
        user = await _make_user(db_session, 5000102)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user.id, price="40.00")
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await _make_work_plan_with_coefficients(
            db_session, project.id, room.id, surface.id, user.id,
            [OrderedPriceItemSelection(
                price_item_id=item.id, coefficient_option_ids=[options[1].id]
            )],
        )
        estimate = await _generate(db_session, project.id, user.id)
        service = EstimateService(db_session)
        await service.finalize(estimate.id, user.id, project.id)

        await PriceCoefficientService(db_session).update_option(
            user.id, options[1].id, percentage=Decimal("400")
        )
        item.price = Decimal("1.00")
        await db_session.commit()

        refetched = await service.get_estimate_detail(project.id, estimate.id, user.id)
        assert refetched.lines[0].unit_price == Decimal("44.00")
        assert refetched.lines[0].base_unit_price == Decimal("40.00")
