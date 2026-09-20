"""Focused Stage 11B.1 tests: recommendation catalog + persistence foundation.

Covers WorkRecommendationRule representation (A, B, C), deterministic
identity/materialization (D, E), targeting (F, G, H, I), lifecycle (J, K, L,
M), and a regression guard that existing Stage 6/7 model construction is
unaffected by this stage's new models (N).

No evaluation/materialization HTTP endpoint, no accept-to-WorkPlan mutation,
no dismiss/reconsider endpoints, and no Estimate change exist yet — those are
Stage 11B.2/11C, intentionally not tested here.
"""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.rules.risk_rules import compute_source_signature
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.models.checklist import ChecklistTemplate, QualityLevel, Substrate
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
        owner_id=owner_id,
        name="Obiekt testowy",
        address="ul. Kwiatowa 1",
        city="Kraków",
        postal_code="30-001",
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
        code="TPL_CONCRETE",
        version=1,
        substrate=Substrate.CONCRETE,
        title_key="checklist.concrete.title",
    )
    db.add(template)
    await db.commit()
    return template


async def _make_inspection(
    db,
    room_id: uuid.UUID,
    template_id: uuid.UUID,
    *,
    surface_id: uuid.UUID | None = None,
) -> Inspection:
    inspection = Inspection(
        room_id=room_id,
        surface_id=surface_id,
        template_id=template_id,
        substrate=Substrate.CONCRETE,
        status=InspectionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(inspection)
    await db.commit()
    return inspection


async def _make_finding(
    db, inspection_id: uuid.UUID, *, finding_key: str = "moisture_high"
) -> InspectionFinding:
    finding = InspectionFinding(inspection_id=inspection_id, finding_key=finding_key)
    db.add(finding)
    await db.commit()
    return finding


async def _make_risk(
    db,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    *,
    rule_code: str = "MOISTURE_CRITICAL",
    source_signature: str,
) -> Risk:
    risk = Risk(
        room_id=room_id,
        inspection_id=inspection_id,
        risk_code=rule_code,
        rule_code=rule_code,
        rule_version=1,
        severity=RiskSeverity.HIGH,
        title_key="risk.moisture.title",
        explanation_key="risk.moisture.explanation",
        consequence_key="risk.moisture.consequence",
        mitigation_key="risk.moisture.mitigation",
        communication_key="risk.moisture.communication",
        source_signature=source_signature,
    )
    db.add(risk)
    await db.commit()
    return risk


async def _make_price_item(
    db, owner_id: uuid.UUID, *, code: str, price: str | None = "35.00"
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=code,
        category=PriceCategory.SKIM_COAT,
        unit=PriceUnit.M2,
        price=Decimal(price) if price is not None else None,
        price_scope=PriceScope.LABOR,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_rule(
    db,
    *,
    trigger_type: WorkRecommendationTriggerType,
    trigger_code: str,
    recommended_work_code: str = "SKIM_Q3_M2",
) -> WorkRecommendationRule:
    rule = WorkRecommendationRule(
        trigger_type=trigger_type,
        trigger_code=trigger_code,
        recommended_work_code=recommended_work_code,
    )
    db.add(rule)
    await db.commit()
    return rule


class TestA_RiskRuleTrigger:
    async def test_risk_rule_trigger_is_representable(self, db_session):
        user = await _make_user(db_session, 111001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        signature = compute_source_signature([uuid.uuid4()])
        risk = await _make_risk(
            db_session, room.id, inspection.id,
            rule_code="MOISTURE_CRITICAL", source_signature=signature,
        )
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="MOISTURE_CRITICAL",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code=rule.trigger_code,
            source_signature=signature,
            inspection_id=inspection.id,
            rule_id=rule.id,
            risk_id=risk.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()

        assert recommendation.trigger_type == WorkRecommendationTriggerType.RISK_RULE
        assert recommendation.risk_id == risk.id
        assert recommendation.finding_id is None


class TestB_FindingKeyTrigger:
    async def test_finding_key_trigger_is_representable(self, db_session):
        user = await _make_user(db_session, 111002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="old_paint_present")
        signature = compute_source_signature([finding.id])
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
            recommended_work_code="MECHANICAL_SCRATCH",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=signature,
            inspection_id=inspection.id,
            rule_id=rule.id,
            finding_id=finding.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()

        assert recommendation.trigger_type == WorkRecommendationTriggerType.FINDING
        assert recommendation.finding_id == finding.id
        assert recommendation.risk_id is None


class TestC_SemanticWorkCode:
    async def test_recommended_work_code_is_a_string_not_a_price_item_fk(self, db_session):
        user = await _make_user(db_session, 111003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
            recommended_work_code="SKIM_Q3_M2",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()

        assert isinstance(recommendation.recommended_work_code, str)
        assert recommendation.recommended_work_code == "SKIM_Q3_M2"
        # No PriceItem needs to exist at all for a PENDING recommendation —
        # the code is resolved only at acceptance time (Stage 11C).
        assert recommendation.resolved_price_item_id is None


class TestD_DeterministicIdentity:
    async def test_materialize_one_reuses_the_same_row_by_identity(self, db_session):
        user = await _make_user(db_session, 111004)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        signature = compute_source_signature([uuid.uuid4()])
        service = WorkRecommendationService(db_session)

        first = await service.materialize_one(
            room_id=room.id,
            inspection_id=inspection.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            rule=rule,
            source_signature=signature,
        )
        await db_session.commit()

        second = await service.materialize_one(
            room_id=room.id,
            inspection_id=inspection.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            rule=rule,
            source_signature=signature,
        )
        await db_session.commit()

        assert first.id == second.id

        from sqlalchemy import func, select
        count = (
            await db_session.execute(
                select(func.count()).select_from(WorkRecommendation)
            )
        ).scalar_one()
        assert count == 1

    async def test_duplicate_identity_insert_violates_db_constraint(self, db_session):
        user = await _make_user(db_session, 111005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        signature = compute_source_signature([uuid.uuid4()])

        db_session.add(
            WorkRecommendation(
                trigger_type=WorkRecommendationTriggerType.FINDING,
                trigger_code=rule.trigger_code,
                source_signature=signature,
                inspection_id=inspection.id,
                rule_id=rule.id,
                room_id=room.id,
                surface_id=None,
                target_kind=WorkRecommendationTargetKind.ROOM,
                recommended_work_code=rule.recommended_work_code,
            )
        )
        await db_session.commit()

        db_session.add(
            WorkRecommendation(
                trigger_type=WorkRecommendationTriggerType.FINDING,
                trigger_code=rule.trigger_code,
                source_signature=signature,
                inspection_id=inspection.id,
                rule_id=rule.id,
                room_id=room.id,
                surface_id=None,
                target_kind=WorkRecommendationTargetKind.ROOM,
                recommended_work_code=rule.recommended_work_code,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestE_SameWorkCodeDifferentSignatures:
    async def test_same_recommended_work_code_from_two_signatures_both_persist(self, db_session):
        user = await _make_user(db_session, 111006)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
            recommended_work_code="SKIM_Q3_M2",
        )
        service = WorkRecommendationService(db_session)

        first = await service.materialize_one(
            room_id=room.id, inspection_id=inspection.id, surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM, rule=rule,
            source_signature=compute_source_signature([uuid.uuid4()]),
        )
        second = await service.materialize_one(
            room_id=room.id, inspection_id=inspection.id, surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM, rule=rule,
            source_signature=compute_source_signature([uuid.uuid4()]),
        )
        await db_session.commit()

        assert first.id != second.id
        assert first.recommended_work_code == second.recommended_work_code == "SKIM_Q3_M2"


class TestF_WallTargeting:
    async def test_wall_surface_target_persists(self, db_session):
        user = await _make_user(db_session, 111007)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        wall = await _make_surface(db_session, room.id, SurfaceType.WALL)
        template = await _make_template(db_session)
        inspection = await _make_inspection(
            db_session, room.id, template.id, surface_id=wall.id
        )
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=wall.id,
            target_kind=WorkRecommendationTargetKind.WALL,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()

        assert recommendation.surface_id == wall.id
        assert recommendation.target_kind == WorkRecommendationTargetKind.WALL


class TestG_CanonicalPlaneTargeting:
    async def test_canonical_floor_and_ceiling_surface_targets_persist(self, db_session):
        user = await _make_user(db_session, 111008)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        floor = await _make_surface(db_session, room.id, SurfaceType.FLOOR)
        ceiling = await _make_surface(db_session, room.id, SurfaceType.CEILING)
        template = await _make_template(db_session)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="floor_uneven",
        )

        floor_inspection = await _make_inspection(db_session, room.id, template.id)
        floor_rec = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=floor_inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=floor.id,
            target_kind=WorkRecommendationTargetKind.FLOOR,
            recommended_work_code=rule.recommended_work_code,
        )
        ceiling_inspection = await _make_inspection(db_session, room.id, template.id)
        ceiling_rec = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=ceiling_inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=ceiling.id,
            target_kind=WorkRecommendationTargetKind.CEILING,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add_all([floor_rec, ceiling_rec])
        await db_session.commit()

        assert floor_rec.surface_id == floor.id
        assert floor_rec.target_kind == WorkRecommendationTargetKind.FLOOR
        assert ceiling_rec.surface_id == ceiling.id
        assert ceiling_rec.target_kind == WorkRecommendationTargetKind.CEILING


class TestH_RoomAdvisory:
    async def test_room_level_recommendation_has_no_surface_target(self, db_session):
        user = await _make_user(db_session, 111009)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="general_damp",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()

        assert recommendation.surface_id is None
        assert recommendation.target_kind == WorkRecommendationTargetKind.ROOM
        assert recommendation.room_id == room.id


class TestI_NoOpeningTarget:
    def test_model_has_no_opening_field(self):
        column_names = {c.name for c in WorkRecommendation.__table__.columns}
        assert "opening_id" not in column_names
        assert not hasattr(WorkRecommendation, "opening_id")


class TestJ_LifecycleStatus:
    async def test_default_status_is_pending(self, db_session):
        user = await _make_user(db_session, 111010)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()

        assert recommendation.status == WorkRecommendationStatus.PENDING

    @pytest.mark.parametrize(
        "status",
        [
            WorkRecommendationStatus.PENDING,
            WorkRecommendationStatus.ACCEPTED,
            WorkRecommendationStatus.DISMISSED,
        ],
    )
    async def test_each_lifecycle_status_persists(self, db_session, status):
        user = await _make_user(db_session, 111011)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=f"trigger_{status.value.lower()}",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
            status=status,
        )
        db_session.add(recommendation)
        await db_session.commit()
        await db_session.refresh(recommendation)

        assert recommendation.status == status


class TestK_ActiveResolvedLifecycle:
    async def test_is_active_defaults_true_and_resolved_at_is_settable(self, db_session):
        user = await _make_user(db_session, 111012)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()
        assert recommendation.is_active is True
        assert recommendation.resolved_at is None

        recommendation.is_active = False
        recommendation.resolved_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(recommendation)

        assert recommendation.is_active is False
        assert recommendation.resolved_at is not None

    async def test_materialize_one_reactivates_a_resolved_row(self, db_session):
        user = await _make_user(db_session, 111013)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
        )
        signature = compute_source_signature([uuid.uuid4()])
        service = WorkRecommendationService(db_session)

        recommendation = await service.materialize_one(
            room_id=room.id, inspection_id=inspection.id, surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM, rule=rule,
            source_signature=signature,
        )
        await db_session.commit()
        recommendation.is_active = False
        recommendation.resolved_at = datetime.now(timezone.utc)
        await db_session.commit()

        reactivated = await service.materialize_one(
            room_id=room.id, inspection_id=inspection.id, surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM, rule=rule,
            source_signature=signature,
        )
        await db_session.commit()

        assert reactivated.id == recommendation.id
        assert reactivated.is_active is True
        assert reactivated.resolved_at is None


class TestL_ResolvedPriceItemNullable:
    async def test_resolved_price_item_id_is_nullable_before_acceptance(self, db_session):
        user = await _make_user(db_session, 111014)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
            recommended_work_code="CODE_THAT_HAS_NO_PRICEITEM_YET",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
        )
        db_session.add(recommendation)
        await db_session.commit()

        # No PriceItem with this code exists anywhere — the row is still
        # perfectly valid as PENDING. Resolution only happens at accept time.
        assert recommendation.resolved_price_item_id is None
        assert recommendation.status == WorkRecommendationStatus.PENDING


class TestM_NullPriceUnaffected:
    async def test_a_null_priced_price_item_can_still_be_referenced(self, db_session):
        """This stage introduces no new price-nullability behavior: a
        NULL-priced PriceItem is exactly as valid a resolved_price_item_id
        target as any other — Stage 10's NULL-vs-0.00 semantics are
        untouched by Stage 11B.1.
        """
        user = await _make_user(db_session, 111015)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        unresolved_item = await _make_price_item(
            db_session, user.id, code="UNRESOLVED_ITEM", price=None
        )
        rule = await _make_rule(
            db_session,
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="old_paint_present",
            recommended_work_code="UNRESOLVED_ITEM",
        )
        recommendation = WorkRecommendation(
            trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code=rule.trigger_code,
            source_signature=compute_source_signature([uuid.uuid4()]),
            inspection_id=inspection.id,
            rule_id=rule.id,
            room_id=room.id,
            surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM,
            recommended_work_code=rule.recommended_work_code,
            status=WorkRecommendationStatus.ACCEPTED,
            resolved_price_item_id=unresolved_item.id,
            accepted_at=datetime.now(timezone.utc),
        )
        db_session.add(recommendation)
        await db_session.commit()
        await db_session.refresh(recommendation)

        assert recommendation.resolved_price_item_id == unresolved_item.id
        assert unresolved_item.price is None


class TestN_ExistingBehaviorUnaffected:
    async def test_risk_and_inspection_construction_still_work(self, db_session):
        """Regression guard specific to this stage: registering the new
        WorkRecommendation/WorkRecommendationRule models in
        app/models/__init__.py must not disturb existing Risk/Inspection
        model construction (enum name collisions, import ordering, etc.).
        """
        user = await _make_user(db_session, 111016)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id)
        signature = compute_source_signature([finding.id])
        risk = await _make_risk(
            db_session, room.id, inspection.id,
            rule_code="MOISTURE_CRITICAL", source_signature=signature,
        )

        assert risk.id is not None
        assert risk.is_active is True
        assert inspection.status == InspectionStatus.COMPLETED


class TestO_MultipleWorksPerTrigger:
    """Corrected in final verification: source_signature identifies ONLY the
    source evidence (a pure hash over finding UUIDs) and has no knowledge of
    recommended_work_code, so a single trigger firing that maps to several
    suggested works (e.g. a poor substrate recommending both a primer and a
    leveling compound) MUST produce one distinct row per suggested work.
    """

    async def test_one_trigger_materializes_three_independent_recommendations(
        self, db_session
    ):
        user = await _make_user(db_session, 111017)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="substrate_poor")
        signature = compute_source_signature([finding.id])

        primer_rule = await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="substrate_poor", recommended_work_code="PRIMER_M2",
        )
        leveling_rule = await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="substrate_poor", recommended_work_code="LEVELING_M2",
        )
        skim_rule = await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="substrate_poor", recommended_work_code="SKIM_Q3_M2",
        )

        service = WorkRecommendationService(db_session)
        recs = []
        for rule in (primer_rule, leveling_rule, skim_rule):
            rec = await service.materialize_one(
                room_id=room.id, inspection_id=inspection.id, surface_id=None,
                target_kind=WorkRecommendationTargetKind.ROOM, rule=rule,
                source_signature=signature, finding_id=finding.id,
            )
            recs.append(rec)
        await db_session.commit()

        # Three distinct rows, never collapsed or silently dropped.
        ids = {rec.id for rec in recs}
        assert len(ids) == 3
        codes = {rec.recommended_work_code for rec in recs}
        assert codes == {"PRIMER_M2", "LEVELING_M2", "SKIM_Q3_M2"}

        from sqlalchemy import func, select
        count = (
            await db_session.execute(
                select(func.count()).select_from(WorkRecommendation).where(
                    WorkRecommendation.inspection_id == inspection.id,
                    WorkRecommendation.trigger_code == "substrate_poor",
                    WorkRecommendation.source_signature == signature,
                )
            )
        ).scalar_one()
        assert count == 3

        # Re-materializing the same trigger+work still reuses (does not
        # duplicate) each individual row.
        reused = await service.materialize_one(
            room_id=room.id, inspection_id=inspection.id, surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM, rule=primer_rule,
            source_signature=signature, finding_id=finding.id,
        )
        await db_session.commit()
        assert reused.id == recs[0].id


class TestP_TriggerTypeDisambiguation:
    async def test_risk_rule_and_finding_triggers_never_collide_on_identity(
        self, db_session
    ):
        """A RiskRule.code and an InspectionFinding.finding_key are
        independent vocabularies. Even in the deliberately adversarial case
        where both happen to use the identical string as trigger_code, both
        recommend the identical work, and (because the Risk here is derived
        from exactly the one finding) both computed signatures are
        identical, the two recommendations must coexist as separate rows —
        trigger_type must disambiguate them at the DB level, not by
        accidental non-collision of the two code spaces.
        """
        user = await _make_user(db_session, 111018)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        template = await _make_template(db_session)
        inspection = await _make_inspection(db_session, room.id, template.id)
        finding = await _make_finding(db_session, inspection.id, finding_key="COLLIDING_CODE")
        signature = compute_source_signature([finding.id])
        # A single-finding risk has the exact same signature formula as a
        # single-finding FINDING trigger — the adversarial case in practice.
        risk = await _make_risk(
            db_session, room.id, inspection.id,
            rule_code="COLLIDING_CODE", source_signature=signature,
        )

        risk_rule = await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="COLLIDING_CODE", recommended_work_code="SAME_WORK_CODE",
        )
        finding_rule = await _make_rule(
            db_session, trigger_type=WorkRecommendationTriggerType.FINDING,
            trigger_code="COLLIDING_CODE", recommended_work_code="SAME_WORK_CODE",
        )

        service = WorkRecommendationService(db_session)
        from_risk = await service.materialize_one(
            room_id=room.id, inspection_id=inspection.id, surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM, rule=risk_rule,
            source_signature=signature, risk_id=risk.id,
        )
        from_finding = await service.materialize_one(
            room_id=room.id, inspection_id=inspection.id, surface_id=None,
            target_kind=WorkRecommendationTargetKind.ROOM, rule=finding_rule,
            source_signature=signature, finding_id=finding.id,
        )
        await db_session.commit()

        assert from_risk.id != from_finding.id
        assert from_risk.trigger_type == WorkRecommendationTriggerType.RISK_RULE
        assert from_finding.trigger_type == WorkRecommendationTriggerType.FINDING
