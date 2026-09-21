"""Stage 11B.1.1: baseline `WorkRecommendationRule` catalog.

Manual Stage 11D.2 acceptance found `work_recommendation_rules` empty in the
real dev database, so every real "Oceń zalecenia" click returned zero
recommendations. This module proves the four owner-approved, HIGH-confidence
baseline mappings are installed deterministically and idempotently by the
lazy application bootstrap (mirroring `RiskService._ensure_bootstrapped`),
and that the two explicitly-withheld cases (EFFLORESCENCE_CAUSE_CHECK, and
FINDING-keyed duplicates of the same four RISK_RULE mappings) are absent.

Integration coverage against a real evaluate_recommendations() run using
these exact codes lives in test_work_recommendation_evaluation.py's
TestBaselineCatalogIntegration below.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import select

from app.domain.data.price_book_seed import build_approved_price_book_items
from app.domain.data.work_recommendation_rules import (
    build_baseline_work_recommendation_rules,
)
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.models.checklist import ChecklistTemplate, Substrate
from app.models.inspection import Inspection, InspectionStatus
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.risk import Risk, RiskSeverity
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_recommendation import (
    WorkRecommendationRule,
    WorkRecommendationTriggerType,
)

APPROVED_MAPPINGS = {
    "DUSTY_SUBSTRATE_PRIME": "CENNIK_PRIM_STD-01",
    "WEAK_ADHESION_PREP": "CENNIK_PRIM_ADH-01",
    "UNEVENNESS_PREP_INCREASED": "CENNIK_SKIM_LOCAL-01",
    "CRACK_RECURRENCE": "CENNIK_SKIM_CRACK-01",
}


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


class TestBaselineCatalogData:
    """Pure data assertions -- no DB, no service."""

    def test_contains_exactly_the_four_approved_mappings(self):
        entries = build_baseline_work_recommendation_rules()
        actual = {
            (entry.trigger_type, entry.trigger_code, entry.recommended_work_code)
            for entry in entries
        }
        expected = {
            (WorkRecommendationTriggerType.RISK_RULE, code, work_code)
            for code, work_code in APPROVED_MAPPINGS.items()
        }
        assert actual == expected

    def test_all_entries_are_risk_rule_triggered_not_finding(self):
        entries = build_baseline_work_recommendation_rules()
        assert all(
            entry.trigger_type == WorkRecommendationTriggerType.RISK_RULE
            for entry in entries
        )

    def test_no_duplicate_identities_in_baseline_data(self):
        entries = build_baseline_work_recommendation_rules()
        identities = [
            (entry.trigger_type, entry.trigger_code, entry.recommended_work_code)
            for entry in entries
        ]
        assert len(identities) == len(set(identities))

    def test_efflorescence_cause_check_is_not_mapped(self):
        entries = build_baseline_work_recommendation_rules()
        assert not any(entry.trigger_code == "EFFLORESCENCE_CAUSE_CHECK" for entry in entries)

    def test_efflorescence_is_not_mapped_to_scrape_item(self):
        entries = build_baseline_work_recommendation_rules()
        assert not any(
            entry.recommended_work_code == "CENNIK_PREP_SCRAPE-01" for entry in entries
        )

    def test_recommended_work_codes_are_canonical_price_item_codes(self):
        catalog_codes = {item.code for item in build_approved_price_book_items()}
        entries = build_baseline_work_recommendation_rules()
        for entry in entries:
            assert entry.recommended_work_code in catalog_codes

    def test_no_two_baseline_entries_recommend_the_same_work_code(self):
        entries = build_baseline_work_recommendation_rules()
        codes = [entry.recommended_work_code for entry in entries]
        assert len(codes) == len(set(codes))


class TestBaselineCatalogBootstrap:
    """Bootstrap materialization via WorkRecommendationService."""

    async def test_bootstrap_installs_all_four_mappings(self, db_session):
        user = await _make_user(db_session, 411001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        service = WorkRecommendationService(db_session)

        await service._ensure_bootstrapped()

        rows = (
            await db_session.execute(select(WorkRecommendationRule))
        ).scalars().all()
        actual = {(row.trigger_type, row.trigger_code, row.recommended_work_code) for row in rows}
        expected = {
            (WorkRecommendationTriggerType.RISK_RULE, code, work_code)
            for code, work_code in APPROVED_MAPPINGS.items()
        }
        assert actual == expected
        assert all(row.active is True for row in rows)
        # Keep unused fixtures referenced (room/project exist for future
        # room-scoped bootstrap variants without unused-arg lint noise).
        assert room.project_id == project.id

    async def test_bootstrap_is_idempotent_on_repeated_calls(self, db_session):
        service = WorkRecommendationService(db_session)
        await service._ensure_bootstrapped()
        await service._ensure_bootstrapped()
        await service._ensure_bootstrapped()

        rows = (
            await db_session.execute(select(WorkRecommendationRule))
        ).scalars().all()
        assert len(rows) == len(APPROVED_MAPPINGS)

    async def test_bootstrap_never_duplicates_a_preexisting_row(self, db_session):
        """A rule already present (e.g. from a prior process run) is left
        untouched -- bootstrap only adds what's missing, never re-inserts."""
        existing = WorkRecommendationRule(
            trigger_type=WorkRecommendationTriggerType.RISK_RULE,
            trigger_code="CRACK_RECURRENCE",
            recommended_work_code="CENNIK_SKIM_CRACK-01",
            active=True,
        )
        db_session.add(existing)
        await db_session.commit()
        existing_id = existing.id

        service = WorkRecommendationService(db_session)
        await service._ensure_bootstrapped()

        rows = (
            await db_session.execute(
                select(WorkRecommendationRule).where(
                    WorkRecommendationRule.trigger_code == "CRACK_RECURRENCE"
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == existing_id

    async def test_evaluate_recommendations_triggers_bootstrap(self, db_session):
        user = await _make_user(db_session, 411002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        service = WorkRecommendationService(db_session)

        await service.evaluate_recommendations(project.id, room.id, user.id)

        rows = (
            await db_session.execute(select(WorkRecommendationRule))
        ).scalars().all()
        assert len(rows) == len(APPROVED_MAPPINGS)

    async def test_list_recommendations_triggers_bootstrap(self, db_session):
        user = await _make_user(db_session, 411003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        service = WorkRecommendationService(db_session)

        await service.list_recommendations(project.id, room.id, user.id)

        rows = (
            await db_session.execute(select(WorkRecommendationRule))
        ).scalars().all()
        assert len(rows) == len(APPROVED_MAPPINGS)


class TestBaselineCatalogIntegration:
    """Real evaluate_recommendations() run for the owner's actual manual
    acceptance scenario: a WALL inspection with the five Stage 7 risks the
    owner actually saw, of which exactly four now have a baseline mapping."""

    async def _make_inspection_with_risk(
        self, db, *, rule_code: str, room_id, surface_id
    ):
        template = ChecklistTemplate(
            code=f"TPL_{rule_code}", version=1, substrate=Substrate.GYPSUM_PLASTER,
            title_key="checklist.gypsum.title",
        )
        db.add(template)
        await db.commit()

        inspection = Inspection(
            room_id=room_id, surface_id=surface_id, plane=None, template_id=template.id,
            substrate=Substrate.GYPSUM_PLASTER, quality_target=None,
            status=InspectionStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(inspection)
        await db.commit()

        risk = Risk(
            room_id=room_id, inspection_id=inspection.id, risk_code=rule_code,
            rule_code=rule_code, rule_version=1, severity=RiskSeverity.MEDIUM,
            title_key="risk.x.title", explanation_key="risk.x.explanation",
            consequence_key="risk.x.consequence", mitigation_key="risk.x.mitigation",
            communication_key="risk.x.communication",
            source_signature=f"sig-{rule_code}", is_active=True,
        )
        db.add(risk)
        await db.commit()
        return inspection, risk

    async def test_dusty_substrate_prime_materializes_with_null_price_item(self, db_session):
        """The owner's real scenario: DUSTY_SUBSTRATE_PRIME fires ->
        WorkRecommendation is materialized with recommended_work_code =
        CENNIK_PRIM_STD-01, even though that PriceItem's price is NULL
        ("do ustalenia") -- NULL price must never block materialization,
        only accept-time PriceItem *resolution* is a separate concern."""
        user = await _make_user(db_session, 411010)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = Surface(room_id=room.id, name="Ściana 1", surface_type=SurfaceType.WALL)
        db_session.add(surface)
        await db_session.commit()

        price_item = PriceItem(
            owner_id=user.id, code="CENNIK_PRIM_STD-01", category=PriceCategory.PREPARATION,
            unit=PriceUnit.M2, name_key="pricebook.seed.prim_std", price=None,
            price_scope=PriceScope.LABOR_AND_MATERIAL,
        )
        db_session.add(price_item)
        await db_session.commit()

        await self._make_inspection_with_risk(
            db_session, rule_code="DUSTY_SUBSTRATE_PRIME", room_id=room.id, surface_id=surface.id,
        )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 1
        assert len(result.recommendations) == 1
        rec = result.recommendations[0]
        assert rec.trigger_type == WorkRecommendationTriggerType.RISK_RULE
        assert rec.trigger_code == "DUSTY_SUBSTRATE_PRIME"
        assert rec.recommended_work_code == "CENNIK_PRIM_STD-01"
        assert rec.is_active is True

        resolved = await service.resolve_current_price_items(user.id, [rec])
        assert resolved["CENNIK_PRIM_STD-01"].price is None

    async def test_all_four_approved_scenarios_materialize_exactly_one_each(self, db_session):
        user = await _make_user(db_session, 411011)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)

        for code, work_code in APPROVED_MAPPINGS.items():
            surface = Surface(room_id=room.id, name=f"Ściana {code}", surface_type=SurfaceType.WALL)
            db_session.add(surface)
            await db_session.commit()
            db_session.add(
                PriceItem(
                    owner_id=user.id, code=work_code, category=PriceCategory.PREPARATION,
                    unit=PriceUnit.M2, name_key="pricebook.seed.x", price=None,
                )
            )
            await db_session.commit()
            await self._make_inspection_with_risk(
                db_session, rule_code=code, room_id=room.id, surface_id=surface.id,
            )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 4
        recommended_codes = {rec.recommended_work_code for rec in result.recommendations}
        assert recommended_codes == set(APPROVED_MAPPINGS.values())

    async def test_efflorescence_risk_produces_no_recommendation(self, db_session):
        """The owner's real fifth risk, EFFLORESCENCE_CAUSE_CHECK, remains an
        intentional catalog gap: it must never silently materialize a
        recommendation against an unrelated PriceItem."""
        user = await _make_user(db_session, 411012)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = Surface(room_id=room.id, name="Ściana 1", surface_type=SurfaceType.WALL)
        db_session.add(surface)
        await db_session.commit()
        # Even if the owner's PriceBook happens to contain the scraping item,
        # it must not be recommended for efflorescence.
        db_session.add(
            PriceItem(
                owner_id=user.id, code="CENNIK_PREP_SCRAPE-01", category=PriceCategory.PREPARATION,
                unit=PriceUnit.M2, name_key="pricebook.seed.prep_scrape", price=None,
            )
        )
        await db_session.commit()

        await self._make_inspection_with_risk(
            db_session, rule_code="EFFLORESCENCE_CAUSE_CHECK", room_id=room.id, surface_id=surface.id,
        )

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 0
        assert result.recommendations == []

    async def test_real_owner_scenario_produces_exactly_four_of_five(self, db_session):
        """Reproduces the owner's actual manual-acceptance room: five active
        Stage 7 risks (CRACK_RECURRENCE, UNEVENNESS_PREP_INCREASED,
        DUSTY_SUBSTRATE_PRIME, EFFLORESCENCE_CAUSE_CHECK, WEAK_ADHESION_PREP)
        on one WALL inspection. Expected: exactly 4 recommendations, never 5,
        never 0."""
        user = await _make_user(db_session, 411013)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = Surface(room_id=room.id, name="Ściana 1", surface_type=SurfaceType.WALL)
        db_session.add(surface)
        await db_session.commit()

        for work_code in set(APPROVED_MAPPINGS.values()) | {"CENNIK_PREP_SCRAPE-01"}:
            db_session.add(
                PriceItem(
                    owner_id=user.id, code=work_code, category=PriceCategory.PREPARATION,
                    unit=PriceUnit.M2, name_key="pricebook.seed.x", price=None,
                )
            )
        await db_session.commit()

        template = ChecklistTemplate(
            code="TPL_REAL_SCENARIO", version=1, substrate=Substrate.GYPSUM_PLASTER,
            title_key="checklist.gypsum.title",
        )
        db_session.add(template)
        await db_session.commit()
        inspection = Inspection(
            room_id=room.id, surface_id=surface.id, plane=None, template_id=template.id,
            substrate=Substrate.GYPSUM_PLASTER, quality_target=None,
            status=InspectionStatus.COMPLETED, completed_at=datetime.now(timezone.utc),
        )
        db_session.add(inspection)
        await db_session.commit()

        real_rule_codes = [
            "CRACK_RECURRENCE",
            "UNEVENNESS_PREP_INCREASED",
            "DUSTY_SUBSTRATE_PRIME",
            "EFFLORESCENCE_CAUSE_CHECK",
            "WEAK_ADHESION_PREP",
        ]
        for rule_code in real_rule_codes:
            db_session.add(
                Risk(
                    room_id=room.id, inspection_id=inspection.id, risk_code=rule_code,
                    rule_code=rule_code, rule_version=1, severity=RiskSeverity.MEDIUM,
                    title_key="risk.x.title", explanation_key="risk.x.explanation",
                    consequence_key="risk.x.consequence", mitigation_key="risk.x.mitigation",
                    communication_key="risk.x.communication",
                    source_signature=f"sig-{rule_code}", is_active=True,
                )
            )
        await db_session.commit()

        service = WorkRecommendationService(db_session)
        result = await service.evaluate_recommendations(project.id, room.id, user.id)

        assert result.created == 4
        recommended_codes = {rec.recommended_work_code for rec in result.recommendations}
        assert recommended_codes == set(APPROVED_MAPPINGS.values())
        trigger_codes = {rec.trigger_code for rec in result.recommendations}
        assert "EFFLORESCENCE_CAUSE_CHECK" not in trigger_codes
