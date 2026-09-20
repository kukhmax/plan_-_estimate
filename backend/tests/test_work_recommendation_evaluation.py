"""Focused Stage 11B.2 tests: recommendation materialization + lifecycle
reconciliation via WorkRecommendationService.evaluate_recommendations.

Covers materialization (A-G), lifecycle reconciliation (H-R), and target
derivation (AF-AJ) from the canonical Stage 11B.2 task spec. Command-API
(dismiss/reconsider/list/ownership/PriceItem read-resolution) tests live in
test_work_recommendation_api.py.

No recommendation acceptance into SurfaceWorkPlan exists yet (Stage 11C).
"""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from app.domain.rules.risk_rules import compute_source_signature
from app.domain.services.canonical_planes import ensure_canonical_plane_surfaces
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.models.area_segment import AreaPlane
from app.models.checklist import ChecklistTemplate, Substrate
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.risk import Risk, RiskSeverity
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationRule,
    WorkRecommendationStatus,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)


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
        code="TPL_CONCRETE", version=1, substrate=Substrate.CONCRETE,
        title_key="checklist.concrete.title",
    )
    db.add(template)
    await db.commit()
    return template


async def _make_inspection(
    db, room_id: uuid.UUID, template_id: uuid.UUID, *,
    surface_id: uuid.UUID | None = None,
    plane: AreaPlane | None = None,
    status: InspectionStatus = InspectionStatus.COMPLETED,
) -> Inspection:
    inspection = Inspection(
        room_id=room_id, surface_id=surface_id, plane=plane, template_id=template_id,
        substrate=Substrate.CONCRETE, status=status,
        completed_at=datetime.now(timezone.utc) if status is InspectionStatus.COMPLETED else None,
    )
    db.add(inspection)
    await db.commit()
    return inspection


async def _make_finding(
    db, inspection_id: uuid.UUID, *, finding_key: str = "old_paint_present",
    is_active: bool = True,
) -> InspectionFinding:
    finding = InspectionFinding(
        inspection_id=inspection_id, finding_key=finding_key, is_active=is_active,
    )
    db.add(finding)
    await db.commit()
    return finding


async def _make_risk(
    db, room_id: uuid.UUID, inspection_id: uuid.UUID, *,
    rule_code: str = "SUBSTRATE_POOR", source_signature: str, is_active: bool = True,
) -> Risk:
    risk = Risk(
        room_id=room_id, inspection_id=inspection_id, risk_code=rule_code,
        rule_code=rule_code, rule_version=1, severity=RiskSeverity.HIGH,
        title_key="risk.x.title", explanation_key="risk.x.explanation",
        consequence_key="risk.x.consequence", mitigation_key="risk.x.mitigation",
        communication_key="risk.x.communication", source_signature=source_signature,
        is_active=is_active,
    )
    db.add(risk)
    await db.commit()
    return risk


async def _make_rule(
    db, *, trigger_type: WorkRecommendationTriggerType, trigger_code: str,
    recommended_work_code: str = "SKIM_Q3_M2",
) -> WorkRecommendationRule:
    rule = WorkRecommendationRule(
        trigger_type=trigger_type, trigger_code=trigger_code,
        recommended_work_code=recommended_work_code,
    )
    db.add(rule)
    await db.commit()
    return rule


async def _room_count(db) -> int:
    from sqlalchemy import func, select
    return (
        await db.execute(select(func.count()).select_from(WorkRecommendation))
    ).scalar_one()


class TestA_RiskMaterialization:
    async def test_risk_trigger_materializes_recommendation(self, db_session):
        user = await _make_user(db_session, 211001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id, surface_id=wall.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="cracks_present")
        signature = compute_source_signature([finding.id])
        await _make_risk(db_session, room.id, inspection.id, rule_code="SUBSTRATE_POOR", source_signature=signature)
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="SUBSTRATE_POOR", recommended_work_code="PRIMER_M2",
        )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 1
        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert rec.trigger_type == WorkRecommendationTriggerType.RISK_RULE
        assert rec.trigger_code == "SUBSTRATE_POOR"
        assert rec.recommended_work_code == "PRIMER_M2"
        assert rec.surface_id == wall.id
        assert rec.target_kind == WorkRecommendationTargetKind.WALL
        assert rec.status == WorkRecommendationStatus.PENDING
        assert rec.is_active is True
        assert rec.risk_id is not None
        assert rec.finding_id is None


class TestB_FindingMaterialization:
    async def test_finding_trigger_materializes_recommendation(self, db_session):
        user = await _make_user(db_session, 211002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present", recommended_work_code="MECHANICAL_SCRATCH",
        )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 1
        rec = result.recommendations[0]
        assert rec.trigger_type == WorkRecommendationTriggerType.FINDING
        assert rec.finding_id == finding.id
        assert rec.risk_id is None
        assert rec.target_kind == WorkRecommendationTargetKind.ROOM
        assert rec.surface_id is None


class TestC_MultipleWorksPerTrigger:
    async def test_one_trigger_produces_three_independent_rows(self, db_session):
        user = await _make_user(db_session, 211003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="substrate_poor")
        for code in ("PRIMER_M2", "LEVELING_M2", "SKIM_Q3_M2"):
            await _make_rule(
                db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
                trigger_code="substrate_poor", recommended_work_code=code,
            )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 3
        codes = {r.recommended_work_code for r in result.recommendations}
        assert codes == {"PRIMER_M2", "LEVELING_M2", "SKIM_Q3_M2"}


class TestD_RepeatUnchanged:
    async def test_repeat_evaluate_creates_no_duplicates(self, db_session):
        user = await _make_user(db_session, 211004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert first.created == 1

        second = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert second.created == 0
        assert second.reactivated == 0
        assert second.unchanged == 1
        assert await _room_count(db_session) == 1


class TestE_TriggerTypeCollision:
    async def test_risk_and_finding_same_code_signature_work_do_not_collide(self, db_session):
        user = await _make_user(db_session, 211005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="COLLIDING_CODE")
        signature = compute_source_signature([finding.id])
        await _make_risk(
            db_session, room.id, inspection.id, rule_code="COLLIDING_CODE",
            source_signature=signature,
        )
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="COLLIDING_CODE", recommended_work_code="SAME_WORK",
        )
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="COLLIDING_CODE", recommended_work_code="SAME_WORK",
        )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 2
        trigger_types = {r.trigger_type for r in result.recommendations}
        assert trigger_types == {
            WorkRecommendationTriggerType.RISK_RULE,
            WorkRecommendationTriggerType.FINDING,
        }


class TestFG_MultipleInspectionsAndSignatures:
    async def test_two_inspections_same_trigger_key_do_not_collide(self, db_session):
        user = await _make_user(db_session, 211006)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall1 = await _make_surface(db_session, room.id, SurfaceType.WALL)
        wall2 = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection1 = await _make_inspection(db_session, room.id, template.id, surface_id=wall1.id)
        inspection2 = await _make_inspection(db_session, room.id, template.id, surface_id=wall2.id)
        await _make_finding(db_session, inspection1.id, finding_key="old_paint_present")
        await _make_finding(db_session, inspection2.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present", recommended_work_code="SKIM_Q3_M2",
        )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 2
        surface_ids = {r.surface_id for r in result.recommendations}
        assert surface_ids == {wall1.id, wall2.id}
        inspection_ids = {r.inspection_id for r in result.recommendations}
        assert inspection_ids == {inspection1.id, inspection2.id}
        # Same recommended_work_code, independent source signatures.
        signatures = {r.source_signature for r in result.recommendations}
        assert len(signatures) == 2


class TestH_PendingStable:
    async def test_active_pending_row_is_untouched_on_repeat_evaluate(self, db_session):
        user = await _make_user(db_session, 211007)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec_id = first.recommendations[0].id
        updated_at_before = first.recommendations[0].updated_at

        second = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert second.recommendations[0].id == rec_id
        assert second.recommendations[0].status == WorkRecommendationStatus.PENDING
        assert second.recommendations[0].updated_at == updated_at_before


class TestI_DismissedSticky:
    async def test_dismissed_remains_dismissed_on_repeat_evaluate(self, db_session):
        user = await _make_user(db_session, 211008)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec = first.recommendations[0]
        await service.dismiss(project.id, rec.id, user.id)

        second = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert second.recommendations[0].id == rec.id
        assert second.recommendations[0].status == WorkRecommendationStatus.DISMISSED


class TestJ_AcceptedTerminal:
    async def test_accepted_remains_accepted_on_repeat_evaluate(self, db_session):
        user = await _make_user(db_session, 211009)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec = first.recommendations[0]
        # 11C accept command does not exist yet -- arrange persisted state directly.
        rec.status = WorkRecommendationStatus.ACCEPTED
        rec.accepted_at = datetime.now(timezone.utc)
        await db_session.commit()

        second = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert second.recommendations[0].id == rec.id
        assert second.recommendations[0].status == WorkRecommendationStatus.ACCEPTED


class TestKLMN_SourceDisappears:
    async def _setup(self, db_session, status: WorkRecommendationStatus):
        user = await _make_user(db_session, 211010)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec = first.recommendations[0]
        if status is WorkRecommendationStatus.DISMISSED:
            await service.dismiss(project.id, rec.id, user.id)
        elif status is WorkRecommendationStatus.ACCEPTED:
            rec.status = WorkRecommendationStatus.ACCEPTED
            rec.accepted_at = datetime.now(timezone.utc)
            await db_session.commit()
        return user, project, room, finding, service, rec

    async def test_source_disappears_resolves_pending(self, db_session):
        user, project, room, finding, service, rec = await self._setup(
            db_session, WorkRecommendationStatus.PENDING
        )
        finding.is_active = False
        await db_session.commit()

        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.resolved == 1
        from sqlalchemy import select
        refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec.id))
        ).scalar_one()
        assert refreshed.is_active is False
        assert refreshed.resolved_at is not None
        assert refreshed.status == WorkRecommendationStatus.PENDING

    async def test_source_disappears_resolves_dismissed(self, db_session):
        user, project, room, finding, service, rec = await self._setup(
            db_session, WorkRecommendationStatus.DISMISSED
        )
        finding.is_active = False
        await db_session.commit()

        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.resolved == 1
        from sqlalchemy import select
        refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec.id))
        ).scalar_one()
        assert refreshed.is_active is False
        assert refreshed.status == WorkRecommendationStatus.DISMISSED

    async def test_source_disappears_resolves_accepted(self, db_session):
        user, project, room, finding, service, rec = await self._setup(
            db_session, WorkRecommendationStatus.ACCEPTED
        )
        finding.is_active = False
        await db_session.commit()

        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.resolved == 1
        from sqlalchemy import select
        refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec.id))
        ).scalar_one()
        assert refreshed.is_active is False
        assert refreshed.status == WorkRecommendationStatus.ACCEPTED


class TestOPQ_Reactivation:
    async def test_reactivated_pending_preserves_status(self, db_session):
        user = await _make_user(db_session, 211020)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec_id = first.recommendations[0].id

        finding.is_active = False
        await db_session.commit()
        await service.evaluate_recommendations(project.id, room.id, user.id)

        finding.is_active = True
        await db_session.commit()
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.reactivated == 1
        rec = result.recommendations[0]
        assert rec.id == rec_id
        assert rec.is_active is True
        assert rec.resolved_at is None
        assert rec.status == WorkRecommendationStatus.PENDING

    async def test_reactivated_dismissed_remains_dismissed(self, db_session):
        user = await _make_user(db_session, 211021)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec_id = first.recommendations[0].id
        await service.dismiss(project.id, rec_id, user.id)

        finding.is_active = False
        await db_session.commit()
        await service.evaluate_recommendations(project.id, room.id, user.id)
        finding.is_active = True
        await db_session.commit()
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.reactivated == 1
        rec = result.recommendations[0]
        assert rec.id == rec_id
        assert rec.status == WorkRecommendationStatus.DISMISSED

    async def test_reactivated_accepted_remains_accepted(self, db_session):
        user = await _make_user(db_session, 211022)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec = first.recommendations[0]
        rec.status = WorkRecommendationStatus.ACCEPTED
        rec.accepted_at = datetime.now(timezone.utc)
        await db_session.commit()

        finding.is_active = False
        await db_session.commit()
        await service.evaluate_recommendations(project.id, room.id, user.id)
        finding.is_active = True
        await db_session.commit()
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.reactivated == 1
        assert result.recommendations[0].id == rec.id
        assert result.recommendations[0].status == WorkRecommendationStatus.ACCEPTED


class TestR_NewSignatureIsNewRow:
    async def test_new_source_signature_creates_new_row_old_remains(self, db_session):
        user = await _make_user(db_session, 211023)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        old_finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        old_rec_id = first.recommendations[0].id

        # Evidence changed: old finding superseded by a new one (new UUID ->
        # new source_signature -> a new recommendation identity).
        old_finding.is_active = False
        new_finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present_v2")
        # Reuse the same trigger_code by pointing a second rule at the new key
        # to keep this test isolated to the "new signature" mechanic itself:
        # a fresh finding always yields a fresh, unrelated signature even for
        # the *same* finding_key. Demonstrate that directly too:
        new_same_key_finding = InspectionFinding(
            inspection_id=inspection.id, finding_key="old_paint_present", is_active=True,
        )
        db_session.add(new_same_key_finding)
        await db_session.commit()

        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 1
        assert result.resolved == 1
        new_rec = result.recommendations[0]
        assert new_rec.id != old_rec_id
        assert new_rec.finding_id == new_same_key_finding.id

        from sqlalchemy import select
        old_rec = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == old_rec_id))
        ).scalar_one()
        assert old_rec is not None
        assert old_rec.is_active is False


class TestAFGH_TargetDerivation:
    async def test_wall_target_uses_inspection_surface(self, db_session):
        user = await _make_user(db_session, 211030)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id, surface_id=wall.id)
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.recommendations[0].target_kind == WorkRecommendationTargetKind.WALL
        assert result.recommendations[0].surface_id == wall.id

    async def test_floor_target_uses_canonical_floor_surface(self, db_session):
        user = await _make_user(db_session, 211031)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        floor, _ceiling = await ensure_canonical_plane_surfaces(db_session, room.id)
        await db_session.commit()
        template = await _make_template(db_session)
        inspection = await _make_inspection(
            db_session, room.id, template.id, plane=AreaPlane.FLOOR
        )
        await _make_finding(db_session, inspection.id, finding_key="floor_uneven")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="floor_uneven",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.recommendations[0].target_kind == WorkRecommendationTargetKind.FLOOR
        assert result.recommendations[0].surface_id == floor.id

    async def test_ceiling_target_uses_canonical_ceiling_surface(self, db_session):
        user = await _make_user(db_session, 211032)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        _floor, ceiling = await ensure_canonical_plane_surfaces(db_session, room.id)
        await db_session.commit()
        template = await _make_template(db_session)
        inspection = await _make_inspection(
            db_session, room.id, template.id, plane=AreaPlane.CEILING
        )
        await _make_finding(db_session, inspection.id, finding_key="ceiling_stain")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="ceiling_stain",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.recommendations[0].target_kind == WorkRecommendationTargetKind.CEILING
        assert result.recommendations[0].surface_id == ceiling.id

    async def test_room_advisory_recommendation_has_no_fabricated_surface(self, db_session):
        user = await _make_user(db_session, 211033)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_finding(db_session, inspection.id, finding_key="general_damp")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="general_damp",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.recommendations[0].target_kind == WorkRecommendationTargetKind.ROOM
        assert result.recommendations[0].surface_id is None

    def test_no_opening_target_field_exists(self):
        column_names = {c.name for c in WorkRecommendation.__table__.columns}
        assert "opening_id" not in column_names


class TestRoomIsolation:
    """Final-verification additions: evaluating one room must never touch a
    recommendation belonging to a different room.
    """

    async def test_evaluating_room_a_never_touches_room_b(self, db_session):
        user = await _make_user(db_session, 211040)
        project = await _make_project(db_session, user.id)
        room_a = await _make_room(db_session, project.id)
        room_b = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection_a = await _make_inspection(db_session, room_a.id, template.id)
        inspection_b = await _make_inspection(db_session, room_b.id, template.id)
        finding_a = await _make_finding(db_session, inspection_a.id, finding_key="old_paint_present")
        finding_b = await _make_finding(db_session, inspection_b.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)

        result_a = await service.evaluate_recommendations(project.id, room_a.id, user.id)
        result_b = await service.evaluate_recommendations(project.id, room_b.id, user.id)
        assert result_a.created == 1
        assert result_b.created == 1
        rec_a_id = result_a.recommendations[0].id
        rec_b_id = result_b.recommendations[0].id
        rec_b_updated_at = result_b.recommendations[0].updated_at

        # Room A's source disappears; only Room A is (re-)evaluated.
        finding_a.is_active = False
        await db_session.commit()
        result_a2 = await service.evaluate_recommendations(project.id, room_a.id, user.id)

        assert result_a2.resolved == 1
        assert len(result_a2.recommendations) == 0

        from sqlalchemy import select
        rec_b_refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec_b_id))
        ).scalar_one()
        assert rec_b_refreshed.is_active is True
        assert rec_b_refreshed.resolved_at is None
        assert rec_b_refreshed.updated_at == rec_b_updated_at

        rec_a_refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec_a_id))
        ).scalar_one()
        assert rec_a_refreshed.is_active is False


class TestMultiInspectionSelectiveResolution:
    async def test_removing_one_inspections_source_does_not_resolve_the_other(self, db_session):
        user = await _make_user(db_session, 211041)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection_a = await _make_inspection(db_session, room.id, template.id)
        inspection_b = await _make_inspection(db_session, room.id, template.id)
        finding_a = await _make_finding(db_session, inspection_a.id, finding_key="old_paint_present")
        finding_b = await _make_finding(db_session, inspection_b.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present", recommended_work_code="SKIM_Q3_M2",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert first.created == 2
        by_inspection = {r.inspection_id: r.id for r in first.recommendations}
        rec_a_id = by_inspection[inspection_a.id]
        rec_b_id = by_inspection[inspection_b.id]

        finding_a.is_active = False
        await db_session.commit()
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.resolved == 1
        remaining_ids = {r.id for r in result.recommendations}
        assert remaining_ids == {rec_b_id}

        from sqlalchemy import select
        rec_a_refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec_a_id))
        ).scalar_one()
        assert rec_a_refreshed.is_active is False
        rec_b_refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec_b_id))
        ).scalar_one()
        assert rec_b_refreshed.is_active is True


class TestInactiveRiskExclusion:
    async def test_inactive_risk_never_materializes_a_recommendation(self, db_session):
        user = await _make_user(db_session, 211042)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="cracks_present")
        signature = compute_source_signature([finding.id])
        await _make_risk(
            db_session, room.id, inspection.id, rule_code="SUBSTRATE_POOR",
            source_signature=signature, is_active=False,
        )
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="SUBSTRATE_POOR",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 0
        assert len(result.recommendations) == 0

    async def test_a_historical_resolved_risk_cannot_rematerialize(self, db_session):
        """A Risk that was once active, is now resolved (is_active=False),
        must not cause its recommendation to be (re)created."""
        user = await _make_user(db_session, 211043)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="cracks_present")
        signature = compute_source_signature([finding.id])
        risk = await _make_risk(
            db_session, room.id, inspection.id, rule_code="SUBSTRATE_POOR",
            source_signature=signature, is_active=True,
        )
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="SUBSTRATE_POOR",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert first.created == 1

        risk.is_active = False
        await db_session.commit()
        second = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert second.resolved == 1
        assert len(second.recommendations) == 0

        third = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert third.created == 0
        assert third.reactivated == 0
        assert len(third.recommendations) == 0


class TestFindingSourceFilters:
    async def test_active_finding_on_completed_inspection_participates(self, db_session):
        user = await _make_user(db_session, 211044)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(
            db_session, room.id, template.id, status=InspectionStatus.COMPLETED
        )
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present", is_active=True)
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert result.created == 1

    async def test_active_finding_on_draft_inspection_does_not_participate(self, db_session):
        user = await _make_user(db_session, 211045)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(
            db_session, room.id, template.id, status=InspectionStatus.DRAFT
        )
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present", is_active=True)
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert result.created == 0
        assert len(result.recommendations) == 0

    async def test_inactive_finding_does_not_participate(self, db_session):
        user = await _make_user(db_session, 211046)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        await _make_finding(db_session, inspection.id, finding_key="old_paint_present", is_active=False)
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert result.created == 0

    async def test_finding_from_another_room_does_not_participate(self, db_session):
        user = await _make_user(db_session, 211047)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        other_room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        other_inspection = await _make_inspection(db_session, other_room.id, template.id)
        await _make_finding(db_session, other_inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)
        assert result.created == 0
        assert len(result.recommendations) == 0


class TestAcceptanceSnapshotPreservation:
    async def test_reconciliation_never_touches_accepted_at_or_resolved_price_item_id(self, db_session):
        user = await _make_user(db_session, 211048)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present", recommended_work_code="SKIM_Q3_M2",
        )
        price_item = await _make_price_item_local(db_session, user.id, code="SKIM_Q3_M2")
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec = first.recommendations[0]

        fixed_accepted_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rec.status = WorkRecommendationStatus.ACCEPTED
        rec.accepted_at = fixed_accepted_at
        rec.resolved_price_item_id = price_item.id
        await db_session.commit()

        # Repeat evaluate (unchanged), then resolve, then reactivate.
        await service.evaluate_recommendations(project.id, room.id, user.id)
        finding.is_active = False
        await db_session.commit()
        await service.evaluate_recommendations(project.id, room.id, user.id)
        finding.is_active = True
        await db_session.commit()
        await service.evaluate_recommendations(project.id, room.id, user.id)

        from sqlalchemy import select
        refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec.id))
        ).scalar_one()
        assert refreshed.accepted_at == fixed_accepted_at
        assert refreshed.resolved_price_item_id == price_item.id
        assert refreshed.status == WorkRecommendationStatus.ACCEPTED

    async def test_reconciliation_never_touches_dismissed_at_except_via_commands(self, db_session):
        user = await _make_user(db_session, 211049)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        service = WorkRecommendationService(db_session)
        first = await service.evaluate_recommendations(project.id, room.id, user.id)
        rec = first.recommendations[0]
        await service.dismiss(project.id, rec.id, user.id)
        await db_session.refresh(rec)
        fixed_dismissed_at = rec.dismissed_at
        assert fixed_dismissed_at is not None

        finding.is_active = False
        await db_session.commit()
        await service.evaluate_recommendations(project.id, room.id, user.id)
        finding.is_active = True
        await db_session.commit()
        await service.evaluate_recommendations(project.id, room.id, user.id)

        from sqlalchemy import select
        refreshed = (
            await db_session.execute(select(WorkRecommendation).where(WorkRecommendation.id == rec.id))
        ).scalar_one()
        assert refreshed.dismissed_at == fixed_dismissed_at
        assert refreshed.status == WorkRecommendationStatus.DISMISSED


async def _make_price_item_local(db, owner_id: uuid.UUID, *, code: str) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id, code=code, category=PriceCategory.SKIM_COAT, unit=PriceUnit.M2,
        price=Decimal("35.00"), price_scope=PriceScope.LABOR,
    )
    db.add(item)
    await db.commit()
    return item
