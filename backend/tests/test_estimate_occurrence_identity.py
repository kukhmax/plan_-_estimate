"""Stage 13E.2B — Estimate occurrence identity (migration 0028).

Same Surface occurrence_key => same logical work: an ordinary WorkPlan save
that recreates the row keeps Estimate overrides. A different key is different
work: old overrides never migrate. Legacy (key-less) lines use a bounded,
self-upgrading fallback that a template REPLACE record disables. Reveal,
MANUAL and FINAL/ACCEPTED behaviour is unchanged. The migration backfill is
exercised with the migration's own SQL.
"""
from decimal import Decimal
import importlib.util
from pathlib import Path
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import EstimateStateError
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from app.models.estimate import Estimate, EstimateLine, EstimateStatus, LineOrigin
from app.models.price_item import PriceCategory, PriceScope, PriceUnit
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.models.workflow_template import (
    SurfaceWorkPlanTemplateApplication,
    TemplateApplicationMode,
)
from app.schemas.work_plan import OrderedPriceItemSelection as Sel
from tests.test_estimates import (
    _make_opening,
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
    _make_user,
)
from tests.test_planned_work_coefficient_assignments import _make_group_with_options

_MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0028_estimate_line_occurrence_key.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("m0028", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pcts(line) -> list[str]:
    return sorted(e["percentage"] for e in (line.coefficient_snapshot or []))


async def _setup(db, telegram_id, *, price="20.00"):
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)  # 5.000 x 2.700 = 13.500 m2
    item = await _make_price_item(db, user.id, price=price)
    _, opts = await _make_group_with_options(db, user.id, percentages=["0", "15", "25"])
    return user, project, room, surface, item, opts


async def _save(db, user, project, room, surface, selections):
    return await SurfaceWorkPlanService(db).set_plan(
        project.id, room.id, surface.id, user.id,
        substrate=Substrate.GYPSUM_PLASTER, planned_works=selections,
    )


async def _works(db, surface_id) -> list[SurfacePlannedWork]:
    rows = await db.execute(
        select(SurfacePlannedWork)
        .join(SurfaceWorkPlan, SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id)
        .where(SurfaceWorkPlan.surface_id == surface_id)
        .order_by(SurfacePlannedWork.position)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _lines(db, estimate_id) -> list[EstimateLine]:
    rows = await db.execute(
        select(EstimateLine)
        .where(EstimateLine.estimate_id == estimate_id)
        .order_by(EstimateLine.position)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _override(svc, project, estimate, user, line, *, price=None, quantity=None):
    fields, kw = set(), {}
    if price is not None:
        fields.add("unit_price")
        kw["unit_price"] = Decimal(price)
    if quantity is not None:
        fields.add("quantity")
        kw["quantity"] = Decimal(quantity)
    return await svc.patch_line(project.id, estimate.id, user.id, line.id, provided_fields=fields, **kw)


# ---------------------------------------------------------------------------
# Migration 0028 backfill (1-7), with the migration's own SQL
# ---------------------------------------------------------------------------


class TestMigrationBackfill:
    async def _estimate_with_line(self, db, telegram_id, status=EstimateStatus.DRAFT):
        user, project, room, surface, item, opts = await _setup(db, telegram_id)
        await _save(db, user, project, room, surface, [Sel(price_item_id=item.id)])
        svc = EstimateService(db)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db, estimate.id)
        (work,) = await _works(db, surface.id)
        line.occurrence_key = None  # simulate a pre-0028 row
        estimate_row = await db.get(Estimate, estimate.id)
        estimate_row.status = status
        await db.commit()
        return user, project, room, surface, item, estimate, line, work

    async def _run_backfill(self, db):
        await db.execute(text(_migration_module().BACKFILL_SQL))
        await db.commit()

    async def test_resolvable_draft_surface_line_is_backfilled(self, db_session):
        *_, estimate, line, work = await self._estimate_with_line(db_session, 1305001)
        await self._run_backfill(db_session)
        (line,) = await _lines(db_session, estimate.id)
        assert line.occurrence_key == work.occurrence_key

    async def test_stale_planned_work_id_stays_null(self, db_session):
        *_, estimate, line, work = await self._estimate_with_line(db_session, 1305002)
        line.planned_work_id = uuid.uuid4()
        await db_session.commit()
        await self._run_backfill(db_session)
        assert (await _lines(db_session, estimate.id))[0].occurrence_key is None

    async def test_price_item_mismatch_stays_null(self, db_session):
        user, *_, estimate, line, work = await self._estimate_with_line(db_session, 1305003)
        other = await _make_price_item(db_session, user.id)
        line.price_item_id = other.id
        await db_session.commit()
        await self._run_backfill(db_session)
        assert (await _lines(db_session, estimate.id))[0].occurrence_key is None

    @pytest.mark.parametrize("status", [EstimateStatus.FINAL, EstimateStatus.ACCEPTED])
    async def test_final_and_accepted_stay_null(self, db_session, status):
        *_, estimate, line, work = await self._estimate_with_line(
            db_session, 1305004 if status == EstimateStatus.FINAL else 1305005, status
        )
        await self._run_backfill(db_session)
        assert (await _lines(db_session, estimate.id))[0].occurrence_key is None

    async def test_duplicate_planned_work_id_in_one_estimate_stays_null(self, db_session):
        *_, estimate, line, work = await self._estimate_with_line(db_session, 1305006)
        clone = EstimateLine(**{
            c.key: getattr(line, c.key) for c in EstimateLine.__table__.columns if c.key not in ("id", "position")
        }, position=99)
        db_session.add(clone)
        await db_session.commit()
        await self._run_backfill(db_session)
        assert all(ln.occurrence_key is None for ln in await _lines(db_session, estimate.id))

    async def test_manual_and_reveal_lines_stay_null(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305007)
        window = await _make_opening(db_session, surface.id)
        reveal_item = await _make_price_item(db_session, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM)
        await OpeningRevealWorkService(db_session).set_works(window.id, user.id, [reveal_item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        await svc.add_manual_line(
            estimate.id, user.id, description="Dojazd", scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT, quantity=Decimal("1.000"), unit_price=Decimal("50.00"),
            project_id=project.id,
        )
        await self._run_backfill(db_session)
        lines = await _lines(db_session, estimate.id)
        assert {ln.origin for ln in lines} == {LineOrigin.PLANNED_WORK, LineOrigin.MANUAL}
        assert all(ln.occurrence_key is None for ln in lines)


# ---------------------------------------------------------------------------
# Snapshot on creation (8, 9, 30)
# ---------------------------------------------------------------------------


class TestSnapshot:
    async def test_generation_snapshots_surface_key_and_leaves_reveal_null(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305101)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)] * 2)
        window = await _make_opening(db_session, surface.id)
        reveal_item = await _make_price_item(db_session, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM)
        await OpeningRevealWorkService(db_session).set_works(window.id, user.id, [reveal_item.id])
        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        works = await _works(db_session, surface.id)
        lines = await _lines(db_session, estimate.id)
        surface_lines = [ln for ln in lines if ln.opening_id is None]
        reveal_lines = [ln for ln in lines if ln.opening_id is not None]
        assert [ln.occurrence_key for ln in surface_lines] == [w.occurrence_key for w in works]
        assert reveal_lines and all(ln.occurrence_key is None for ln in reveal_lines)

    async def test_partial_unique_index(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305102)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        base = {c.key: getattr(line, c.key) for c in EstimateLine.__table__.columns if c.key not in ("id", "position", "occurrence_key")}
        db_session.add_all([EstimateLine(**base, position=50), EstimateLine(**base, position=51)])
        await db_session.commit()  # two NULL keys are fine
        db_session.add(EstimateLine(**base, position=52, occurrence_key=line.occurrence_key))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


# ---------------------------------------------------------------------------
# Ordinary key-preserving save (10-13, 29)
# ---------------------------------------------------------------------------


class TestOrdinarySave:
    async def test_same_key_keeps_overrides_repoints_and_refreshes(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305201)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id, coefficient_option_ids=[opts[1].id])])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, line, price="30.00", quantity="9.000")
        (work_a,) = await _works(db_session, surface.id)
        key, old_row = work_a.occurrence_key, work_a.id
        line_id = line.id

        item.price = Decimal("22.00")
        await db_session.commit()
        await _save(db_session, user, project, room, surface, [
            Sel(price_item_id=item.id, occurrence_key=key, coefficient_option_ids=[opts[2].id]),
        ])
        (work_b,) = await _works(db_session, surface.id)
        assert work_b.id != old_row and work_b.occurrence_key == key

        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (0, 0)
        (after,) = await _lines(db_session, estimate.id)
        assert after.id == line_id
        assert (after.planned_work_id, after.occurrence_key) == (work_b.id, key)
        assert (after.unit_price, after.price_override) == (Decimal("30.00"), True)
        assert (after.quantity, after.quantity_overridden) == (Decimal("9.000"), True)
        assert after.base_unit_price == Decimal("22.00")
        assert _pcts(after) == ["25.000"]

    async def test_duplicates_keep_their_own_overrides_even_reordered(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305202)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)] * 2)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        la, lb = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, la, price="30.00")
        await _override(svc, project, estimate, user, lb, price="40.00")
        ka, kb = (w.occurrence_key for w in await _works(db_session, surface.id))
        # reorder: B first, A second -- identity follows the key, not the position
        await _save(db_session, user, project, room, surface, [
            Sel(price_item_id=item.id, occurrence_key=kb), Sel(price_item_id=item.id, occurrence_key=ka),
        ])
        await svc.regenerate_draft(estimate.id, user.id, project.id)
        by_key = {ln.occurrence_key: ln.unit_price for ln in await _lines(db_session, estimate.id)}
        assert by_key == {ka: Decimal("30.00"), kb: Decimal("40.00")}


# ---------------------------------------------------------------------------
# Different key = different work (15-17, 23)
# ---------------------------------------------------------------------------


class TestDifferentKey:
    async def test_new_key_does_not_inherit_price_or_quantity_override(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305301)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, line, price="30.00", quantity="9.000")
        old_line_id = line.id
        # replace the occurrence (same surface, same PriceItem, NEW key)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])

        preview = await svc.preview_regeneration(project.id, estimate.id, user.id)
        assert (preview.added, preview.removed) == (1, 1)
        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (1, 1)
        (new,) = await _lines(db_session, estimate.id)
        assert new.id != old_line_id
        assert (new.unit_price, new.price_override) == (Decimal("20.00"), False)
        assert (new.quantity, new.quantity_overridden) == (Decimal("13.500"), False)

    async def test_duplicates_replaced_by_new_keys_give_removed_and_added(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305302)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)] * 2)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        la, lb = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, la, price="30.00")
        await _override(svc, project, estimate, user, lb, price="40.00")
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)] * 2)  # C, D
        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (2, 2)
        lines = await _lines(db_session, estimate.id)
        assert all(not ln.price_override and ln.unit_price == Decimal("20.00") for ln in lines)
        assert {ln.id for ln in lines}.isdisjoint({la.id, lb.id})

    async def test_removed_line_cannot_resurrect(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305303)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, line, price="30.00")
        old_id = line.id
        await _save(db_session, user, project, room, surface, [])
        await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert await _lines(db_session, estimate.id) == []
        assert await db_session.get(EstimateLine, old_id) is None
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        await svc.regenerate_draft(estimate.id, user.id, project.id)
        (fresh,) = await _lines(db_session, estimate.id)
        assert (fresh.unit_price, fresh.price_override) == (Decimal("20.00"), False)

    async def test_keyless_resave_now_means_new_work(self, db_session):
        """Documents the 13E.2B contract change: a legacy key-less save
        creates new occurrences, so overrides no longer follow it. The editor
        must echo occurrence_key (13E) to keep overrides on ordinary saves."""
        user, project, room, surface, item, opts = await _setup(db_session, 1305304)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, line, price="30.00")
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id, coefficient_option_ids=[opts[1].id])])
        await svc.regenerate_draft(estimate.id, user.id, project.id)
        (new,) = await _lines(db_session, estimate.id)
        assert new.price_override is False


# ---------------------------------------------------------------------------
# Legacy NULL fallback (18-22)
# ---------------------------------------------------------------------------


class TestLegacyFallback:
    async def _legacy(self, db, telegram_id):
        user, project, room, surface, item, opts = await _setup(db, telegram_id)
        await _save(db, user, project, room, surface, [Sel(price_item_id=item.id)])
        svc = EstimateService(db)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db, estimate.id)
        await _override(svc, project, estimate, user, line, price="30.00")
        line = await db.get(EstimateLine, line.id)
        line.occurrence_key = None  # pre-0028 line
        await db.commit()
        # plan re-saved since generation (key-less legacy client): stale id, new key
        await _save(db, user, project, room, surface, [Sel(price_item_id=item.id)])
        return user, project, room, surface, item, svc, estimate, line.id

    async def test_preview_matches_but_persists_nothing(self, db_session):
        user, project, room, surface, item, svc, estimate, line_id = await self._legacy(db_session, 1305401)
        (stale_pwid,) = [ln.planned_work_id for ln in await _lines(db_session, estimate.id)]
        preview = await svc.preview_regeneration(project.id, estimate.id, user.id)
        assert (preview.added, preview.removed) == (0, 0)
        (line,) = await _lines(db_session, estimate.id)
        assert (line.occurrence_key, line.planned_work_id) == (None, stale_pwid)

    async def test_regeneration_matches_and_upgrades_then_new_key_cannot_inherit(self, db_session):
        user, project, room, surface, item, svc, estimate, line_id = await self._legacy(db_session, 1305402)
        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed, result.updated) == (0, 0, 0)
        (work,) = await _works(db_session, surface.id)
        (line,) = await _lines(db_session, estimate.id)
        assert (line.id, line.occurrence_key, line.unit_price) == (line_id, work.occurrence_key, Decimal("30.00"))
        # upgraded: a later different key is different work
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (1, 1)
        (new,) = await _lines(db_session, estimate.id)
        assert new.price_override is False

    async def test_replace_provenance_blocks_legacy_fallback(self, db_session):
        user, project, room, surface, item, svc, estimate, line_id = await self._legacy(db_session, 1305403)
        plan = (await db_session.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == surface.id))).scalar_one()
        db_session.add(SurfaceWorkPlanTemplateApplication(
            work_plan_id=plan.id, template_code="T", template_name="T",
            mode=TemplateApplicationMode.REPLACE, steps_applied=1,
        ))
        await db_session.commit()
        preview = await svc.preview_regeneration(project.id, estimate.id, user.id)
        assert (preview.added, preview.removed) == (1, 1)
        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (1, 1)
        (new,) = await _lines(db_session, estimate.id)
        assert new.id != line_id and new.price_override is False

    async def test_append_provenance_does_not_block_fallback(self, db_session):
        user, project, room, surface, item, svc, estimate, line_id = await self._legacy(db_session, 1305404)
        plan = (await db_session.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == surface.id))).scalar_one()
        db_session.add(SurfaceWorkPlanTemplateApplication(
            work_plan_id=plan.id, template_code="T", template_name="T",
            mode=TemplateApplicationMode.APPEND, steps_applied=1,
        ))
        await db_session.commit()
        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (0, 0)


# ---------------------------------------------------------------------------
# Reveal, MANUAL, FINAL, reset (24-28)
# ---------------------------------------------------------------------------


class TestUnchangedAndReset:
    async def test_reveal_overrides_survive_reveal_resave(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305501)
        window = await _make_opening(db_session, surface.id)
        reveal_item = await _make_price_item(db_session, user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM, price="20.00")
        reveal = OpeningRevealWorkService(db_session)
        await reveal.set_works(window.id, user.id, [reveal_item.id])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, line, price="33.00", quantity="4.000")
        await reveal.set_works(window.id, user.id, [reveal_item.id])  # recreated row, no key
        result = await svc.regenerate_draft(estimate.id, user.id, project.id)
        assert (result.added, result.removed) == (0, 0)
        (after,) = await _lines(db_session, estimate.id)
        assert (after.id, after.unit_price, after.quantity, after.occurrence_key) == (
            line.id, Decimal("33.00"), Decimal("4.000"), None,
        )

    async def test_manual_line_untouched(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305502)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        manual = await svc.add_manual_line(
            estimate.id, user.id, description="Dojazd", scope=PriceScope.LABOR,
            unit=PriceUnit.FLAT, quantity=Decimal("1.000"), unit_price=Decimal("50.00"),
            project_id=project.id,
        )
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        await svc.regenerate_draft(estimate.id, user.id, project.id)
        kept = await db_session.get(EstimateLine, manual.id)
        assert (kept.origin, kept.unit_price, kept.occurrence_key) == (LineOrigin.MANUAL, Decimal("50.00"), None)

    async def test_final_cannot_be_regenerated_and_keeps_snapshot(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305503)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        key = line.occurrence_key
        await svc.finalize(estimate.id, user.id, project.id)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])
        with pytest.raises(EstimateStateError):
            await svc.regenerate_draft(estimate.id, user.id, project.id)
        with pytest.raises(EstimateStateError):
            await svc.preview_regeneration(project.id, estimate.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        assert line.occurrence_key == key

    async def test_reset_after_ordinary_save_resolves_occurrence_by_key(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305504)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id, coefficient_option_ids=[opts[1].id])])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, line, price="30.00")
        (work,) = await _works(db_session, surface.id)
        # ordinary save (new row id, same key), NOT regenerated yet
        await _save(db_session, user, project, room, surface, [
            Sel(price_item_id=item.id, occurrence_key=work.occurrence_key, coefficient_option_ids=[opts[2].id]),
        ])
        reset = await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert (reset.unit_price, reset.price_override, _pcts(reset)) == (Decimal("25.00"), False, ["25.000"])

    async def test_reset_with_unknown_key_falls_back_to_price_item(self, db_session):
        user, project, room, surface, item, opts = await _setup(db_session, 1305505)
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id, coefficient_option_ids=[opts[1].id])])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(project.id, user.id)
        (line,) = await _lines(db_session, estimate.id)
        await _override(svc, project, estimate, user, line, price="30.00")
        await _save(db_session, user, project, room, surface, [Sel(price_item_id=item.id)])  # new key
        reset = await svc.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert (reset.unit_price, reset.coefficient_snapshot) == (Decimal("20.00"), None)
