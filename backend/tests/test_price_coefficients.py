"""Focused Stage 12C tests: price coefficient catalog domain service.

Covers CoefficientGroup/CoefficientOption CRUD, immutable stable codes, the
base-option invariant (atomic replacement, archived-base non-promotion),
owner isolation, and exact Decimal percentage validation. No planned-work
assignment (Stage 12D) and no Estimate integration (Stage 12E) exist yet, so
none of that is exercised here.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import (
    CoefficientGroupNotFoundError,
    CoefficientOptionNotFoundError,
    PriceCoefficientValidationError,
)
from app.domain.services.price_coefficient_service import (
    PriceCoefficientService,
    validate_percentage,
)
from app.models import User
from app.models.price_coefficient import (
    CoefficientGroup,
    CoefficientOption,
    CoefficientSelectionMode,
)


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


class TestModelEnums:
    def test_selection_mode_exact_members(self):
        assert [m.value for m in CoefficientSelectionMode] == ["SINGLE_SELECT"]


class TestDbInvariants:
    async def test_percentage_column_precision(self, db_session):
        col = CoefficientOption.__table__.c.percentage
        assert col.type.precision == 6
        assert col.type.scale == 3

    async def test_group_owner_code_unique(self, db_session):
        user = await _make_user(db_session, 12001)
        db_session.add(CoefficientGroup(owner_id=user.id, code="DUP", display_name="A"))
        await db_session.commit()
        db_session.add(CoefficientGroup(owner_id=user.id, code="DUP", display_name="B"))
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_option_group_code_unique(self, db_session):
        user = await _make_user(db_session, 12002)
        group = CoefficientGroup(owner_id=user.id, code="G1", display_name="Group")
        db_session.add(group)
        await db_session.commit()
        db_session.add(
            CoefficientOption(
                group_id=group.id, code="DUP", display_name="A", percentage=Decimal("10.000")
            )
        )
        await db_session.commit()
        db_session.add(
            CoefficientOption(
                group_id=group.id, code="DUP", display_name="B", percentage=Decimal("5.000")
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_same_option_code_allowed_across_different_groups(self, db_session):
        user = await _make_user(db_session, 12003)
        g1 = CoefficientGroup(owner_id=user.id, code="G1", display_name="One")
        g2 = CoefficientGroup(owner_id=user.id, code="G2", display_name="Two")
        db_session.add_all([g1, g2])
        await db_session.commit()
        db_session.add(
            CoefficientOption(
                group_id=g1.id, code="SHARED", display_name="A", percentage=Decimal("0.000")
            )
        )
        db_session.add(
            CoefficientOption(
                group_id=g2.id, code="SHARED", display_name="B", percentage=Decimal("0.000")
            )
        )
        await db_session.commit()  # no IntegrityError


class TestPercentageValidation:
    @pytest.mark.parametrize("raw", ["0", "0.000", "10", "-10", "99.999", "500", "-99.999"])
    def test_valid_values_accepted(self, raw):
        result = validate_percentage(Decimal(raw))
        assert result == Decimal(raw)

    def test_zero_is_valid(self):
        assert validate_percentage(Decimal("0")) == Decimal("0")

    def test_positive_is_valid(self):
        assert validate_percentage(Decimal("25")) == Decimal("25")

    def test_negative_is_valid(self):
        assert validate_percentage(Decimal("-15")) == Decimal("-15")

    def test_exactly_minus_100_rejected(self):
        with pytest.raises(PriceCoefficientValidationError):
            validate_percentage(Decimal("-100"))

    def test_below_minus_100_rejected(self):
        with pytest.raises(PriceCoefficientValidationError):
            validate_percentage(Decimal("-150"))

    def test_above_max_rejected(self):
        with pytest.raises(PriceCoefficientValidationError):
            validate_percentage(Decimal("501"))

    def test_at_max_boundary_accepted(self):
        assert validate_percentage(Decimal("500")) == Decimal("500")

    def test_excess_precision_rejected(self):
        with pytest.raises(PriceCoefficientValidationError):
            validate_percentage(Decimal("10.1234"))

    def test_non_finite_rejected(self):
        with pytest.raises(PriceCoefficientValidationError):
            validate_percentage(Decimal("NaN"))

    def test_string_input_coerced_to_decimal(self):
        # Service call sites may pass a raw string from a request body; the
        # validator itself must never touch a binary float.
        assert validate_percentage("12.500") == Decimal("12.500")


class TestGroupCrud:
    async def test_create_group_generates_custom_code(self, db_session):
        user = await _make_user(db_session, 12010)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="Wysokość")
        assert group.code.startswith("CUSTOM_")
        assert group.display_name == "Wysokość"
        assert group.selection_mode == CoefficientSelectionMode.SINGLE_SELECT
        assert group.is_archived is False

    async def test_create_group_requires_display_name(self, db_session):
        user = await _make_user(db_session, 12011)
        service = PriceCoefficientService(db_session)
        with pytest.raises(PriceCoefficientValidationError):
            await service.create_group(user.id, display_name="   ")

    async def test_list_owner_groups_active_default(self, db_session):
        user = await _make_user(db_session, 12012)
        service = PriceCoefficientService(db_session)
        g1 = await service.create_group(user.id, display_name="A")
        g2 = await service.create_group(user.id, display_name="B")
        await service.archive_group(user.id, g2.id)
        groups = await service.list_owner_groups(user.id)
        assert [g.id for g in groups] == [g1.id]

    async def test_list_owner_groups_all(self, db_session):
        user = await _make_user(db_session, 12013)
        service = PriceCoefficientService(db_session)
        g1 = await service.create_group(user.id, display_name="A")
        g2 = await service.create_group(user.id, display_name="B")
        await service.archive_group(user.id, g2.id)
        groups = await service.list_owner_groups(user.id, archived="all")
        assert {g.id for g in groups} == {g1.id, g2.id}

    async def test_update_group_display_name(self, db_session):
        user = await _make_user(db_session, 12014)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="Old")
        updated = await service.update_group(user.id, group.id, display_name="New")
        assert updated.display_name == "New"

    async def test_group_code_immutable_no_update_field(self, db_session):
        user = await _make_user(db_session, 12015)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        original_code = group.code
        # update_group has no `code` parameter at all -- immutability is
        # structural, not merely a validation check.
        await service.update_group(user.id, group.id, display_name="B")
        refreshed = await service.get_owned_group(user.id, group.id)
        assert refreshed.code == original_code

    async def test_archive_then_restore_group(self, db_session):
        user = await _make_user(db_session, 12016)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        archived = await service.archive_group(user.id, group.id)
        assert archived.is_archived is True
        restored = await service.restore_group(user.id, group.id)
        assert restored.is_archived is False

    async def test_archive_group_idempotent(self, db_session):
        user = await _make_user(db_session, 12017)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        await service.archive_group(user.id, group.id)
        again = await service.archive_group(user.id, group.id)
        assert again.is_archived is True

    async def test_get_missing_group_raises(self, db_session):
        user = await _make_user(db_session, 12018)
        service = PriceCoefficientService(db_session)
        import uuid

        with pytest.raises(CoefficientGroupNotFoundError):
            await service.get_owned_group(user.id, uuid.uuid4())


class TestGroupOwnerIsolation:
    async def test_cross_owner_get_raises_not_found(self, db_session):
        owner = await _make_user(db_session, 12020)
        other = await _make_user(db_session, 12021)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(owner.id, display_name="A")
        with pytest.raises(CoefficientGroupNotFoundError):
            await service.get_owned_group(other.id, group.id)

    async def test_cross_owner_update_raises_not_found(self, db_session):
        owner = await _make_user(db_session, 12022)
        other = await _make_user(db_session, 12023)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(owner.id, display_name="A")
        with pytest.raises(CoefficientGroupNotFoundError):
            await service.update_group(other.id, group.id, display_name="Hacked")

    async def test_cross_owner_archive_raises_not_found(self, db_session):
        owner = await _make_user(db_session, 12024)
        other = await _make_user(db_session, 12025)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(owner.id, display_name="A")
        with pytest.raises(CoefficientGroupNotFoundError):
            await service.archive_group(other.id, group.id)

    async def test_duplicate_code_allowed_across_different_owners(self, db_session):
        """(owner_id, code) is the unique scope -- two owners' independently
        generated CUSTOM_* codes could theoretically collide only if the
        UUID-derived generator collided, which the unique-per-owner
        constraint does not itself prevent across owners by design."""
        owner1 = await _make_user(db_session, 12026)
        owner2 = await _make_user(db_session, 12027)
        db_session.add(CoefficientGroup(owner_id=owner1.id, code="SAME", display_name="A"))
        db_session.add(CoefficientGroup(owner_id=owner2.id, code="SAME", display_name="B"))
        await db_session.commit()  # no IntegrityError


class TestOptionCrud:
    async def test_create_option_generates_custom_code(self, db_session):
        user = await _make_user(db_session, 12030)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="Wysokość")
        option = await service.create_option(
            user.id, group.id, display_name="Wysoka", percentage=Decimal("20")
        )
        assert option.code.startswith("CUSTOM_")
        assert option.group_id == group.id
        assert option.percentage == Decimal("20")
        assert option.is_base is False

    async def test_create_option_rejects_invalid_percentage(self, db_session):
        user = await _make_user(db_session, 12031)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        with pytest.raises(PriceCoefficientValidationError):
            await service.create_option(
                user.id, group.id, display_name="Bad", percentage=Decimal("-100")
            )

    async def test_create_option_on_archived_group_rejected(self, db_session):
        user = await _make_user(db_session, 12032)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        await service.archive_group(user.id, group.id)
        with pytest.raises(PriceCoefficientValidationError):
            await service.create_option(
                user.id, group.id, display_name="X", percentage=Decimal("0")
            )

    async def test_options_ordered_by_position(self, db_session):
        user = await _make_user(db_session, 12033)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        first = await service.create_option(
            user.id, group.id, display_name="First", percentage=Decimal("0")
        )
        second = await service.create_option(
            user.id, group.id, display_name="Second", percentage=Decimal("10")
        )
        refreshed = await service.get_owned_group(user.id, group.id, with_options=True)
        assert [o.id for o in refreshed.options] == [first.id, second.id]

    async def test_update_option_percentage(self, db_session):
        user = await _make_user(db_session, 12034)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        option = await service.create_option(
            user.id, group.id, display_name="X", percentage=Decimal("10")
        )
        updated = await service.update_option(
            user.id, option.id, percentage=Decimal("15")
        )
        assert updated.percentage == Decimal("15")

    async def test_update_option_display_name(self, db_session):
        user = await _make_user(db_session, 12035)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        option = await service.create_option(
            user.id, group.id, display_name="Old", percentage=Decimal("0")
        )
        updated = await service.update_option(user.id, option.id, display_name="New")
        assert updated.display_name == "New"

    async def test_option_code_immutable_no_update_field(self, db_session):
        user = await _make_user(db_session, 12036)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        option = await service.create_option(
            user.id, group.id, display_name="X", percentage=Decimal("0")
        )
        original_code = option.code
        await service.update_option(user.id, option.id, display_name="Y")
        refreshed = await service.get_owned_option(user.id, option.id)
        assert refreshed.code == original_code

    async def test_archive_then_restore_option(self, db_session):
        user = await _make_user(db_session, 12037)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        option = await service.create_option(
            user.id, group.id, display_name="X", percentage=Decimal("0")
        )
        archived = await service.archive_option(user.id, option.id)
        assert archived.is_archived is True
        restored = await service.restore_option(user.id, option.id)
        assert restored.is_archived is False

    async def test_get_missing_option_raises(self, db_session):
        user = await _make_user(db_session, 12038)
        service = PriceCoefficientService(db_session)
        import uuid

        with pytest.raises(CoefficientOptionNotFoundError):
            await service.get_owned_option(user.id, uuid.uuid4())

    async def test_cross_owner_option_access_raises_not_found(self, db_session):
        owner = await _make_user(db_session, 12039)
        other = await _make_user(db_session, 12040)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(owner.id, display_name="A")
        option = await service.create_option(
            owner.id, group.id, display_name="X", percentage=Decimal("0")
        )
        with pytest.raises(CoefficientOptionNotFoundError):
            await service.get_owned_option(other.id, option.id)
        with pytest.raises(CoefficientOptionNotFoundError):
            await service.update_option(other.id, option.id, percentage=Decimal("99"))
        with pytest.raises(CoefficientOptionNotFoundError):
            await service.archive_option(other.id, option.id)

    async def test_cannot_attach_option_to_another_owners_group(self, db_session):
        owner = await _make_user(db_session, 12041)
        other = await _make_user(db_session, 12042)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(owner.id, display_name="A")
        with pytest.raises(CoefficientGroupNotFoundError):
            await service.create_option(
                other.id, group.id, display_name="X", percentage=Decimal("0")
            )


class TestBaseOptionInvariant:
    async def test_first_base_option_allowed(self, db_session):
        user = await _make_user(db_session, 12050)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        option = await service.create_option(
            user.id, group.id, display_name="Normal", percentage=Decimal("0"), is_base=True
        )
        assert option.is_base is True

    async def test_second_base_option_atomically_replaces_first(self, db_session):
        """Explicitly documented policy (docs/stage-12-architecture.md Sec 6):
        setting is_base=True on a new/updated option atomically clears any
        other active is_base option in the same group -- never rejected,
        never leaves two simultaneously true."""
        user = await _make_user(db_session, 12051)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        first = await service.create_option(
            user.id, group.id, display_name="First", percentage=Decimal("0"), is_base=True
        )
        second = await service.create_option(
            user.id, group.id, display_name="Second", percentage=Decimal("10"), is_base=True
        )
        refreshed_first = await service.get_owned_option(user.id, first.id)
        refreshed_second = await service.get_owned_option(user.id, second.id)
        assert refreshed_first.is_base is False
        assert refreshed_second.is_base is True

    async def test_update_option_to_base_replaces_previous_base(self, db_session):
        user = await _make_user(db_session, 12052)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        first = await service.create_option(
            user.id, group.id, display_name="First", percentage=Decimal("0"), is_base=True
        )
        second = await service.create_option(
            user.id, group.id, display_name="Second", percentage=Decimal("10")
        )
        await service.update_option(user.id, second.id, is_base=True)
        refreshed_first = await service.get_owned_option(user.id, first.id)
        refreshed_second = await service.get_owned_option(user.id, second.id)
        assert refreshed_first.is_base is False
        assert refreshed_second.is_base is True

    async def test_at_most_one_active_base_never_two(self, db_session):
        user = await _make_user(db_session, 12053)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        await service.create_option(
            user.id, group.id, display_name="One", percentage=Decimal("0"), is_base=True
        )
        await service.create_option(
            user.id, group.id, display_name="Two", percentage=Decimal("10"), is_base=True
        )
        await service.create_option(
            user.id, group.id, display_name="Three", percentage=Decimal("20"), is_base=True
        )
        refreshed = await service.get_owned_group(user.id, group.id, with_options=True)
        base_options = [o for o in refreshed.options if o.is_base]
        assert len(base_options) == 1
        assert base_options[0].display_name == "Three"

    async def test_zero_percent_non_base_option_remains_possible(self, db_session):
        """A 0% option that is NOT the declared base must remain representable
        (docs/stage-12-architecture.md Sec 4: is_base is not inferred from
        percentage == 0)."""
        user = await _make_user(db_session, 12054)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        base = await service.create_option(
            user.id, group.id, display_name="Base", percentage=Decimal("0"), is_base=True
        )
        other_zero = await service.create_option(
            user.id, group.id, display_name="AlsoZero", percentage=Decimal("0")
        )
        assert base.is_base is True
        assert other_zero.is_base is False
        assert other_zero.percentage == Decimal("0")

    async def test_archiving_base_option_does_not_promote_another(self, db_session):
        """Explicit application only (D10): archiving the base leaves the
        group with zero active base options -- nothing is auto-promoted."""
        user = await _make_user(db_session, 12055)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        base = await service.create_option(
            user.id, group.id, display_name="Base", percentage=Decimal("0"), is_base=True
        )
        other = await service.create_option(
            user.id, group.id, display_name="Other", percentage=Decimal("10")
        )
        await service.archive_option(user.id, base.id)
        refreshed_base = await service.get_owned_option(user.id, base.id)
        refreshed_other = await service.get_owned_option(user.id, other.id)
        assert refreshed_base.is_archived is True
        assert refreshed_base.is_base is True  # historical state preserved
        assert refreshed_other.is_base is False  # never auto-promoted

    async def test_archived_base_option_not_touched_by_a_new_base_selection(self, db_session):
        """An archived option's historical is_base state is not retroactively
        rewritten by a new active selection elsewhere in the group."""
        user = await _make_user(db_session, 12056)
        service = PriceCoefficientService(db_session)
        group = await service.create_group(user.id, display_name="A")
        old_base = await service.create_option(
            user.id, group.id, display_name="OldBase", percentage=Decimal("0"), is_base=True
        )
        await service.archive_option(user.id, old_base.id)
        new_option = await service.create_option(
            user.id, group.id, display_name="New", percentage=Decimal("10"), is_base=True
        )
        refreshed_old = await service.get_owned_option(user.id, old_base.id)
        assert refreshed_old.is_base is True  # untouched, still archived
        assert new_option.is_base is True
