"""Owner walkthrough bug: manual overrides were lost on Estimate regeneration.

Every WorkPlan / reveal-work save is a full replace that recreates the
occurrence rows with new ids, and regeneration matched existing lines only by
`planned_work_id`, so a re-saved occurrence became REMOVED + ADDED and the
owner's manual price (and quantity) override disappeared. Regeneration now
pairs lines by exact id first, then by logical key (surface, opening,
PriceItem) with duplicates paired by order.
"""
from decimal import Decimal

import pytest

from app.domain.exceptions import EstimateStateError
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from app.models.estimate import EstimateStatus, LineOrigin
from app.models.price_item import PriceCategory, PriceUnit
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


def _pcts(line) -> list[str]:
    return sorted(entry["percentage"] for entry in (line.coefficient_snapshot or []))


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


async def _override_price(service, project, estimate, user, line, value):
    return await service.patch_line(
        project.id, estimate.id, user.id, line.id,
        provided_fields={"unit_price"}, unit_price=Decimal(value),
    )


async def _reset_price(service, project, estimate, user, line):
    return await service.patch_line(
        project.id, estimate.id, user.id, line.id,
        provided_fields=set(), reset_price_override=True,
    )


async def _detail(service, project, estimate, user):
    return await service.get_estimate_detail(project.id, estimate.id, user.id)


# ---------------------------------------------------------------------------
# Owner walkthrough, opening reveal (A-F)
# ---------------------------------------------------------------------------


class TestOwnerWalkthroughOpeningReveal:
    async def _setup(self, db, telegram_id, *, price="20.00"):
        user = await _make_user(db, telegram_id)
        project = await _make_project(db, user.id)
        room = await _make_room(db, project.id)
        surface = await _make_surface(db, room.id)
        window = await _make_opening(
            db, surface.id, width="1.500", height="2.000", reveal_depth="0.200",
            reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False,
        )
        item = await _make_price_item(
            db, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM, price=price
        )
        _, opts = await _make_group_with_options(db, user.id, percentages=["0", "15", "25"])
        reveal = OpeningRevealWorkService(db)
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[opts[1].id]])
        service = EstimateService(db)
        estimate = await service.generate_estimate(project.id, user.id)
        return user, project, window, item, opts, reveal, service, estimate

    async def test_a_to_f_manual_30_survives_plus_25_and_reset_gives_25(self, db_session):
        user, project, window, item, opts, reveal, service, estimate = await self._setup(
            db_session, 1500001
        )
        line = estimate.lines[0]
        # A
        assert (line.quantity, line.base_unit_price, line.unit_price, line.amount) == (
            Decimal("5.500"), Decimal("20.00"), Decimal("23.00"), Decimal("126.50"),
        )
        # B
        overridden = await _override_price(service, project, estimate, user, line, "30.00")
        assert overridden.amount == Decimal("165.00") and overridden.price_override
        # C: +15 -> +25 (full replace, new occurrence id)
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[opts[2].id]])
        # D: preview reports the change but mutates nothing
        preview = await service.preview_regeneration(project.id, estimate.id, user.id)
        assert (preview.added, preview.removed, preview.updated) == (0, 0, 1)
        change = preview.changes[0]
        assert change.change_type == "UPDATED" and change.price_override is True
        assert change.new_unit_price == Decimal("30.00")
        before = (await _detail(service, project, estimate, user)).lines[0]
        assert (before.unit_price, before.price_override, before.amount, _pcts(before)) == (
            Decimal("30.00"), True, Decimal("165.00"), ["15.000"],
        )
        # E: regenerate keeps the manual price, refreshes provenance
        result = await service.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed, result.updated) == (0, 0, 1)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert after.id == line.id
        assert after.price_override is True
        assert after.unit_price == Decimal("30.00")
        assert after.base_unit_price == Decimal("20.00")
        assert _pcts(after) == ["25.000"]
        assert after.amount == Decimal("165.00")
        # F: reset uses CURRENT base + CURRENT coefficients
        reset = await _reset_price(service, project, estimate, user, after)
        assert reset.price_override is False
        assert reset.unit_price == Decimal("25.00")
        assert reset.quantity == Decimal("5.500")
        assert reset.amount == Decimal("137.50")

    async def test_coefficient_removal_keeps_override_and_reset_gives_raw_base(self, db_session):
        user, project, window, item, opts, reveal, service, estimate = await self._setup(
            db_session, 1500002
        )
        line = estimate.lines[0]
        await _override_price(service, project, estimate, user, line, "30.00")
        await reveal.set_works(window.id, user.id, [item.id])
        await service.regenerate_draft(estimate.id, user.id, project.id)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert (after.unit_price, after.price_override, after.coefficient_snapshot) == (
            Decimal("30.00"), True, [],
        )
        reset = await _reset_price(service, project, estimate, user, after)
        assert reset.unit_price == Decimal("20.00")

    async def test_reset_with_explicit_base_zero_percent(self, db_session):
        user, project, window, item, opts, reveal, service, estimate = await self._setup(
            db_session, 1500003
        )
        line = estimate.lines[0]
        await _override_price(service, project, estimate, user, line, "30.00")
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[opts[0].id]])
        await service.regenerate_draft(estimate.id, user.id, project.id)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert after.unit_price == Decimal("30.00") and after.price_override
        assert after.coefficient_snapshot[0]["is_base"] is True
        reset = await _reset_price(service, project, estimate, user, after)
        assert reset.unit_price == Decimal("20.00")
        assert reset.coefficient_snapshot[0]["is_base"] is True

    async def test_base_price_change_refreshes_provenance_but_keeps_override(self, db_session):
        user, project, window, item, opts, reveal, service, estimate = await self._setup(
            db_session, 1500004
        )
        line = estimate.lines[0]
        await _override_price(service, project, estimate, user, line, "30.00")
        item.price = Decimal("22.00")
        await db_session.commit()
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[opts[1].id]])
        await service.regenerate_draft(estimate.id, user.id, project.id)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert (after.base_unit_price, after.unit_price, after.price_override) == (
            Decimal("22.00"), Decimal("30.00"), True,
        )
        reset = await _reset_price(service, project, estimate, user, after)
        assert reset.unit_price == Decimal("25.30")  # 22.00 x 1.15

    async def test_null_current_base_keeps_manual_price_until_reset(self, db_session):
        user, project, window, item, opts, reveal, service, estimate = await self._setup(
            db_session, 1500005
        )
        line = estimate.lines[0]
        await _override_price(service, project, estimate, user, line, "30.00")
        item.price = None
        await db_session.commit()
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[opts[1].id]])
        await service.regenerate_draft(estimate.id, user.id, project.id)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert after.base_unit_price is None
        assert (after.unit_price, after.price_override, after.amount) == (
            Decimal("30.00"), True, Decimal("165.00"),
        )
        reset = await _reset_price(service, project, estimate, user, after)
        assert reset.unit_price is None and reset.amount is None

    async def test_zero_current_base_keeps_manual_price_until_reset(self, db_session):
        user, project, window, item, opts, reveal, service, estimate = await self._setup(
            db_session, 1500006
        )
        line = estimate.lines[0]
        await _override_price(service, project, estimate, user, line, "30.00")
        item.price = Decimal("0.00")
        await db_session.commit()
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[opts[2].id]])
        await service.regenerate_draft(estimate.id, user.id, project.id)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert (after.base_unit_price, after.unit_price, after.price_override) == (
            Decimal("0.00"), Decimal("30.00"), True,
        )
        reset = await _reset_price(service, project, estimate, user, after)
        assert reset.unit_price == Decimal("0.00") and reset.amount == Decimal("0.00")

    async def test_final_and_accepted_estimates_stay_immutable(self, db_session):
        user, project, window, item, opts, reveal, service, estimate = await self._setup(
            db_session, 1500007
        )
        line = estimate.lines[0]
        await _override_price(service, project, estimate, user, line, "30.00")
        await service.finalize(estimate.id, user.id, project.id)
        await reveal.set_works(window.id, user.id, [item.id], coefficient_option_ids=[[opts[2].id]])
        for status in (EstimateStatus.FINAL, EstimateStatus.ACCEPTED):
            fresh = await _detail(service, project, estimate, user)
            fresh.status = status
            await db_session.commit()
            with pytest.raises(EstimateStateError):
                await service.regenerate_draft(estimate.id, user.id, project.id)
            with pytest.raises(EstimateStateError):
                await service.preview_regeneration(project.id, estimate.id, user.id)
            with pytest.raises(EstimateStateError):
                await _reset_price(service, project, estimate, user, line)
            kept = (await _detail(service, project, estimate, user)).lines[0]
            assert (kept.unit_price, kept.price_override, _pcts(kept)) == (
                Decimal("30.00"), True, ["15.000"],
            )


# ---------------------------------------------------------------------------
# Surface parity, duplicates, quantity override, MANUAL lines
# ---------------------------------------------------------------------------


class TestSurfaceOverridePreservation:
    async def _setup(self, db, telegram_id):
        user = await _make_user(db, telegram_id)
        project = await _make_project(db, user.id)
        room = await _make_room(db, project.id)
        surface = await _make_surface(db, room.id)  # 5.000 x 2.700 = 13.500 m2
        item = await _make_price_item(db, user.id, price="20.00")
        _, opts = await _make_group_with_options(db, user.id, percentages=["0", "15", "25"])
        plans = SurfaceWorkPlanService(db)
        return user, project, room, surface, item, opts, plans, EstimateService(db)

    async def _save(self, plans, project, room, surface, user, selections):
        await plans.set_plan(
            project.id, room.id, surface.id, user.id,
            substrate=Substrate.GYPSUM_PLASTER, planned_works=selections,
        )

    async def test_surface_price_override_survives_coefficient_change(self, db_session):
        user, project, room, surface, item, opts, plans, service = await self._setup(db_session, 1500101)
        await self._save(plans, project, room, surface, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=[opts[1].id]),
        ])
        estimate = await service.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        await _override_price(service, project, estimate, user, line, "30.00")
        (key,) = await _current_keys(db_session, surface.id)
        await self._save(plans, project, room, surface, user, [
            Sel(price_item_id=item.id, occurrence_key=key, coefficient_option_ids=[opts[2].id]),
        ])
        await service.regenerate_draft(estimate.id, user.id, project.id)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert (after.id, after.unit_price, after.price_override, _pcts(after)) == (
            line.id, Decimal("30.00"), True, ["25.000"],
        )
        reset = await _reset_price(service, project, estimate, user, after)
        assert reset.unit_price == Decimal("25.00")

    async def test_quantity_override_survives_a_resave(self, db_session):
        user, project, room, surface, item, opts, plans, service = await self._setup(db_session, 1500102)
        await self._save(plans, project, room, surface, user, [Sel(price_item_id=item.id)])
        estimate = await service.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        await service.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"quantity"}, quantity=Decimal("9.000"),
        )
        (key,) = await _current_keys(db_session, surface.id)
        await self._save(plans, project, room, surface, user, [
            Sel(price_item_id=item.id, occurrence_key=key, coefficient_option_ids=[opts[1].id]),
        ])
        await service.regenerate_draft(estimate.id, user.id, project.id)
        after = (await _detail(service, project, estimate, user)).lines[0]
        assert (after.quantity, after.quantity_overridden, after.source_quantity) == (
            Decimal("9.000"), True, Decimal("13.500"),
        )
        assert after.amount == Decimal("207.00")  # 9.000 x 23.00

    async def test_duplicate_occurrences_keep_their_own_overrides_by_order(self, db_session):
        user, project, room, surface, item, opts, plans, service = await self._setup(db_session, 1500103)
        await self._save(plans, project, room, surface, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=[opts[1].id]),
            Sel(price_item_id=item.id, coefficient_option_ids=[opts[2].id]),
        ])
        estimate = await service.generate_estimate(project.id, user.id)
        first, second = sorted(estimate.lines, key=lambda ln: ln.position)
        await _override_price(service, project, estimate, user, first, "30.00")
        await service.patch_line(
            project.id, estimate.id, user.id, second.id,
            provided_fields={"quantity"}, quantity=Decimal("3.000"),
        )
        # Re-save identically, echoing the keys (all occurrence ids change).
        k1, k2 = await _current_keys(db_session, surface.id)
        await self._save(plans, project, room, surface, user, [
            Sel(price_item_id=item.id, occurrence_key=k1, coefficient_option_ids=[opts[1].id]),
            Sel(price_item_id=item.id, occurrence_key=k2, coefficient_option_ids=[opts[2].id]),
        ])
        result = await service.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (0, 0)
        a, b = sorted((await _detail(service, project, estimate, user)).lines, key=lambda ln: ln.position)
        assert (a.id, a.unit_price, a.price_override, a.quantity_overridden, _pcts(a)) == (
            first.id, Decimal("30.00"), True, False, ["15.000"],
        )
        assert (b.id, b.quantity, b.quantity_overridden, b.price_override, _pcts(b)) == (
            second.id, Decimal("3.000"), True, False, ["25.000"],
        )
        assert b.unit_price == Decimal("25.00")

    async def test_removing_one_duplicate_keeps_the_first_in_order(self, db_session):
        user, project, room, surface, item, opts, plans, service = await self._setup(db_session, 1500104)
        await self._save(plans, project, room, surface, user, [
            Sel(price_item_id=item.id), Sel(price_item_id=item.id),
        ])
        estimate = await service.generate_estimate(project.id, user.id)
        first, second = sorted(estimate.lines, key=lambda ln: ln.position)
        await _override_price(service, project, estimate, user, first, "30.00")
        k1, _k2 = await _current_keys(db_session, surface.id)
        await self._save(plans, project, room, surface, user, [Sel(price_item_id=item.id, occurrence_key=k1)])
        result = await service.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (0, 1)
        lines = (await _detail(service, project, estimate, user)).lines
        assert [ln.id for ln in lines] == [first.id]
        assert lines[0].unit_price == Decimal("30.00")

    async def test_manual_lines_unchanged_across_resave_and_regeneration(self, db_session):
        from app.models.price_item import PriceScope

        user, project, room, surface, item, opts, plans, service = await self._setup(db_session, 1500105)
        await self._save(plans, project, room, surface, user, [Sel(price_item_id=item.id)])
        estimate = await service.generate_estimate(project.id, user.id)
        manual = await service.add_manual_line(
            estimate.id, user.id, description="Dojazd", scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT, quantity=Decimal("1.000"), unit_price=Decimal("50.00"),
            project_id=project.id,
        )
        await self._save(plans, project, room, surface, user, [
            Sel(price_item_id=item.id, coefficient_option_ids=[opts[1].id]),
        ])
        result = await service.regenerate_draft(estimate.id, user.id, project.id)
        assert result.preserved_manual == 1
        lines = (await _detail(service, project, estimate, user)).lines
        manual_lines = [ln for ln in lines if ln.origin == LineOrigin.MANUAL]
        assert [(ln.id, ln.unit_price, ln.quantity, ln.description) for ln in manual_lines] == [
            (manual.id, Decimal("50.00"), Decimal("1.000"), "Dojazd")
        ]
