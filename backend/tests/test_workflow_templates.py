"""Stage 13B — workflow template persistence and template-application
provenance (D1, D2, D6, D7, D8, D9, D11).

Persistence/domain only: no API, no apply behaviour, no default recipes.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import (
    PriceItemNotFoundError,
    WorkflowTemplateNotFoundError,
    WorkflowTemplateValidationError,
)
from app.domain.services.workflow_template_service import (
    WorkflowTemplateService,
    WorkflowTemplateStepSpec as Step,
)
from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceCategory, PriceItem
from app.models.surface import SurfaceType
from app.models.work_plan import SurfaceWorkPlan
from app.models.workflow_template import (
    SurfaceWorkPlanTemplateApplication,
    TemplateApplicationMode,
    WorkflowTemplate,
    WorkflowTemplateStep,
)
from tests.test_planned_work_coefficient_assignments import (
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
    _make_user,
)


async def _owner_with_items(db, telegram_id: int):
    user = await _make_user(db, telegram_id)
    prime = await _make_price_item(db, user.id, code=f"PRIM_{telegram_id}", category=PriceCategory.PREPARATION)
    skim = await _make_price_item(db, user.id, code=f"SKIM_{telegram_id}", category=PriceCategory.SKIM_COAT)
    return user, prime, skim, WorkflowTemplateService(db)


class TestTemplatePersistence:
    async def test_owner_scoped_template_with_ordered_steps(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302001)
        template = await service.create_template(
            user.id,
            display_name="  Tynk gipsowy → S2  ",
            description="Przykład",
            applies_to_substrates=[Substrate.GYPSUM_PLASTER, Substrate.GYPSUM_PLASTER],
            applies_to_quality=[QualityLevel.S2],
            applies_to_surface_types=[SurfaceType.WALL, SurfaceType.CEILING],
            steps=[
                Step(price_item_id=prime.id, wait_after_hours=4, note=" grunt głęboko penetrujący "),
                Step(price_item_id=skim.id, is_optional=True, wait_after_hours=24),
                Step(price_item_id=prime.id),  # the same item twice is allowed
            ],
        )
        assert template.owner_id == user.id
        assert template.code.startswith("CUSTOM_")
        assert template.display_name == "Tynk gipsowy → S2"
        assert template.applies_to_substrates == ["GYPSUM_PLASTER"]
        assert template.applies_to_quality == ["S2"]
        assert template.applies_to_surface_types == ["WALL", "CEILING"]
        assert template.is_archived is False
        assert [(s.position, s.price_item_id, s.is_optional, s.note, s.wait_after_hours) for s in template.steps] == [
            (0, prime.id, False, "grunt głęboko penetrujący", 4),
            (1, skim.id, True, None, 24),
            (2, prime.id, False, None, None),
        ]
        assert template.steps[0].price_item.code == prime.code

    async def test_empty_filters_mean_any(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302002)
        template = await service.create_template(user.id, display_name="Dowolna", applies_to_quality=[])
        assert (template.applies_to_substrates, template.applies_to_quality, template.applies_to_surface_types) == (None, None, None)

    async def test_other_owner_cannot_read_or_use_items(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302003)
        other, other_prime, _, _ = await _owner_with_items(db_session, 1302004)
        template = await service.create_template(user.id, display_name="Moja")
        with pytest.raises(WorkflowTemplateNotFoundError):
            await service.get_owned_template(other.id, template.id)
        with pytest.raises(PriceItemNotFoundError):
            await service.replace_steps(user.id, template.id, [Step(price_item_id=other_prime.id)])

    async def test_code_unique_per_owner(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302005)
        db_session.add_all([
            WorkflowTemplate(owner_id=user.id, code="SAME", display_name="A"),
            WorkflowTemplate(owner_id=user.id, code="SAME", display_name="B"),
        ])
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_display_name_required(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302006)
        with pytest.raises(WorkflowTemplateValidationError):
            await service.create_template(user.id, display_name="   ")

    async def test_replace_steps_renumbers_and_is_atomic(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302007)
        template = await service.create_template(
            user.id, display_name="T", steps=[Step(price_item_id=prime.id), Step(price_item_id=skim.id)],
        )
        template = await service.replace_steps(user.id, template.id, [
            Step(price_item_id=skim.id, wait_after_hours=12), Step(price_item_id=prime.id),
        ])
        assert [(s.position, s.price_item_id, s.wait_after_hours) for s in template.steps] == [
            (0, skim.id, 12), (1, prime.id, None),
        ]
        template_id, owner_id, prime_id, skim_id = template.id, user.id, prime.id, skim.id
        with pytest.raises(WorkflowTemplateValidationError):
            await service.replace_steps(owner_id, template_id, [Step(price_item_id=prime_id, wait_after_hours=-1)])
        await db_session.rollback()
        template = await service.get_owned_template(owner_id, template_id)
        assert [s.price_item_id for s in template.steps] == [skim_id, prime_id]

    async def test_archive_and_restore(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302008)
        template = await service.create_template(user.id, display_name="T", steps=[Step(price_item_id=prime.id)])
        assert (await service.archive_template(user.id, template.id)).is_archived is True
        assert (await service.archive_template(user.id, template.id)).is_archived is True  # idempotent
        restored = await service.restore_template(user.id, template.id)
        assert restored.is_archived is False
        assert len((await service.get_owned_template(user.id, template.id)).steps) == 1

    async def test_used_price_item_cannot_be_hard_deleted(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302009)
        await service.create_template(user.id, display_name="T", steps=[Step(price_item_id=prime.id)])
        await db_session.delete(prime)
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


class TestStepRules:
    @pytest.mark.parametrize("value", [0, -1, -48])
    async def test_zero_and_negative_wait_rejected(self, db_session, value):
        user, prime, skim, service = await _owner_with_items(db_session, 1302101 + abs(value))
        with pytest.raises(WorkflowTemplateValidationError):
            await service.create_template(user.id, display_name="T", steps=[Step(price_item_id=prime.id, wait_after_hours=value)])

    async def test_db_check_rejects_negative_wait(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302110)
        template = await service.create_template(user.id, display_name="T")
        db_session.add(WorkflowTemplateStep(template_id=template.id, position=0, price_item_id=prime.id, wait_after_hours=-3))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_reveal_price_item_rejected(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302111)
        reveal = await _make_price_item(db_session, user.id, code="REV", category=PriceCategory.REVEAL)
        with pytest.raises(WorkflowTemplateValidationError):
            await service.create_template(user.id, display_name="T", steps=[Step(price_item_id=reveal.id)])
        await db_session.rollback()
        count = (await db_session.execute(select(func.count()).select_from(WorkflowTemplate))).scalar_one()
        assert count == 0

    async def test_archived_item_cannot_be_added_but_existing_step_kept(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302112)
        template = await service.create_template(user.id, display_name="T", steps=[Step(price_item_id=prime.id)])
        prime.is_archived = True
        await db_session.commit()
        # keeping the existing step is allowed
        template = await service.replace_steps(user.id, template.id, [Step(price_item_id=prime.id), Step(price_item_id=skim.id)])
        assert len(template.steps) == 2
        # increasing its count is not
        with pytest.raises(WorkflowTemplateValidationError):
            await service.replace_steps(user.id, template.id, [Step(price_item_id=prime.id)] * 2)

    async def test_step_carries_no_coefficients_and_price_item_has_no_break(self, db_session):
        assert not hasattr(WorkflowTemplateStep, "coefficient_assignments")
        assert "wait_after_hours" not in PriceItem.__table__.columns
        assert "wait_after_hours" in WorkflowTemplateStep.__table__.columns


class TestProvenance:
    async def _plan(self, db, owner_id):
        project = await _make_project(db, owner_id)
        room = await _make_room(db, project.id)
        surface = await _make_surface(db, room.id)
        plan = SurfaceWorkPlan(surface_id=surface.id, substrate=Substrate.GYPSUM_PLASTER)
        db.add(plan)
        await db.commit()
        return plan

    async def test_history_attached_to_plan_and_snapshot_survives_template_changes(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302201)
        template = await service.create_template(user.id, display_name="Oryginał", steps=[Step(price_item_id=prime.id)])
        plan = await self._plan(db_session, user.id)
        for mode, n in ((TemplateApplicationMode.APPEND, 1), (TemplateApplicationMode.REPLACE, 1)):
            db_session.add(SurfaceWorkPlanTemplateApplication(
                work_plan_id=plan.id, template_id=template.id, template_code=template.code,
                template_name=template.display_name, mode=mode, steps_applied=n,
                applied_at=datetime.now(timezone.utc),
            ))
        await db_session.commit()

        await service.update_template(user.id, template.id, display_name="Zmieniona")
        await service.replace_steps(user.id, template.id, [Step(price_item_id=skim.id)] * 3)
        await service.archive_template(user.id, template.id)

        rows = (
            await db_session.execute(
                select(SurfaceWorkPlanTemplateApplication)
                .where(SurfaceWorkPlanTemplateApplication.work_plan_id == plan.id)
                .order_by(SurfaceWorkPlanTemplateApplication.applied_at)
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
        assert [(r.template_id, r.template_name, r.mode, r.steps_applied) for r in rows] == [
            (template.id, "Oryginał", TemplateApplicationMode.APPEND, 1),
            (template.id, "Oryginał", TemplateApplicationMode.REPLACE, 1),
        ]

    async def test_deleted_template_clears_link_but_keeps_snapshot(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302202)
        template = await service.create_template(user.id, display_name="Do usunięcia")
        code = template.code
        plan = await self._plan(db_session, user.id)
        record = SurfaceWorkPlanTemplateApplication(
            work_plan_id=plan.id, template_id=template.id, template_code=code,
            template_name="Do usunięcia", mode=TemplateApplicationMode.APPEND, steps_applied=0,
        )
        db_session.add(record)
        await db_session.commit()
        record_id = record.id

        await db_session.delete(template)
        await db_session.commit()

        kept = (
            await db_session.execute(
                select(SurfaceWorkPlanTemplateApplication)
                .where(SurfaceWorkPlanTemplateApplication.id == record_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert (kept.template_id, kept.template_code, kept.template_name) == (None, code, "Do usunięcia")

    async def test_plan_deletion_cascades_history(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302203)
        plan = await self._plan(db_session, user.id)
        db_session.add(SurfaceWorkPlanTemplateApplication(
            work_plan_id=plan.id, template_code="X", template_name="X",
            mode=TemplateApplicationMode.APPEND, steps_applied=0,
        ))
        await db_session.commit()
        await db_session.delete(plan)
        await db_session.commit()
        count = (
            await db_session.execute(select(func.count()).select_from(SurfaceWorkPlanTemplateApplication))
        ).scalar_one()
        assert count == 0

    async def test_negative_steps_applied_rejected(self, db_session):
        user, prime, skim, service = await _owner_with_items(db_session, 1302204)
        plan = await self._plan(db_session, user.id)
        db_session.add(SurfaceWorkPlanTemplateApplication(
            work_plan_id=plan.id, template_code="X", template_name="X",
            mode=TemplateApplicationMode.APPEND, steps_applied=-1,
        ))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_plan_save_does_not_touch_history(self, db_session):
        from app.domain.services.work_plan_service import SurfaceWorkPlanService
        from app.schemas.work_plan import OrderedPriceItemSelection

        user, prime, skim, service = await _owner_with_items(db_session, 1302205)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        plans = SurfaceWorkPlanService(db_session)
        plan = await plans.set_plan(
            project.id, room.id, surface.id, user.id, substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[OrderedPriceItemSelection(price_item_id=prime.id)],
        )
        db_session.add(SurfaceWorkPlanTemplateApplication(
            work_plan_id=plan.id, template_code="X", template_name="X",
            mode=TemplateApplicationMode.REPLACE, steps_applied=1,
        ))
        await db_session.commit()
        await plans.set_plan(
            project.id, room.id, surface.id, user.id, substrate=Substrate.GYPSUM_PLASTER, planned_works=[],
        )
        count = (
            await db_session.execute(select(func.count()).select_from(SurfaceWorkPlanTemplateApplication))
        ).scalar_one()
        assert count == 1
