"""Stage 13B — stable logical occurrence identity (D13) and the materialised
technological break (D9) on SurfacePlannedWork.

Covers: server-generated keys; preservation across the Stage 10 full-replace
save while the row id changes; payload key validation (duplicate, foreign,
invented, stale, changed PriceItem) with the plan left unchanged on every
rejection; wait_after_hours persistence/validation; apply-to-all (new keys,
breaks and coefficients copied); Stage 11 append (new key, no break, no
provenance); the HTTP mapping (GET exposes the key, 409 on conflict); and
Stage 12 Estimate override behaviour with key-preserving saves.
"""
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import (
    SurfaceWorkPlanOccurrenceConflictError,
    SurfaceWorkPlanValidationError,
)
from app.domain.services.estimate_service import EstimateService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import QualityLevel, Substrate
from app.models.surface import SurfaceType
from app.models.user import User
from app.models.work_plan import (
    SurfacePlannedWork,
    SurfacePlannedWorkCoefficientAssignment,
    SurfaceWorkPlan,
)
from app.models.workflow_template import SurfaceWorkPlanTemplateApplication
from app.schemas.work_plan import OrderedPriceItemSelection
from tests.test_planned_work_coefficient_assignments import (
    VALID_USER,
    _make_group_with_options,
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
    _make_user,
    _wp,
    auth_header,
    get_token,
)

Sel = OrderedPriceItemSelection


async def _setup(db, telegram_id: int):
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    a = await _make_price_item(db, user.id, code=f"A_{telegram_id}")
    b = await _make_price_item(db, user.id, code=f"B_{telegram_id}")
    return user, project, room, surface, a, b, SurfaceWorkPlanService(db)


async def _save(service, user, project, room, surface, selection, **kw):
    return await service.set_plan(
        project.id, room.id, surface.id, user.id,
        substrate=kw.get("substrate", Substrate.GYPSUM_PLASTER),
        quality_target=kw.get("quality_target"),
        planned_works=selection,
    )


async def _state(db, surface_id) -> tuple:
    """Persisted plan state read straight from the DB (after a rollback)."""
    plan = (
        await db.execute(
            select(SurfaceWorkPlan)
            .where(SurfaceWorkPlan.surface_id == surface_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    works = (
        await db.execute(
            select(SurfacePlannedWork)
            .where(SurfacePlannedWork.work_plan_id == plan.id)
            .order_by(SurfacePlannedWork.position)
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    rows = []
    for w in works:
        options = (
            await db.execute(
                select(SurfacePlannedWorkCoefficientAssignment.coefficient_option_id)
                .where(SurfacePlannedWorkCoefficientAssignment.surface_planned_work_id == w.id)
            )
        ).scalars().all()
        rows.append(
            (w.id, w.occurrence_key, w.price_item_id, w.position, w.wait_after_hours,
             sorted(str(o) for o in options))
        )
    return plan.substrate, plan.quality_target, rows


# ---------------------------------------------------------------------------
# Generation and preservation
# ---------------------------------------------------------------------------


class TestKeyGenerationAndPreservation:
    async def test_new_occurrences_get_server_generated_unique_keys(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301001)
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)] * 2 + [Sel(price_item_id=b.id)])
        keys = [w.occurrence_key for w in plan.planned_works]
        assert all(isinstance(k, uuid.UUID) for k in keys)
        assert len(set(keys)) == 3  # duplicate PriceItems get distinct keys
        # never derived from the row id or the PriceItem
        for w in plan.planned_works:
            assert w.occurrence_key not in (w.id, w.price_item_id, w.work_plan_id)

    async def test_full_replace_preserves_key_while_row_id_changes(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301002)
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id), Sel(price_item_id=b.id)])
        before = [(w.id, w.occurrence_key, w.price_item_id) for w in plan.planned_works]
        # reorder + re-save, echoing the keys
        plan = await _save(service, user, project, room, surface, [
            Sel(price_item_id=b.id, occurrence_key=before[1][1]),
            Sel(price_item_id=a.id, occurrence_key=before[0][1]),
        ])
        after = [(w.id, w.occurrence_key, w.price_item_id) for w in plan.planned_works]
        assert [k for _, k, _ in after] == [before[1][1], before[0][1]]
        assert [p for _, _, p in after] == [b.id, a.id]
        assert {i for i, _, _ in after}.isdisjoint({i for i, _, _ in before})

    async def test_missing_key_creates_new_occurrence_identity(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301003)
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        old_key = plan.planned_works[0].occurrence_key
        plan = await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, occurrence_key=old_key),
            Sel(price_item_id=a.id),
        ])
        keys = [w.occurrence_key for w in plan.planned_works]
        assert keys[0] == old_key
        assert keys[1] != old_key

    async def test_legacy_keyless_save_resets_identity(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301004)
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        old_key = plan.planned_works[0].occurrence_key
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        assert plan.planned_works[0].occurrence_key != old_key

    async def test_replace_planned_works_preserves_keys(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301005)
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        key = plan.planned_works[0].occurrence_key
        plan = await service.replace_planned_works(
            project.id, room.id, surface.id, user.id,
            planned_works=[Sel(price_item_id=a.id, occurrence_key=key), Sel(price_item_id=b.id)],
        )
        assert plan.planned_works[0].occurrence_key == key

    async def test_coefficients_and_break_travel_with_preserved_key(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301006)
        _, opts = await _make_group_with_options(db_session, user.id, percentages=["0", "15"])
        plan = await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, coefficient_option_ids=[opts[1].id], wait_after_hours=24),
        ])
        key = plan.planned_works[0].occurrence_key
        plan = await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, occurrence_key=key, coefficient_option_ids=[opts[1].id], wait_after_hours=24),
        ])
        work = plan.planned_works[0]
        assert (work.occurrence_key, work.wait_after_hours) == (key, 24)
        assert [o.id for o in work.coefficient_options] == [opts[1].id]

    async def test_db_enforces_global_uniqueness(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301007)
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        key = plan.planned_works[0].occurrence_key
        other_surface = await _make_surface(db_session, room.id)
        other = SurfaceWorkPlan(surface_id=other_surface.id, substrate=Substrate.CONCRETE)
        db_session.add(other)
        await db_session.flush()
        db_session.add(SurfacePlannedWork(
            work_plan_id=other.id, price_item_id=a.id, position=0, occurrence_key=key,
        ))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


# ---------------------------------------------------------------------------
# Payload key validation; every rejection leaves the plan unchanged
# ---------------------------------------------------------------------------


class TestKeyValidationIsTransactional:
    async def _prepared(self, db, telegram_id):
        user, project, room, surface, a, b, service = await _setup(db, telegram_id)
        _, opts = await _make_group_with_options(db, user.id, percentages=["0", "15"])
        plan = await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, coefficient_option_ids=[opts[1].id], wait_after_hours=12),
            Sel(price_item_id=b.id),
        ], quality_target=QualityLevel.S2)
        keys = [w.occurrence_key for w in plan.planned_works]
        surface_id = surface.id
        before = await _state(db, surface_id)
        return user, project, room, surface, a, b, service, keys, surface_id, before

    async def _assert_rejected_and_unchanged(self, db, exc_type, call, surface_id, before):
        with pytest.raises(exc_type):
            await call()
        await db.rollback()
        assert await _state(db, surface_id) == before

    async def test_duplicate_key_in_payload_rejected(self, db_session):
        user, project, room, surface, a, b, service, keys, sid, before = await self._prepared(db_session, 1301101)
        await self._assert_rejected_and_unchanged(
            db_session, SurfaceWorkPlanValidationError,
            lambda: _save(service, user, project, room, surface, [
                Sel(price_item_id=a.id, occurrence_key=keys[0]),
                Sel(price_item_id=a.id, occurrence_key=keys[0]),
            ], substrate=Substrate.CONCRETE),
            sid, before,
        )

    async def test_key_of_another_plan_same_owner_rejected(self, db_session):
        user, project, room, surface, a, b, service, keys, sid, before = await self._prepared(db_session, 1301102)
        other = await _make_surface(db_session, room.id)
        other_plan = await service.set_plan(
            project.id, room.id, other.id, user.id,
            substrate=Substrate.GYPSUM_PLASTER, planned_works=[Sel(price_item_id=a.id)],
        )
        foreign_key = other_plan.planned_works[0].occurrence_key
        await self._assert_rejected_and_unchanged(
            db_session, SurfaceWorkPlanOccurrenceConflictError,
            lambda: _save(service, user, project, room, surface, [
                Sel(price_item_id=a.id, occurrence_key=foreign_key),
            ]),
            sid, before,
        )

    async def test_key_of_another_owner_rejected_without_disclosure(self, db_session):
        user, project, room, surface, a, b, service, keys, sid, before = await self._prepared(db_session, 1301103)
        intruder, i_project, i_room, i_surface, i_a, _, _ = await _setup(db_session, 1301104)
        # capture ids: objects expire on rollback
        i_ids = (i_project.id, i_room.id, i_surface.id, intruder.id)
        i_item_id = i_a.id
        invented = uuid.uuid4()
        errors = []
        for key in (keys[0], invented):  # a real foreign key vs an invented one
            with pytest.raises(SurfaceWorkPlanOccurrenceConflictError) as exc:
                await service.set_plan(
                    *i_ids, substrate=Substrate.GYPSUM_PLASTER,
                    planned_works=[Sel(price_item_id=i_item_id, occurrence_key=key)],
                )
            await db_session.rollback()
            errors.append(str(exc.value).replace(str(key), "<key>"))
        assert errors[0] == errors[1]  # indistinguishable responses
        assert await _state(db_session, sid) == before

    async def test_invented_key_rejected(self, db_session):
        user, project, room, surface, a, b, service, keys, sid, before = await self._prepared(db_session, 1301105)
        await self._assert_rejected_and_unchanged(
            db_session, SurfaceWorkPlanOccurrenceConflictError,
            lambda: _save(service, user, project, room, surface, [
                Sel(price_item_id=a.id, occurrence_key=keys[0]),
                Sel(price_item_id=b.id, occurrence_key=uuid.uuid4()),
            ]),
            sid, before,
        )

    async def test_stale_removed_key_rejected(self, db_session):
        user, project, room, surface, a, b, service, keys, sid, _ = await self._prepared(db_session, 1301106)
        # Another save removes occurrence B; an old draft still holds its key.
        await _save(service, user, project, room, surface, [Sel(price_item_id=a.id, occurrence_key=keys[0])])
        before = await _state(db_session, sid)
        await self._assert_rejected_and_unchanged(
            db_session, SurfaceWorkPlanOccurrenceConflictError,
            lambda: _save(service, user, project, room, surface, [
                Sel(price_item_id=a.id, occurrence_key=keys[0]),
                Sel(price_item_id=b.id, occurrence_key=keys[1]),
            ]),
            sid, before,
        )

    async def test_known_key_with_changed_price_item_rejected(self, db_session):
        user, project, room, surface, a, b, service, keys, sid, before = await self._prepared(db_session, 1301107)
        await self._assert_rejected_and_unchanged(
            db_session, SurfaceWorkPlanValidationError,
            lambda: _save(service, user, project, room, surface, [
                Sel(price_item_id=b.id, occurrence_key=keys[0]),
            ]),
            sid, before,
        )

    async def test_key_on_a_brand_new_plan_rejected(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301108)
        with pytest.raises(SurfaceWorkPlanOccurrenceConflictError):
            await _save(service, user, project, room, surface, [
                Sel(price_item_id=a.id, occurrence_key=uuid.uuid4()),
            ])
        await db_session.rollback()
        count = (await db_session.execute(select(func.count()).select_from(SurfaceWorkPlan))).scalar_one()
        assert count == 0


# ---------------------------------------------------------------------------
# wait_after_hours (D9)
# ---------------------------------------------------------------------------


class TestWaitAfterHours:
    @pytest.mark.parametrize("value", [0, -1, -24])
    def test_schema_rejects_zero_and_negative(self, value):
        with pytest.raises(ValidationError):
            Sel(price_item_id=uuid.uuid4(), wait_after_hours=value)

    def test_schema_accepts_null_and_positive(self):
        assert Sel(price_item_id=uuid.uuid4()).wait_after_hours is None
        assert Sel(price_item_id=uuid.uuid4(), wait_after_hours=48).wait_after_hours == 48

    async def test_db_rejects_negative(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301201)
        plan = await _save(service, user, project, room, surface, [])
        db_session.add(SurfacePlannedWork(
            work_plan_id=plan.id, price_item_id=a.id, position=0, wait_after_hours=-5,
        ))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_break_is_per_occurrence_and_not_on_price_item(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301202)
        plan = await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, wait_after_hours=24),
            Sel(price_item_id=a.id),
        ])
        assert [w.wait_after_hours for w in plan.planned_works] == [24, None]
        assert not hasattr(a, "wait_after_hours")

    async def test_estimate_ignores_break(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301203)
        await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        estimates = EstimateService(db_session)
        without = await estimates.generate_estimate(project.id, user.id)
        line_without = (without.lines[0].quantity, without.lines[0].unit_price, without.lines[0].amount)
        await _save(service, user, project, room, surface, [Sel(price_item_id=a.id, wait_after_hours=72)])
        await estimates.regenerate_draft(without.id, user.id, project.id)
        detail = await estimates.get_estimate_detail(project.id, without.id, user.id)
        line = detail.lines[0]
        assert (line.quantity, line.unit_price, line.amount) == line_without


# ---------------------------------------------------------------------------
# Apply-to-all (D13 H)
# ---------------------------------------------------------------------------


class TestApplyToAll:
    async def test_destinations_get_new_keys_breaks_and_coefficients_copied(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301301)
        _, opts = await _make_group_with_options(db_session, user.id, percentages=["0", "15"])
        await _make_surface(db_session, room.id, SurfaceType.WALL)
        await _make_surface(db_session, room.id, SurfaceType.WALL)
        source = await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, coefficient_option_ids=[opts[1].id], wait_after_hours=24),
            Sel(price_item_id=a.id),
        ])
        source_keys = [w.occurrence_key for w in source.planned_works]

        targets = await service.apply_to_room_walls(project.id, room.id, surface.id, user.id)

        assert len(targets) == 2
        all_target_keys = [w.occurrence_key for t in targets for w in t.planned_works]
        assert len(all_target_keys) == 4
        assert len(set(all_target_keys)) == 4
        assert set(all_target_keys).isdisjoint(source_keys)
        for target in targets:
            assert [w.wait_after_hours for w in target.planned_works] == [24, None]
            assert [[o.id for o in w.coefficient_options] for w in target.planned_works] == [[opts[1].id], []]
        # source untouched
        surface_id = surface.id
        await db_session.rollback()
        _, _, rows = await _state(db_session, surface_id)
        assert [r[1] for r in rows] == source_keys

    async def test_reapply_gives_fresh_keys_again(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301302)
        await _make_surface(db_session, room.id, SurfaceType.WALL)
        await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        first = await service.apply_to_room_walls(project.id, room.id, surface.id, user.id)
        first_key = first[0].planned_works[0].occurrence_key
        second = await service.apply_to_room_walls(project.id, room.id, surface.id, user.id)
        assert second[0].planned_works[0].occurrence_key != first_key


# ---------------------------------------------------------------------------
# Stage 11 append
# ---------------------------------------------------------------------------


class TestStage11Append:
    async def test_accepted_recommendation_gets_new_key_no_break_no_provenance(self, db_session):
        from tests.test_work_recommendation_accept import _plan_works, _setup_actionable

        user, project, room, wall, plan, item, rec, service = await _setup_actionable(
            db_session, 1301401, with_plan_codes=["EXISTING_A", "EXISTING_B"],
        )
        before = [(w.id, w.occurrence_key) for w in await _plan_works(db_session, plan.id)]

        await service.accept_recommendation(project.id, rec.id, user.id)

        works = await _plan_works(db_session, plan.id)
        assert [(w.id, w.occurrence_key) for w in works[:2]] == before
        appended = works[2]
        assert appended.occurrence_key not in {k for _, k in before}
        assert appended.wait_after_hours is None
        count = (
            await db_session.execute(select(func.count()).select_from(SurfaceWorkPlanTemplateApplication))
        ).scalar_one()
        assert count == 0

    async def test_direct_append_gets_key(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301402)
        plan = await _save(service, user, project, room, surface, [Sel(price_item_id=a.id)])
        locked = await service.lock_plan(surface.id)
        work = await service.append_one_planned_work_no_commit(locked, b)
        await db_session.commit()
        assert isinstance(work.occurrence_key, uuid.UUID)
        assert work.occurrence_key != plan.planned_works[0].occurrence_key


# ---------------------------------------------------------------------------
# HTTP contract (additive)
# ---------------------------------------------------------------------------


class TestHttp:
    async def _prepare(self, async_client, db_session):
        headers = auth_header(await get_token(async_client, VALID_USER))
        owner = (
            await db_session.execute(select(User).where(User.telegram_user_id == VALID_USER["id"]))
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        return headers, project, room, surface, item

    async def test_get_and_put_round_trip_key_and_break(self, async_client: AsyncClient, db_session):
        headers, project, room, surface, item = await self._prepare(async_client, db_session)
        url = _wp(project.id, room.id, surface.id)
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER",
            "planned_works": [{"price_item_id": str(item.id), "wait_after_hours": 24}],
        })
        assert resp.status_code == 200, resp.text
        work = resp.json()["planned_works"][0]
        key = work["occurrence_key"]
        assert work["wait_after_hours"] == 24
        got = (await async_client.get(url, headers=headers)).json()["planned_works"][0]
        assert got["occurrence_key"] == key
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER",
            "planned_works": [{"price_item_id": str(item.id), "occurrence_key": key, "wait_after_hours": 24}],
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["planned_works"][0]["occurrence_key"] == key

    async def test_unknown_key_is_409_and_duplicate_is_422(self, async_client: AsyncClient, db_session):
        headers, project, room, surface, item = await self._prepare(async_client, db_session)
        url = _wp(project.id, room.id, surface.id)
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "planned_works": [{"price_item_id": str(item.id)}],
        })
        key = resp.json()["planned_works"][0]["occurrence_key"]
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER",
            "planned_works": [{"price_item_id": str(item.id), "occurrence_key": str(uuid.uuid4())}],
        })
        assert resp.status_code == 409, resp.text
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER",
            "planned_works": [
                {"price_item_id": str(item.id), "occurrence_key": key},
                {"price_item_id": str(item.id), "occurrence_key": key},
            ],
        })
        assert resp.status_code == 422, resp.text
        resp = await async_client.put(url, headers=headers, json={
            "substrate": "GYPSUM_PLASTER",
            "planned_works": [{"price_item_id": str(item.id), "wait_after_hours": -1}],
        })
        assert resp.status_code == 422, resp.text
        got = (await async_client.get(url, headers=headers)).json()["planned_works"]
        assert [w["occurrence_key"] for w in got] == [key]

    async def test_legacy_price_item_ids_payload_still_works(self, async_client: AsyncClient, db_session):
        headers, project, room, surface, item = await self._prepare(async_client, db_session)
        resp = await async_client.put(_wp(project.id, room.id, surface.id), headers=headers, json={
            "substrate": "GYPSUM_PLASTER", "price_item_ids": [str(item.id), str(item.id)],
        })
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        assert len({w["occurrence_key"] for w in works}) == 2
        assert all(w["wait_after_hours"] is None for w in works)


# ---------------------------------------------------------------------------
# Stage 12 Estimate behaviour with key-preserving saves (unchanged semantics)
# ---------------------------------------------------------------------------


class TestEstimateUnchanged:
    async def test_override_survives_key_preserving_resave(self, db_session):
        user, project, room, surface, a, b, service = await _setup(db_session, 1301501)
        a.price = Decimal("20.00")
        await db_session.commit()
        _, opts = await _make_group_with_options(db_session, user.id, percentages=["0", "15", "25"])
        plan = await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, coefficient_option_ids=[opts[1].id]),
        ])
        key = plan.planned_works[0].occurrence_key
        estimates = EstimateService(db_session)
        estimate = await estimates.generate_estimate(project.id, user.id)
        line = estimate.lines[0]
        await estimates.patch_line(
            project.id, estimate.id, user.id, line.id,
            provided_fields={"unit_price"}, unit_price=Decimal("30.00"),
        )
        await _save(service, user, project, room, surface, [
            Sel(price_item_id=a.id, occurrence_key=key, coefficient_option_ids=[opts[2].id]),
        ])
        await estimates.regenerate_draft(estimate.id, user.id, project.id)
        after = (await estimates.get_estimate_detail(project.id, estimate.id, user.id)).lines[0]
        assert (after.id, after.unit_price, after.price_override) == (line.id, Decimal("30.00"), True)
        reset = await estimates.patch_line(
            project.id, estimate.id, user.id, after.id,
            provided_fields=set(), reset_price_override=True,
        )
        assert reset.unit_price == Decimal("25.00")
