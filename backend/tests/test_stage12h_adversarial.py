"""Stage 12H: adversarial verification of the full Stage 12 coefficient chain.

Targets gaps not already covered by the 12C-12G suites: occurrence identity
under full replace (reorder / remove / add / repeated saves / legacy payload),
apply-to-all with duplicate occurrences, Reveal parity, the exact Decimal
matrix from the Stage 12H brief, snapshot immutability against description /
base-status / Price Book edits, reset with an empty current coefficient set,
FINAL immutability for coefficient-bearing lines, archived-assignment repair,
cross-owner restore, and Stage 11 coefficient-agnosticism.
"""
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import (
    EstimateStateError,
    EstimateValidationError,
    OpeningRevealWorkValidationError,
    PriceCoefficientValidationError,
    SurfaceWorkPlanValidationError,
)
from app.domain.services.estimate_service import (
    EstimateService,
    _calculate_effective_unit_price,
)
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from app.models.opening_reveal_planned_work import (
    OpeningRevealPlannedWork,
    OpeningRevealPlannedWorkCoefficientAssignment,
)
from app.models.price_coefficient import CoefficientOption
from app.models.price_item import PriceCategory, PriceScope, PriceUnit
from app.models.surface import Surface
from app.models.work_plan import (
    SurfacePlannedWork,
    SurfacePlannedWorkCoefficientAssignment,
)
from app.schemas.work_plan import OrderedPriceItemSelection
from tests.test_estimates import (
    _make_opening,
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
    _make_user,
)
from tests.test_planned_work_coefficient_assignments import (
    OTHER_USER,
    VALID_USER,
    _make_group_with_options,
    _wp,
    auth_header,
    get_token,
)

Sel = OrderedPriceItemSelection


async def _set_plan(db, project, room, surface, owner, selections, substrate=Substrate.GYPSUM_PLASTER):
    return await SurfaceWorkPlanService(db).set_plan(
        project.id, room.id, surface.id, owner.id,
        substrate=substrate, planned_works=selections,
    )


async def _plan_selection(db, surface_id) -> list[tuple[uuid.UUID, list[uuid.UUID]]]:
    """[(price_item_id, sorted option ids)] in position order, read fresh."""
    from app.models.work_plan import SurfaceWorkPlan

    plan_id = (
        await db.execute(select(SurfaceWorkPlan.id).where(SurfaceWorkPlan.surface_id == surface_id))
    ).scalar_one()
    works = (
        await db.execute(
            select(SurfacePlannedWork)
            .where(SurfacePlannedWork.work_plan_id == plan_id)
            .order_by(SurfacePlannedWork.position)
        )
    ).scalars().all()
    out = []
    for work in works:
        option_ids = (
            await db.execute(
                select(SurfacePlannedWorkCoefficientAssignment.coefficient_option_id).where(
                    SurfacePlannedWorkCoefficientAssignment.surface_planned_work_id == work.id
                )
            )
        ).scalars().all()
        out.append((work.price_item_id, sorted(option_ids)))
    return out


async def _assignment_rows_for(db, option_ids) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(SurfacePlannedWorkCoefficientAssignment).where(
                SurfacePlannedWorkCoefficientAssignment.coefficient_option_id.in_(option_ids)
            )
        )
    ).scalar_one()


async def _reveal_selection(db, opening_id) -> list[tuple[uuid.UUID, list[uuid.UUID]]]:
    works = (
        await db.execute(
            select(OpeningRevealPlannedWork)
            .where(OpeningRevealPlannedWork.opening_id == opening_id)
            .order_by(OpeningRevealPlannedWork.position)
        )
    ).scalars().all()
    out = []
    for work in works:
        option_ids = (
            await db.execute(
                select(OpeningRevealPlannedWorkCoefficientAssignment.coefficient_option_id).where(
                    OpeningRevealPlannedWorkCoefficientAssignment.opening_reveal_planned_work_id
                    == work.id
                )
            )
        ).scalars().all()
        out.append((work.price_item_id, sorted(option_ids)))
    return out


async def _base_scenario(db, telegram_id, *, price="40.00"):
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    item = await _make_price_item(db, user.id, price=price)
    return user, project, room, surface, item


# ---------------------------------------------------------------------------
# 3. Occurrence identity under full replace (Surface)
# ---------------------------------------------------------------------------


class TestSurfaceOccurrenceIdentity:
    async def test_reordering_duplicates_moves_each_selection_with_its_occurrence(self, db_session):
        user, project, room, surface, item = await _base_scenario(db_session, 1200001)
        _, g1 = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        _, g2 = await _make_group_with_options(db_session, user.id, percentages=["0", "20"])
        a, b = [g1[1].id], [g2[1].id]
        await _set_plan(db_session, project, room, surface, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=a),
            Sel(price_item_id=item.id, coefficient_option_ids=b),
            Sel(price_item_id=item.id),
        ])
        await _set_plan(db_session, project, room, surface, user, [
            Sel(price_item_id=item.id),
            Sel(price_item_id=item.id, coefficient_option_ids=b),
            Sel(price_item_id=item.id, coefficient_option_ids=a),
        ])
        assert await _plan_selection(db_session, surface.id) == [
            (item.id, []), (item.id, sorted(b)), (item.id, sorted(a)),
        ]
        # No orphan rows: exactly one assignment per selected option remains.
        assert await _assignment_rows_for(db_session, a + b) == 2

    async def test_remove_middle_and_add_occurrence(self, db_session):
        user, project, room, surface, item = await _base_scenario(db_session, 1200002)
        other = await _make_price_item(db_session, user.id, price="10.00")
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10", "20"])
        await _set_plan(db_session, project, room, surface, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id]),
            Sel(price_item_id=item.id, coefficient_option_ids=[g[2].id]),
            Sel(price_item_id=item.id, coefficient_option_ids=[g[0].id]),
        ])
        await _set_plan(db_session, project, room, surface, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id]),
            Sel(price_item_id=item.id, coefficient_option_ids=[g[0].id]),
            Sel(price_item_id=other.id),
        ])
        assert await _plan_selection(db_session, surface.id) == [
            (item.id, [g[1].id]), (item.id, [g[0].id]), (other.id, []),
        ]
        assert await _assignment_rows_for(db_session, [o.id for o in g]) == 2

    async def test_repeated_identical_saves_are_stable(self, db_session):
        user, project, room, surface, item = await _base_scenario(db_session, 1200003)
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        selection = [
            Sel(price_item_id=item.id, coefficient_option_ids=[g[0].id]),
            Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id]),
        ]
        for _ in range(4):
            await _set_plan(db_session, project, room, surface, user, selection)
        assert await _plan_selection(db_session, surface.id) == [
            (item.id, [g[0].id]), (item.id, [g[1].id]),
        ]
        assert await _assignment_rows_for(db_session, [o.id for o in g]) == 2

    async def test_substrate_change_with_planned_works_keeps_coefficients(self, db_session):
        user, project, room, surface, item = await _base_scenario(db_session, 1200004)
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        sel = [Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id])]
        await _set_plan(db_session, project, room, surface, user, sel)
        await _set_plan(db_session, project, room, surface, user, sel, substrate=Substrate.CONCRETE)
        assert await _plan_selection(db_session, surface.id) == [(item.id, [g[1].id])]

    async def test_legacy_price_item_ids_save_clears_previous_coefficients(
        self, async_client: AsyncClient, db_session
    ):
        """The frontend sends the legacy payload once no occurrence has a
        coefficient left; that must clear every prior assignment (no ghost
        selection survives a full replace)."""
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        user_id = (
            await async_client.get("/api/me", headers=headers)
        ).json()["id"]
        user_uuid = uuid.UUID(user_id)
        project = await _make_project(db_session, user_uuid)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, user_uuid, price="40.00")
        _, g = await _make_group_with_options(db_session, user_uuid, percentages=["0", "10"])
        url = _wp(project.id, room.id, surface.id)

        first = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "quality_target": None,
            "planned_works": [
                {"price_item_id": str(item.id), "coefficient_option_ids": [str(g[1].id)]},
                {"price_item_id": str(item.id), "coefficient_option_ids": [str(g[0].id)]},
            ],
        })
        assert first.status_code == 200, first.text
        legacy = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "quality_target": None,
            "price_item_ids": [str(item.id), str(item.id)],
        })
        assert legacy.status_code == 200, legacy.text
        assert [w["coefficient_options"] for w in legacy.json()["planned_works"]] == [[], []]
        assert await _assignment_rows_for(db_session, [o.id for o in g]) == 0


# ---------------------------------------------------------------------------
# 2 / 5. Reveal parity
# ---------------------------------------------------------------------------


class TestRevealParity:
    async def _reveal_scenario(self, db, telegram_id):
        user = await _make_user(db, telegram_id)
        project = await _make_project(db, user.id)
        room = await _make_room(db, project.id)
        surface = await _make_surface(db, room.id)
        opening = await _make_opening(db, surface.id)
        return user, project, room, surface, opening

    async def test_labor_and_material_reveal_item_rejected_but_plannable_without_coefficients(
        self, db_session
    ):
        user, project, room, surface, opening = await self._reveal_scenario(db_session, 1200101)
        mixed = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM,
            price_scope=PriceScope.LABOR_AND_MATERIAL, price="15.00",
        )
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        service = OpeningRevealWorkService(db_session)
        with pytest.raises((PriceCoefficientValidationError, OpeningRevealWorkValidationError)):
            await service.set_works(
                opening.id, user.id, [mixed.id], coefficient_option_ids=[[g[1].id]],
            )
        works = await service.set_works(opening.id, user.id, [mixed.id])
        assert len(works) == 1
        assert await _reveal_selection(db_session, opening.id) == [(mixed.id, [])]

    async def test_reorder_duplicates_and_openings_stay_independent(self, db_session):
        user, project, room, surface, opening = await self._reveal_scenario(db_session, 1200102)
        second = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM, price="15.00",
        )
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10", "20"])
        service = OpeningRevealWorkService(db_session)
        await service.set_works(
            opening.id, user.id, [item.id, item.id],
            coefficient_option_ids=[[g[1].id], [g[2].id]],
        )
        await service.set_works(second.id, user.id, [item.id], coefficient_option_ids=[[g[0].id]])
        # Reorder the first opening; the second must not move.
        await service.set_works(
            opening.id, user.id, [item.id, item.id],
            coefficient_option_ids=[[g[2].id], [g[1].id]],
        )
        assert await _reveal_selection(db_session, opening.id) == [
            (item.id, [g[2].id]), (item.id, [g[1].id]),
        ]
        assert await _reveal_selection(db_session, second.id) == [(item.id, [g[0].id])]
        # Legacy full replace without coefficients clears only this opening.
        await service.set_works(opening.id, user.id, [item.id])
        assert await _reveal_selection(db_session, opening.id) == [(item.id, [])]
        assert await _reveal_selection(db_session, second.id) == [(item.id, [g[0].id])]

    async def test_lm_and_m2_reveal_quantities_unchanged_by_coefficients(self, db_session):
        user, project, room, surface, opening = await self._reveal_scenario(db_session, 1200103)
        lm = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM, price="10.00",
        )
        m2 = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.M2, price="20.00",
        )
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "25"])
        service = OpeningRevealWorkService(db_session)
        await service.set_works(opening.id, user.id, [lm.id, m2.id])
        plain = await EstimateService(db_session).generate_estimate(project.id, user.id)
        plain_qty = {line.price_item_id: line.quantity for line in plain.lines}
        await EstimateService(db_session).finalize(plain.id, user.id, project.id)

        await service.set_works(
            opening.id, user.id, [lm.id, m2.id], coefficient_option_ids=[[g[1].id], [g[1].id]],
        )
        est = await EstimateService(db_session).generate_estimate(project.id, user.id)
        by_item = {line.price_item_id: line for line in est.lines}
        assert by_item[lm.id].quantity == plain_qty[lm.id]
        assert by_item[m2.id].quantity == plain_qty[m2.id]
        assert by_item[lm.id].unit_price == Decimal("12.50")
        assert by_item[m2.id].unit_price == Decimal("25.00")


# ---------------------------------------------------------------------------
# 4. Apply-to-all walls
# ---------------------------------------------------------------------------


class TestApplyToAllWalls:
    async def test_duplicates_base_and_multi_group_copied_per_occurrence(self, db_session):
        user, project, room, source, item = await _base_scenario(db_session, 1200201)
        other_item = await _make_price_item(db_session, user.id, price="5.00")
        t1 = await _make_surface(db_session, room.id, width="3.000", height="2.500")
        t2 = await _make_surface(db_session, room.id, width="4.000", height="2.600")
        _, g1 = await _make_group_with_options(db_session, user.id, percentages=["0", "15"])
        _, g2 = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        selection = [
            Sel(price_item_id=item.id, coefficient_option_ids=[g1[0].id, g2[1].id]),
            Sel(price_item_id=item.id, coefficient_option_ids=[g1[1].id]),
            Sel(price_item_id=other_item.id),
        ]
        await _set_plan(db_session, project, room, source, user, selection)
        await SurfaceWorkPlanService(db_session).apply_to_room_walls(
            project.id, room.id, source.id, user.id,
        )
        expected = await _plan_selection(db_session, source.id)
        for target, width, height in ((t1, "3.000", "2.500"), (t2, "4.000", "2.600")):
            assert await _plan_selection(db_session, target.id) == expected
            fresh = (
                await db_session.execute(select(Surface).where(Surface.id == target.id))
            ).scalar_one()
            assert fresh.width == Decimal(width) and fresh.height == Decimal(height)

    async def test_archived_source_option_rejects_whole_batch(self, db_session):
        user, project, room, source, item = await _base_scenario(db_session, 1200202)
        t1 = await _make_surface(db_session, room.id)
        t2 = await _make_surface(db_session, room.id)
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        await _set_plan(db_session, project, room, t1, user, [Sel(price_item_id=item.id)])
        await _set_plan(db_session, project, room, source, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id]),
        ])
        await PriceCoefficientService(db_session).archive_option(user.id, g[1].id)
        ids = SimpleNamespace(
            project=project.id, room=room.id, source=source.id, user=user.id,
            item=item.id, t1=t1.id, t2=t2.id,
        )
        with pytest.raises((PriceCoefficientValidationError, SurfaceWorkPlanValidationError)):
            await SurfaceWorkPlanService(db_session).apply_to_room_walls(
                ids.project, ids.room, ids.source, ids.user,
            )
        await db_session.rollback()
        assert await _plan_selection(db_session, ids.t1) == [(ids.item, [])]
        from app.models.work_plan import SurfaceWorkPlan

        t2_plan = (
            await db_session.execute(
                select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == ids.t2)
            )
        ).scalar_one_or_none()
        assert t2_plan is None


# ---------------------------------------------------------------------------
# 6. Decimal matrix (calculator)
# ---------------------------------------------------------------------------


def _opts(*percentages: str):
    return [SimpleNamespace(percentage=Decimal(p)) for p in percentages]


class TestDecimalMatrix:
    @pytest.mark.parametrize(
        ("percentages", "expected"),
        [
            ((), "100.00"),
            (("0",), "100.00"),
            (("10",), "110.00"),
            (("15", "20"), "135.00"),
            (("15", "20", "10"), "145.00"),
            (("25", "20", "20"), "165.00"),
            (("10", "-10"), "100.00"),
            (("-10",), "90.00"),
            (("-100",), "0.00"),
            (("-60", "-40"), "0.00"),
        ],
    )
    def test_base_100_additive_matrix(self, percentages, expected):
        result = _calculate_effective_unit_price(Decimal("100.00"), _opts(*percentages))
        assert result == Decimal(expected)
        assert isinstance(result, Decimal)

    def test_below_minus_100_rejected(self):
        with pytest.raises(EstimateValidationError):
            _calculate_effective_unit_price(Decimal("100.00"), _opts("-60", "-40.001"))

    def test_additive_not_compounded(self):
        # Compounding would give 100 * 1.25 * 1.2 * 1.2 = 180.00.
        assert _calculate_effective_unit_price(
            Decimal("100.00"), _opts("25", "20", "20")
        ) != Decimal("180.00")

    def test_fractional_percentage_rounds_half_up_once(self):
        # 100 * 1.12345 = 112.345 -> 112.35 (HALF_UP, single rounding point)
        assert _calculate_effective_unit_price(Decimal("100.00"), _opts("12.345")) == Decimal("112.35")
        # 33.33 * 1.12345 = 37.4445885 -> 37.44
        assert _calculate_effective_unit_price(Decimal("33.33"), _opts("12.345")) == Decimal("37.44")
        # Per-option rounding would give 10.01 * 1.005 -> 10.06 (10.06005); exact is the same
        # here, so probe a case where early rounding differs: 0.05 * (1 + 0.5% + 0.5%).
        assert _calculate_effective_unit_price(Decimal("0.05"), _opts("0.5", "0.5")) == Decimal("0.05")

    def test_zero_and_null_base(self):
        assert _calculate_effective_unit_price(Decimal("0.00"), _opts("20", "15")) == Decimal("0.00")
        assert _calculate_effective_unit_price(None, _opts("20")) is None


# ---------------------------------------------------------------------------
# 7 / 9 / 11. Snapshot, reset, FINAL immutability
# ---------------------------------------------------------------------------


async def _estimate_with_coefficient(db, telegram_id):
    user, project, room, surface, item = await _base_scenario(db, telegram_id)
    group, g = await _make_group_with_options(db, user.id, percentages=["0", "10"])
    await _set_plan(db, project, room, surface, user, [
        Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id]),
    ])
    estimate = await EstimateService(db).generate_estimate(project.id, user.id)
    return user, project, room, surface, item, group, g, estimate


class TestSnapshotAndOverride:
    async def test_description_base_status_and_price_book_edits_never_touch_draft_lines(
        self, db_session
    ):
        user, project, room, surface, item, group, g, estimate = await _estimate_with_coefficient(
            db_session, 1200301
        )
        line = estimate.lines[0]
        before = (line.unit_price, line.base_unit_price, list(line.coefficient_snapshot))
        coeff = PriceCoefficientService(db_session)
        await coeff.update_group(user.id, group.id, display_name="Zmieniona", description="Nowy opis")
        await coeff.update_option(user.id, g[1].id, description="Opis", display_name="Inna")
        await coeff.update_option(user.id, g[1].id, is_base=True)
        await coeff.archive_group(user.id, group.id)
        item.price = Decimal("99.00")
        await db_session.commit()

        fresh = await EstimateService(db_session).get_estimate_detail(project.id, estimate.id, user.id)
        after = fresh.lines[0]
        assert (after.unit_price, after.base_unit_price, list(after.coefficient_snapshot)) == before
        assert "description" not in after.coefficient_snapshot[0]

    async def test_reset_after_all_coefficients_removed_uses_current_base_without_snapshot(
        self, db_session
    ):
        user, project, room, surface, item, group, g, estimate = await _estimate_with_coefficient(
            db_session, 1200302
        )
        service = EstimateService(db_session)
        line = estimate.lines[0]
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"}, unit_price=Decimal("47.00"),
        )
        item.price = Decimal("50.00")
        await db_session.commit()
        await _set_plan(db_session, project, room, surface, user, [Sel(price_item_id=item.id)])
        reset = await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.price_override is False
        assert reset.unit_price == Decimal("50.00")
        assert reset.base_unit_price == Decimal("50.00")
        assert reset.coefficient_snapshot is None

    async def test_final_coefficient_line_rejects_every_pricing_mutation(self, db_session):
        user, project, room, surface, item, group, g, estimate = await _estimate_with_coefficient(
            db_session, 1200303
        )
        service = EstimateService(db_session)
        line_id = estimate.lines[0].id
        await service.finalize(estimate.id, user.id, project.id)

        with pytest.raises(EstimateStateError):
            await service.patch_line(
                project.id, estimate.id, user.id, line_id,
                provided_fields={"unit_price"}, unit_price=Decimal("1.00"),
            )
        with pytest.raises(EstimateStateError):
            await service.patch_line(
                project.id, estimate.id, user.id, line_id,
                provided_fields=set(), reset_price_override=True,
            )
        with pytest.raises(EstimateStateError):
            await service.regenerate_draft(estimate.id, user.id, project.id)
        with pytest.raises(EstimateStateError):
            await service.preview_regeneration(project.id, estimate.id, user.id)

        await PriceCoefficientService(db_session).update_option(
            user.id, g[1].id, percentage=Decimal("300")
        )
        fresh = await service.get_estimate_detail(project.id, estimate.id, user.id)
        assert fresh.lines[0].unit_price == Decimal("44.00")
        assert fresh.lines[0].coefficient_snapshot[0]["percentage"] == "10.000"


# ---------------------------------------------------------------------------
# 12. Archived assignment already in a WorkPlan
# ---------------------------------------------------------------------------


class TestArchivedAssignment:
    async def test_existing_assignment_stays_readable_resave_rejected_and_repairable(
        self, db_session
    ):
        user, project, room, surface, item = await _base_scenario(db_session, 1200401)
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        sel = [Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id])]
        await _set_plan(db_session, project, room, surface, user, sel)
        await PriceCoefficientService(db_session).archive_option(user.id, g[1].id)

        plan = await SurfaceWorkPlanService(db_session).get_work_plan(
            project.id, room.id, surface.id, user.id
        )
        assert [o.id for o in plan.planned_works[0].coefficient_options] == [g[1].id]

        # Generation keeps honouring the already-persisted selection.
        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        assert estimate.lines[0].unit_price == Decimal("44.00")

        ids = SimpleNamespace(
            project=project.id, room=room.id, surface=surface.id, user=user.id,
            item=item.id, base=g[0].id, archived=g[1].id,
        )
        with pytest.raises(PriceCoefficientValidationError):
            await _set_plan(db_session, project, room, surface, user, sel)
        await db_session.rollback()
        assert await _plan_selection(db_session, ids.surface) == [(ids.item, [ids.archived])]

        await SurfaceWorkPlanService(db_session).set_plan(
            ids.project, ids.room, ids.surface, ids.user,
            substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[Sel(price_item_id=ids.item, coefficient_option_ids=[ids.base])],
        )
        assert await _plan_selection(db_session, ids.surface) == [(ids.item, [ids.base])]

    async def test_option_in_use_cannot_be_hard_deleted(self, db_session):
        user, project, room, surface, item = await _base_scenario(db_session, 1200402)
        _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
        await _set_plan(db_session, project, room, surface, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=[g[1].id]),
        ])
        with pytest.raises(IntegrityError):
            await db_session.execute(delete(CoefficientOption).where(CoefficientOption.id == g[1].id))
            await db_session.commit()
        await db_session.rollback()


# ---------------------------------------------------------------------------
# 1. Cross-owner restore
# ---------------------------------------------------------------------------


async def test_cross_owner_restore_returns_404_without_side_effects(async_client: AsyncClient):
    owner = auth_header(await get_token(async_client, VALID_USER))
    other = auth_header(await get_token(async_client, OTHER_USER))
    group = (
        await async_client.post("/api/price-coefficient-groups", headers=owner, json={"display_name": "G"})
    ).json()
    option = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group['id']}/options",
            headers=owner, json={"display_name": "O", "percentage": "5"},
        )
    ).json()
    await async_client.post(f"/api/price-coefficient-groups/{group['id']}/archive", headers=owner)
    await async_client.post(f"/api/price-coefficient-options/{option['id']}/archive", headers=owner)

    r1 = await async_client.post(f"/api/price-coefficient-groups/{group['id']}/restore", headers=other)
    r2 = await async_client.post(f"/api/price-coefficient-options/{option['id']}/restore", headers=other)
    assert r1.status_code == 404
    assert r2.status_code == 404
    read = (
        await async_client.get(
            f"/api/price-coefficient-groups/{group['id']}?include_archived_options=true", headers=owner
        )
    ).json()
    assert read["is_archived"] is True
    assert read["options"][0]["is_archived"] is True


# ---------------------------------------------------------------------------
# 13. Stage 11 stays coefficient-agnostic
# ---------------------------------------------------------------------------


async def test_accepting_a_recommendation_preserves_existing_coefficients(db_session):
    from tests.test_work_recommendation_accept import _plan_works, _setup_actionable

    user, project, room, wall, plan, item, rec, service = await _setup_actionable(
        db_session, 1200501, with_plan_codes=["EXISTING_A"]
    )
    existing = (await _plan_works(db_session, plan.id))[0]
    _, g = await _make_group_with_options(db_session, user.id, percentages=["0", "10"])
    await SurfaceWorkPlanService(db_session).set_plan(
        project.id, room.id, wall.id, user.id,
        substrate=Substrate.GYPSUM_PLASTER,
        planned_works=[Sel(price_item_id=existing.price_item_id, coefficient_option_ids=[g[1].id])],
    )
    before = await _plan_selection(db_session, wall.id)

    await service.accept_recommendation(project.id, rec.id, user.id)

    after = await _plan_selection(db_session, wall.id)
    assert after[:-1] == before
    assert after[-1] == (item.id, [])


# ---------------------------------------------------------------------------
# 16. Model metadata matches the Stage 12 migrations
# ---------------------------------------------------------------------------


def test_assignment_index_names_match_migration_0024():
    """0024 shortened these index names to fit PostgreSQL's 63-byte limit;
    the model metadata must use the same names or autogenerate would try to
    drop and recreate them."""
    from app.core.database import Base

    expected = {
        "surface_planned_work_coefficient_assignments": {
            "ix_surface_planned_work_coefficient_assignments_work_id",
            "ix_surface_planned_work_coefficient_assignments_option_id",
        },
        "opening_reveal_planned_work_coefficient_assignments": {
            "ix_opening_reveal_coefficient_assignments_work_id",
            "ix_opening_reveal_coefficient_assignments_option_id",
        },
    }
    for table, names in expected.items():
        actual = {index.name for index in Base.metadata.tables[table].indexes}
        assert actual == names
        assert all(len(name) <= 63 for name in actual)


def test_description_columns_carry_no_model_only_comment():
    from app.core.database import Base

    for table in ("coefficient_groups", "coefficient_options"):
        assert Base.metadata.tables[table].c.description.comment is None
