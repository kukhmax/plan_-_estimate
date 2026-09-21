"""Focused Stage 12C tests: coefficient catalog bootstrap mechanism.

The production baseline (`app/domain/data/price_coefficients.py`) ships
intentionally EMPTY -- Stage 12B forbids seeding any Q/S/PSG or other
percentage before Stage 12G defines and the owner approves real default
values. These tests prove the underlying idempotent-bootstrap MECHANISM
itself is correct (mirrors the Stage 11 `WorkRecommendationRule` bootstrap
precedent) using a small, clearly-fake, test-only baseline injected via
monkeypatch -- never real catalog data.
"""
from decimal import Decimal

from sqlalchemy import select

from app.domain.data.price_coefficients import (
    CoefficientGroupData,
    CoefficientOptionData,
)
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.models import User
from app.models.price_coefficient import CoefficientGroup, CoefficientOption

FAKE_BASELINE = [
    CoefficientGroupData(
        code="TEST_HEIGHT",
        display_name="Test Height",
        options=(
            CoefficientOptionData(code="TEST_HEIGHT_NORMAL", percentage="0", is_base=True),
            CoefficientOptionData(code="TEST_HEIGHT_HIGH", percentage="20"),
        ),
    ),
]


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


def _patch_baseline(monkeypatch, baseline=FAKE_BASELINE):
    monkeypatch.setattr(
        "app.domain.services.price_coefficient_service.build_baseline_price_coefficients",
        lambda: baseline,
    )


class TestProductionBaselineIsEmpty:
    def test_shipped_baseline_has_no_entries(self):
        """Guards the Stage 12B gate directly: this must fail loudly if
        anyone adds a real entry to the production data module without an
        explicit, separate owner-approved specification (Stage 12G)."""
        from app.domain.data.price_coefficients import build_baseline_price_coefficients

        assert build_baseline_price_coefficients() == []

    async def test_bootstrap_is_a_no_op_against_the_real_production_baseline(self, db_session):
        user = await _make_user(db_session, 12100)
        service = PriceCoefficientService(db_session)
        created = await service.ensure_owner_catalog(user.id)
        assert created == []
        rows = (
            await db_session.execute(
                select(CoefficientGroup).where(CoefficientGroup.owner_id == user.id)
            )
        ).scalars().all()
        assert rows == []


class TestBootstrapMechanism:
    async def test_first_access_creates_expected_structural_defaults(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        user = await _make_user(db_session, 12101)
        service = PriceCoefficientService(db_session)

        created = await service.ensure_owner_catalog(user.id)
        assert len(created) == 1
        assert created[0].code == "TEST_HEIGHT"

        groups = await service.list_owner_groups(user.id, archived="all")
        assert len(groups) == 1
        group = groups[0]
        assert group.display_name == "Test Height"
        assert {o.code for o in group.options} == {"TEST_HEIGHT_NORMAL", "TEST_HEIGHT_HIGH"}
        base_options = [o for o in group.options if o.is_base]
        assert len(base_options) == 1
        assert base_options[0].code == "TEST_HEIGHT_NORMAL"

    async def test_repeated_bootstrap_creates_no_duplicates(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        user = await _make_user(db_session, 12102)
        service = PriceCoefficientService(db_session)

        await service.ensure_owner_catalog(user.id)
        second = await service.ensure_owner_catalog(user.id)
        third = await service.ensure_owner_catalog(user.id)
        assert second == []
        assert third == []

        groups = (
            await db_session.execute(
                select(CoefficientGroup).where(CoefficientGroup.owner_id == user.id)
            )
        ).scalars().all()
        assert len(groups) == 1
        options = (
            await db_session.execute(
                select(CoefficientOption).where(
                    CoefficientOption.group_id == groups[0].id
                )
            )
        ).scalars().all()
        assert len(options) == 2

    async def test_edited_percentage_survives_repeated_bootstrap(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        user = await _make_user(db_session, 12103)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)

        groups = await service.list_owner_groups(user.id, archived="all")
        high_option = next(o for o in groups[0].options if o.code == "TEST_HEIGHT_HIGH")
        await service.update_option(user.id, high_option.id, percentage=Decimal("25"))

        await service.ensure_owner_catalog(user.id)  # re-run, must not overwrite

        refreshed = await service.get_owned_option(user.id, high_option.id)
        assert refreshed.percentage == Decimal("25")

    async def test_edited_display_name_survives_repeated_bootstrap(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        user = await _make_user(db_session, 12104)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)

        groups = await service.list_owner_groups(user.id, archived="all")
        await service.update_group(user.id, groups[0].id, display_name="Renamed")

        await service.ensure_owner_catalog(user.id)  # re-run, must not overwrite

        refreshed = await service.get_owned_group(user.id, groups[0].id)
        assert refreshed.display_name == "Renamed"

    async def test_archived_group_remains_archived_after_rebootstrap(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        user = await _make_user(db_session, 12105)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        groups = await service.list_owner_groups(user.id, archived="all")
        await service.archive_group(user.id, groups[0].id)

        await service.ensure_owner_catalog(user.id)  # must not reactivate

        refreshed = await service.get_owned_group(user.id, groups[0].id)
        assert refreshed.is_archived is True

    async def test_archived_option_remains_archived_after_rebootstrap(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        user = await _make_user(db_session, 12106)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        groups = await service.list_owner_groups(user.id, archived="all")
        high_option = next(o for o in groups[0].options if o.code == "TEST_HEIGHT_HIGH")
        await service.archive_option(user.id, high_option.id)

        await service.ensure_owner_catalog(user.id)  # must not reactivate

        refreshed = await service.get_owned_option(user.id, high_option.id)
        assert refreshed.is_archived is True

    async def test_restore_remains_explicit_not_triggered_by_bootstrap(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        user = await _make_user(db_session, 12107)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        groups = await service.list_owner_groups(user.id, archived="all")
        await service.archive_group(user.id, groups[0].id)
        await service.ensure_owner_catalog(user.id)
        still_archived = await service.get_owned_group(user.id, groups[0].id)
        assert still_archived.is_archived is True

        restored = await service.restore_group(user.id, groups[0].id)
        assert restored.is_archived is False

    async def test_second_owner_receives_independent_catalog(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        owner1 = await _make_user(db_session, 12108)
        owner2 = await _make_user(db_session, 12109)
        service = PriceCoefficientService(db_session)

        await service.ensure_owner_catalog(owner1.id)
        await service.ensure_owner_catalog(owner2.id)

        groups1 = await service.list_owner_groups(owner1.id, archived="all")
        groups2 = await service.list_owner_groups(owner2.id, archived="all")
        assert len(groups1) == 1
        assert len(groups2) == 1
        assert groups1[0].id != groups2[0].id
        assert groups1[0].owner_id == owner1.id
        assert groups2[0].owner_id == owner2.id

    async def test_one_owners_edits_do_not_affect_another(self, db_session, monkeypatch):
        _patch_baseline(monkeypatch)
        owner1 = await _make_user(db_session, 12110)
        owner2 = await _make_user(db_session, 12111)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(owner1.id)
        await service.ensure_owner_catalog(owner2.id)

        groups1 = await service.list_owner_groups(owner1.id, archived="all")
        await service.update_group(owner1.id, groups1[0].id, display_name="Owner1 Custom")
        await service.archive_group(owner1.id, groups1[0].id)

        groups2 = await service.list_owner_groups(owner2.id, archived="all")
        assert groups2[0].display_name == "Test Height"
        assert groups2[0].is_archived is False
