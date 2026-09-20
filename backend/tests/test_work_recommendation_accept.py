"""Focused Stage 11C.1 tests: atomic recommendation acceptance into a
Surface work plan.

Covers success path (A-L), idempotency (M-P), duplicate occurrences (Q-S),
invalid state/target (T-Y), PriceItem resolution (Z-AK), and transaction/
rollback (AL) from the canonical Stage 11C.1 task spec, at the service
level. HTTP-level ownership/error-mapping tests live in
test_work_recommendation_api.py.

Concurrency limitation (AM/AN): this project's test harness runs against an
in-memory SQLite database via a single shared connection (StaticPool) with
no real row-level locking -- SQLite silently accepts `.with_for_update()`
as a no-op syntax pass-through and cannot enforce PostgreSQL locking
semantics. True concurrent-transaction proof of `SELECT ... FOR UPDATE`
is therefore NOT achievable as a *permanent pytest regression* in this
suite. What IS proven here, deterministically, as the CI-safe substitute:
(a) the accept command's *observable* idempotent outcome (repeat accept
never appends twice, regardless of ordering), and (b) that two *different*
recommendations sequentially accepted onto the same plan always receive
distinct, correctly ordered positions -- the correctness properties the
locks exist to guarantee under real concurrency.

Both concurrency scenarios (same-recommendation, and same-plan/different-
recommendation) were ADDITIONALLY verified as one-off manual scripts
against the REAL local PostgreSQL instance (used for this project's
Alembic migrations), with two genuinely concurrent asyncio tasks each on
their own AsyncSession/connection. In the same-plan case an artificial
delay was injected (via a temporary monkeypatch of
append_one_planned_work_no_commit, restored immediately after) to force
the second transaction's plan-lock acquisition to genuinely block rather
than relying on scheduling luck; the query log directly showed the
second request's queries only proceeding after the first committed. Both
runs passed: exactly one append for the same-recommendation race, and
exactly two distinct, correctly ordered positions with no IntegrityError
for the same-plan race. These are one-off verification scripts, not
permanent pytest regressions (they create/tear down real rows against a
live database and are not CI-appropriate) -- see the Stage 11C.1 final
verification report for the exact commands/output.
"""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import (
    PriceItemNotFoundError,
    SurfaceWorkPlanNotFoundError,
    SurfaceWorkPlanValidationError,
    WorkRecommendationStateError,
    WorkRecommendationTargetError,
)
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.models.checklist import ChecklistTemplate, Substrate
from app.models.inspection import Inspection, InspectionStatus
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationStatus,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)
from app.schemas.work_plan import OrderedPriceItemSelection


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(db, owner_id: uuid.UUID) -> Project:
    project = Project(
        owner_id=owner_id, name="Obiekt testowy", address="ul. Kwiatowa 1",
        city="Kraków", postal_code="30-001",
    )
    db.add(project)
    await db.commit()
    return project


async def _make_room(db, project_id: uuid.UUID) -> Room:
    room = Room(project_id=project_id, name="Salon")
    db.add(room)
    await db.commit()
    return room


async def _make_surface(
    db, room_id: uuid.UUID, surface_type: SurfaceType = SurfaceType.WALL
) -> Surface:
    surface = Surface(room_id=room_id, name="Ściana 1", surface_type=surface_type)
    db.add(surface)
    await db.commit()
    return surface


async def _make_template(db) -> ChecklistTemplate:
    template = ChecklistTemplate(
        code=f"TPL_CONCRETE_{uuid.uuid4().hex[:8]}", version=1, substrate=Substrate.CONCRETE,
        title_key="checklist.concrete.title",
    )
    db.add(template)
    await db.commit()
    return template


async def _make_inspection(db, room_id: uuid.UUID, template_id: uuid.UUID) -> Inspection:
    inspection = Inspection(
        room_id=room_id, template_id=template_id, substrate=Substrate.CONCRETE,
        status=InspectionStatus.COMPLETED, completed_at=datetime.now(timezone.utc),
    )
    db.add(inspection)
    await db.commit()
    return inspection


async def _make_price_item(
    db, owner_id: uuid.UUID, *, code: str, price: str | None = "35.00",
    is_archived: bool = False, category: PriceCategory = PriceCategory.SKIM_COAT,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id, code=code, category=category, unit=PriceUnit.M2,
        price=Decimal(price) if price is not None else None,
        price_scope=PriceScope.LABOR, is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_plan(
    db, project_id, room_id, surface_id, owner_id, *, existing_codes: list[str] | None = None,
) -> SurfaceWorkPlan:
    service = SurfaceWorkPlanService(db)
    selection = [
        OrderedPriceItemSelection(price_item_id=(
            await _make_price_item(db, owner_id, code=code)
        ).id)
        for code in (existing_codes or [])
    ]
    return await service.set_plan(
        project_id, room_id, surface_id, owner_id,
        substrate=Substrate.GYPSUM_PLASTER, quality_target=None,
        planned_works=selection,
    )


async def _make_recommendation(
    db, room: Room, inspection: Inspection, surface: Surface | None, *,
    recommended_work_code: str = "SKIM_Q3_M2",
    status: WorkRecommendationStatus = WorkRecommendationStatus.PENDING,
    is_active: bool = True,
    target_kind: WorkRecommendationTargetKind = WorkRecommendationTargetKind.WALL,
) -> WorkRecommendation:
    rec = WorkRecommendation(
        trigger_type=WorkRecommendationTriggerType.FINDING,
        trigger_code="old_paint_present",
        source_signature=uuid.uuid4().hex,
        inspection_id=inspection.id,
        room_id=room.id,
        surface_id=surface.id if surface is not None else None,
        target_kind=target_kind,
        recommended_work_code=recommended_work_code,
        status=status,
        is_active=is_active,
    )
    db.add(rec)
    await db.commit()
    return rec


async def _setup_actionable(db, telegram_id: int, *, with_plan_codes: list[str] | None = None):
    user = await _make_user(db, telegram_id)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    wall = await _make_surface(db, room.id, SurfaceType.WALL)
    template = await _make_template(db)
    inspection = await _make_inspection(db, room.id, template.id)
    plan = await _make_plan(
        db, project.id, room.id, wall.id, user.id, existing_codes=with_plan_codes,
    )
    item = await _make_price_item(db, user.id, code="SKIM_Q3_M2")
    rec = await _make_recommendation(db, room, inspection, wall, recommended_work_code="SKIM_Q3_M2")
    service = WorkRecommendationService(db)
    return user, project, room, wall, plan, item, rec, service


async def _plan_works(db, plan_id: uuid.UUID) -> list[SurfacePlannedWork]:
    stmt = (
        select(SurfacePlannedWork)
        .where(SurfacePlannedWork.work_plan_id == plan_id)
        .order_by(SurfacePlannedWork.position)
    )
    return list((await db.execute(stmt)).scalars().all())


class TestSuccessPath:
    async def test_active_pending_actionable_accepts(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311001)
        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.status == WorkRecommendationStatus.ACCEPTED

    async def test_inactive_resolved_pending_accepts(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311002)
        rec.is_active = False
        original_resolved_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rec.resolved_at = original_resolved_at
        await db_session.commit()

        accepted = await service.accept_recommendation(project.id, rec.id, user.id)

        assert accepted.status == WorkRecommendationStatus.ACCEPTED
        # Acceptance changes owner-decision state only -- is_active/resolved_at
        # are left exactly as they were (same value, not merely "still set").
        assert accepted.is_active is False
        # SQLite (test harness) does not round-trip tzinfo on DateTime
        # columns; compare naive values -- the real invariant under test is
        # "unchanged by acceptance", not timezone representation.
        assert accepted.resolved_at.replace(tzinfo=None) == original_resolved_at.replace(tzinfo=None)
        assert accepted.accepted_at is not None

    async def test_exactly_one_planned_work_appended(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(
            db_session, 311003, with_plan_codes=["EXISTING_A"],
        )
        await service.accept_recommendation(project.id, rec.id, user.id)
        works = await _plan_works(db_session, plan.id)
        assert len(works) == 2  # 1 pre-existing + 1 appended

    async def test_existing_works_preserved(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(
            db_session, 311004, with_plan_codes=["EXISTING_A", "EXISTING_B"],
        )
        before = await _plan_works(db_session, plan.id)
        before_ids = {w.id for w in before}

        await service.accept_recommendation(project.id, rec.id, user.id)

        after = await _plan_works(db_session, plan.id)
        after_ids = {w.id for w in after}
        assert before_ids.issubset(after_ids)

    async def test_substrate_and_quality_target_preserved(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311005)
        original_substrate = plan.substrate
        original_quality = plan.quality_target

        await service.accept_recommendation(project.id, rec.id, user.id)
        await db_session.refresh(plan)

        assert plan.substrate == original_substrate
        assert plan.quality_target == original_quality

    async def test_new_work_appended_at_max_plus_one(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(
            db_session, 311006, with_plan_codes=["EXISTING_A", "EXISTING_B"],
        )
        await service.accept_recommendation(project.id, rec.id, user.id)
        works = await _plan_works(db_session, plan.id)
        assert [w.position for w in works] == [0, 1, 2]
        assert works[-1].price_item_id == item.id

    async def test_no_renumbering_of_existing_works(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(
            db_session, 311007, with_plan_codes=["EXISTING_A", "EXISTING_B"],
        )
        before = await _plan_works(db_session, plan.id)
        before_positions = {w.id: w.position for w in before}

        await service.accept_recommendation(project.id, rec.id, user.id)

        after = await _plan_works(db_session, plan.id)
        for w in after:
            if w.id in before_positions:
                assert w.position == before_positions[w.id]

    async def test_accepted_at_is_set(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311008)
        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.accepted_at is not None

    async def test_resolved_price_item_id_snapshots_selected_item(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311009)
        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.resolved_price_item_id == item.id

    async def test_recommended_work_code_unchanged(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311010)
        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.recommended_work_code == "SKIM_Q3_M2"

    async def test_is_active_and_resolved_at_unchanged_by_acceptance(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311011)
        assert rec.is_active is True
        assert rec.resolved_at is None
        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.is_active is True
        assert accepted.resolved_at is None


class TestIdempotency:
    async def test_repeat_accept_of_accepted_returns_success(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311020)
        await service.accept_recommendation(project.id, rec.id, user.id)
        again = await service.accept_recommendation(project.id, rec.id, user.id)
        assert again.status == WorkRecommendationStatus.ACCEPTED

    async def test_repeat_accept_does_not_append_second_occurrence(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311021)
        await service.accept_recommendation(project.id, rec.id, user.id)
        await service.accept_recommendation(project.id, rec.id, user.id)
        works = await _plan_works(db_session, plan.id)
        assert len(works) == 1

    async def test_repeat_accept_with_different_manual_id_keeps_original_snapshot(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311022)
        other_item = await _make_price_item(db_session, user.id, code="OTHER_ITEM")
        first = await service.accept_recommendation(project.id, rec.id, user.id)
        second = await service.accept_recommendation(
            project.id, rec.id, user.id, price_item_id=other_item.id,
        )
        assert second.resolved_price_item_id == first.resolved_price_item_id == item.id
        works = await _plan_works(db_session, plan.id)
        assert len(works) == 1

    async def test_accepted_at_remains_original_value_on_repeat(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311023)
        first = await service.accept_recommendation(project.id, rec.id, user.id)
        first_accepted_at = first.accepted_at
        second = await service.accept_recommendation(project.id, rec.id, user.id)
        assert second.accepted_at == first_accepted_at

    async def test_repeat_accept_after_manual_fallback_keeps_original_manual_item(self, db_session):
        """recommended_work_code=A (item), first accept uses manual override
        B (a different code); a later retry with yet another manual item C
        must still return the original B snapshot, never append again, and
        never overwrite recommended_work_code (still A).
        """
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311024)
        item_b = await _make_price_item(db_session, user.id, code="ITEM_B")
        item_c = await _make_price_item(db_session, user.id, code="ITEM_C")

        first = await service.accept_recommendation(
            project.id, rec.id, user.id, price_item_id=item_b.id,
        )
        assert first.recommended_work_code == "SKIM_Q3_M2"
        assert first.resolved_price_item_id == item_b.id

        second = await service.accept_recommendation(
            project.id, rec.id, user.id, price_item_id=item_c.id,
        )
        assert second.recommended_work_code == "SKIM_Q3_M2"
        assert second.resolved_price_item_id == item_b.id  # NOT item_c

        works = await _plan_works(db_session, plan.id)
        assert len(works) == 1
        assert works[0].price_item_id == item_b.id


class TestDuplicateOccurrences:
    async def test_two_different_recommendations_may_accept_same_price_item(self, db_session):
        user, project, room, wall, plan, item, rec_a, service = await _setup_actionable(db_session, 311030)
        template = await _make_template(db_session)
        inspection_b = await _make_inspection(db_session, room.id, template.id)
        rec_b = await _make_recommendation(
            db_session, room, inspection_b, wall, recommended_work_code="SKIM_Q3_M2",
        )

        await service.accept_recommendation(project.id, rec_a.id, user.id)
        await service.accept_recommendation(project.id, rec_b.id, user.id)

        works = await _plan_works(db_session, plan.id)
        assert len(works) == 2
        assert works[0].price_item_id == works[1].price_item_id == item.id

    async def test_two_independent_occurrences_exist_with_distinct_ordered_positions(self, db_session):
        user, project, room, wall, plan, item, rec_a, service = await _setup_actionable(db_session, 311031)
        template = await _make_template(db_session)
        inspection_b = await _make_inspection(db_session, room.id, template.id)
        rec_b = await _make_recommendation(
            db_session, room, inspection_b, wall, recommended_work_code="SKIM_Q3_M2",
        )

        await service.accept_recommendation(project.id, rec_a.id, user.id)
        await service.accept_recommendation(project.id, rec_b.id, user.id)

        works = await _plan_works(db_session, plan.id)
        positions = [w.position for w in works]
        assert positions == sorted(positions)
        assert len(set(positions)) == 2
        ids = {w.id for w in works}
        assert len(ids) == 2


class TestInvalidStateOrTarget:
    async def test_dismissed_recommendation_rejected(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311040)
        rec.status = WorkRecommendationStatus.DISMISSED
        rec.dismissed_at = datetime.now(timezone.utc)
        await db_session.commit()

        with pytest.raises(WorkRecommendationStateError):
            await service.accept_recommendation(project.id, rec.id, user.id)

    async def test_room_recommendation_rejected_as_advisory_only(self, db_session):
        user = await _make_user(db_session, 311041)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(
            db_session, room, inspection, None, target_kind=WorkRecommendationTargetKind.ROOM,
        )
        service = WorkRecommendationService(db_session)

        with pytest.raises(WorkRecommendationTargetError):
            await service.accept_recommendation(project.id, rec.id, user.id)

    async def test_room_rejection_does_not_mutate_recommendation(self, db_session):
        user = await _make_user(db_session, 311042)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rec = await _make_recommendation(
            db_session, room, inspection, None, target_kind=WorkRecommendationTargetKind.ROOM,
        )
        service = WorkRecommendationService(db_session)

        with pytest.raises(WorkRecommendationTargetError):
            await service.accept_recommendation(project.id, rec.id, user.id)

        refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec.id))
        ).scalar_one()
        assert refreshed.status == WorkRecommendationStatus.PENDING
        assert refreshed.accepted_at is None
        assert refreshed.resolved_price_item_id is None

    async def test_missing_surface_workplan_fails_with_404_error(self, db_session):
        user = await _make_user(db_session, 311043)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_price_item(db_session, user.id, code="SKIM_Q3_M2")
        rec = await _make_recommendation(db_session, room, inspection, wall)
        service = WorkRecommendationService(db_session)

        with pytest.raises(SurfaceWorkPlanNotFoundError):
            await service.accept_recommendation(project.id, rec.id, user.id)

    async def test_missing_workplan_does_not_auto_create_one(self, db_session):
        user = await _make_user(db_session, 311044)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_price_item(db_session, user.id, code="SKIM_Q3_M2")
        rec = await _make_recommendation(db_session, room, inspection, wall)
        service = WorkRecommendationService(db_session)

        with pytest.raises(SurfaceWorkPlanNotFoundError):
            await service.accept_recommendation(project.id, rec.id, user.id)

        plan = (
            await db_session.execute(
                select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == wall.id)
            )
        ).scalar_one_or_none()
        assert plan is None


class TestPriceItemResolution:
    async def test_semantic_code_resolves_current_owner_priceitem(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311050)
        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.resolved_price_item_id == item.id

    async def test_missing_semantic_priceitem_rejected(self, db_session):
        user = await _make_user(db_session, 311051)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        plan = await _make_plan(db_session, project.id, room.id, wall.id, user.id)
        rec = await _make_recommendation(
            db_session, room, inspection, wall, recommended_work_code="NEVER_CREATED_CODE",
        )
        service = WorkRecommendationService(db_session)

        with pytest.raises(PriceItemNotFoundError):
            await service.accept_recommendation(project.id, rec.id, user.id)

    async def test_another_owners_same_code_priceitem_never_used(self, db_session):
        user = await _make_user(db_session, 311052)
        other_owner = await _make_user(db_session, 311053)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        plan = await _make_plan(db_session, project.id, room.id, wall.id, user.id)
        await _make_price_item(db_session, other_owner.id, code="SKIM_Q3_M2")
        rec = await _make_recommendation(db_session, room, inspection, wall, recommended_work_code="SKIM_Q3_M2")
        service = WorkRecommendationService(db_session)

        with pytest.raises(PriceItemNotFoundError):
            await service.accept_recommendation(project.id, rec.id, user.id)

    async def test_manual_fallback_priceitem_succeeds(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311054)
        fallback = await _make_price_item(db_session, user.id, code="MANUAL_FALLBACK")
        accepted = await service.accept_recommendation(
            project.id, rec.id, user.id, price_item_id=fallback.id,
        )
        assert accepted.resolved_price_item_id == fallback.id

    async def test_manual_fallback_may_have_different_code(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311055)
        fallback = await _make_price_item(db_session, user.id, code="DIFFERENT_CODE")
        accepted = await service.accept_recommendation(
            project.id, rec.id, user.id, price_item_id=fallback.id,
        )
        assert accepted.recommended_work_code == "SKIM_Q3_M2"
        assert accepted.resolved_price_item_id == fallback.id

    async def test_cross_owner_manual_fallback_rejected(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311056)
        other_owner = await _make_user(db_session, 311057)
        foreign_item = await _make_price_item(db_session, other_owner.id, code="FOREIGN")

        with pytest.raises(PriceItemNotFoundError):
            await service.accept_recommendation(
                project.id, rec.id, user.id, price_item_id=foreign_item.id,
            )

    async def test_archived_semantic_priceitem_rejected(self, db_session):
        user = await _make_user(db_session, 311058)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        plan = await _make_plan(db_session, project.id, room.id, wall.id, user.id)
        await _make_price_item(db_session, user.id, code="ARCHIVED_ITEM", is_archived=True)
        rec = await _make_recommendation(db_session, room, inspection, wall, recommended_work_code="ARCHIVED_ITEM")
        service = WorkRecommendationService(db_session)

        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.accept_recommendation(project.id, rec.id, user.id)

    async def test_archived_manual_fallback_rejected(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311059)
        archived_fallback = await _make_price_item(
            db_session, user.id, code="ARCHIVED_FALLBACK", is_archived=True,
        )
        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.accept_recommendation(
                project.id, rec.id, user.id, price_item_id=archived_fallback.id,
            )

    async def test_null_owner_price_accepted(self, db_session):
        user = await _make_user(db_session, 311060)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        plan = await _make_plan(db_session, project.id, room.id, wall.id, user.id)
        item = await _make_price_item(db_session, user.id, code="NULL_PRICE", price=None)
        rec = await _make_recommendation(db_session, room, inspection, wall, recommended_work_code="NULL_PRICE")
        service = WorkRecommendationService(db_session)

        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.status == WorkRecommendationStatus.ACCEPTED
        assert accepted.resolved_price_item_id == item.id

    async def test_explicit_zero_price_accepted(self, db_session):
        user = await _make_user(db_session, 311061)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        plan = await _make_plan(db_session, project.id, room.id, wall.id, user.id)
        item = await _make_price_item(db_session, user.id, code="ZERO_PRICE", price="0.00")
        rec = await _make_recommendation(db_session, room, inspection, wall, recommended_work_code="ZERO_PRICE")
        service = WorkRecommendationService(db_session)

        accepted = await service.accept_recommendation(project.id, rec.id, user.id)
        assert accepted.status == WorkRecommendationStatus.ACCEPTED
        assert accepted.resolved_price_item_id == item.id

    async def test_reveal_category_rejected_by_stage11_accept_path(self, db_session):
        user = await _make_user(db_session, 311062)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        plan = await _make_plan(db_session, project.id, room.id, wall.id, user.id)
        await _make_price_item(
            db_session, user.id, code="REVEAL_ITEM", category=PriceCategory.REVEAL,
        )
        rec = await _make_recommendation(db_session, room, inspection, wall, recommended_work_code="REVEAL_ITEM")
        service = WorkRecommendationService(db_session)

        with pytest.raises(SurfaceWorkPlanValidationError):
            await service.accept_recommendation(project.id, rec.id, user.id)

    async def test_stage10_manual_workplan_reveal_item_still_allowed_unchanged(self, db_session):
        """The Stage 11 REVEAL guard lives only in the recommendation accept
        path -- the existing, deliberately permissive Stage 10 manual Work
        Plan picker (set_plan/replace_planned_works) must remain unchanged
        and must NOT reject a REVEAL-category item.
        """
        user = await _make_user(db_session, 311063)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        reveal_item = await _make_price_item(
            db_session, user.id, code="MANUAL_REVEAL", category=PriceCategory.REVEAL,
        )
        service = SurfaceWorkPlanService(db_session)

        plan = await service.set_plan(
            project.id, room.id, wall.id, user.id,
            substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[OrderedPriceItemSelection(price_item_id=reveal_item.id)],
        )

        assert plan.planned_works[0].price_item_id == reveal_item.id


class TestTransactionRollback:
    async def test_forced_failure_before_commit_rolls_back_everything(self, db_session, monkeypatch):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311070)
        rec_id = rec.id
        plan_id = plan.id

        async def failing_commit():
            raise RuntimeError("simulated failure before commit")

        monkeypatch.setattr(db_session, "commit", failing_commit)

        with pytest.raises(RuntimeError):
            await service.accept_recommendation(project.id, rec_id, user.id)

        monkeypatch.undo()
        await db_session.rollback()

        refreshed_rec = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec_id))
        ).scalar_one()
        assert refreshed_rec.status == WorkRecommendationStatus.PENDING
        assert refreshed_rec.resolved_price_item_id is None
        assert refreshed_rec.accepted_at is None

        works = await _plan_works(db_session, plan_id)
        assert len(works) == 0


class TestConcurrencyObservableOutcome:
    """Sequential proof of the *outcome* the row locks protect -- see the
    module docstring for why true concurrent-transaction proof is not
    achievable against this project's SQLite test harness.
    """

    async def test_sequential_repeat_accept_same_recommendation_never_appends_twice(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311080)
        for _ in range(5):
            await service.accept_recommendation(project.id, rec.id, user.id)
        works = await _plan_works(db_session, plan.id)
        assert len(works) == 1

    async def test_sequential_accepts_on_same_plan_never_collide_on_position(self, db_session):
        user, project, room, wall, plan, item, rec_a, service = await _setup_actionable(db_session, 311081)
        template = await _make_template(db_session)
        recs = [rec_a]
        for i in range(4):
            inspection = await _make_inspection(db_session, room.id, template.id)
            recs.append(
                await _make_recommendation(
                    db_session, room, inspection, wall, recommended_work_code="SKIM_Q3_M2",
                )
            )
        for rec in recs:
            await service.accept_recommendation(project.id, rec.id, user.id)

        works = await _plan_works(db_session, plan.id)
        positions = [w.position for w in works]
        assert positions == list(range(len(recs)))
        assert len(set(positions)) == len(recs)


class TestNoEstimateMutation:
    async def test_accept_does_not_touch_estimate_tables(self, db_session):
        from app.models.estimate import Estimate, EstimateLine

        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 311090)
        estimate_count_before = (
            await db_session.execute(select(func.count()).select_from(Estimate))
        ).scalar_one()
        line_count_before = (
            await db_session.execute(select(func.count()).select_from(EstimateLine))
        ).scalar_one()

        await service.accept_recommendation(project.id, rec.id, user.id)

        estimate_count_after = (
            await db_session.execute(select(func.count()).select_from(Estimate))
        ).scalar_one()
        line_count_after = (
            await db_session.execute(select(func.count()).select_from(EstimateLine))
        ).scalar_one()
        assert estimate_count_after == estimate_count_before == 0
        assert line_count_after == line_count_before == 0
