"""Focused Stage 9B tests: editable Price Book backend domain.

Covers the PriceItem model/DB invariants, lazy per-owner seed bootstrap,
CUSTOM_* code generation and immutability, the quality hint reuse of the
Stage 6 ``qualitylevel`` enum, and owner isolation. There is no HTTP API in
Stage 9B, so every assertion exercises the domain service directly.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.data.price_book_seed import (
    LEGACY_GENERIC_CODES,
    PriceItemSeed,
    build_approved_price_book_items,
)
from app.domain.exceptions import PriceBookValidationError, PriceItemNotFoundError
from app.domain.services.price_book_service import (
    PriceBookService,
    validate_currency,
    validate_price,
)
from app.models import User
from app.models.checklist import QualityLevel
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


def _custom_kwargs(**overrides) -> dict:
    kwargs = dict(
        category=PriceCategory.PAINTING,
        unit=PriceUnit.M2,
        price=Decimal("6.50"),
        display_name="Malowanie farbą lateksową",
    )
    kwargs.update(overrides)
    return kwargs


class TestModelEnums:
    def test_price_unit_exact_members(self):
        assert [u.value for u in PriceUnit] == ["M2", "LM", "PCS", "HOUR", "DAY", "FLAT"]

    def test_price_category_exact_members(self):
        assert [c.value for c in PriceCategory] == [
            "PREPARATION",
            "SKIM_COAT",
            "PLASTER",
            "DRYWALL",
            "PAINTING",
            "GLASS_FIBER",
            "MICROCEMENT",
            "DECORATIVE",
            "REVEAL",
            "MATERIAL",
            "OTHER",
        ]

    def test_price_scope_exact_members(self):
        assert [s.value for s in PriceScope] == [
            "LABOR",
            "MATERIAL",
            "LABOR_AND_MATERIAL",
        ]


class TestDbInvariants:
    async def test_currency_stored_as_string_not_enum(self, db_session):
        col = PriceItem.__table__.c.currency
        assert str(col.type) == "VARCHAR(3)"

    async def test_price_column_precision(self, db_session):
        col = PriceItem.__table__.c.price
        assert col.type.precision == 12
        assert col.type.scale == 2

    async def test_zero_price_accepted_and_persisted(self, db_session):
        user = await _make_user(db_session, 1001)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(
            user.id,
            **_custom_kwargs(price=Decimal("0.00"), display_name="Do ustalenia"),
        )
        assert item.price == Decimal("0.00")

    def test_negative_price_rejected(self):
        with pytest.raises(PriceBookValidationError, match="greater than or equal to 0"):
            validate_price(Decimal("-0.01"))

    def test_more_than_two_decimals_rejected(self):
        with pytest.raises(PriceBookValidationError, match="at most 2 decimal places"):
            validate_price(Decimal("1.234"))

    def test_valid_price_returned_unchanged(self):
        value = Decimal("12.30")
        assert validate_price(value) is value  # no quantize/round/truncate
        assert validate_price(Decimal("0")) == Decimal("0")

    def test_non_decimal_price_coerced_to_decimal(self):
        assert validate_price("1.50") == Decimal("1.50")

    async def test_duplicate_owner_code_rejected(self, db_session):
        user = await _make_user(db_session, 1002)
        db_session.add(
            PriceItem(
                owner_id=user.id,
                code="CUSTOM_DUP00000001",
                category=PriceCategory.PAINTING,
                unit=PriceUnit.M2,
                price=Decimal("1.00"),
            )
        )
        await db_session.commit()
        db_session.add(
            PriceItem(
                owner_id=user.id,
                code="CUSTOM_DUP00000001",
                category=PriceCategory.PAINTING,
                unit=PriceUnit.M2,
                price=Decimal("2.00"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_same_code_allowed_for_different_owners(self, db_session):
        user1 = await _make_user(db_session, 1003)
        user2 = await _make_user(db_session, 1004)
        for owner in (user1.id, user2.id):
            db_session.add(
                PriceItem(
                    owner_id=owner,
                    code="CENNIK_TEST_SHARED",
                    category=PriceCategory.PAINTING,
                    unit=PriceUnit.M2,
                    price=Decimal("1.00"),
                )
            )
        await db_session.commit()  # must not raise

    async def test_archive_persists_after_requery(self, db_session):
        user = await _make_user(db_session, 1005)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(user.id, **_custom_kwargs())
        await service.update_item(user.id, item.id, is_archived=True)

        assert item.id not in {i.id for i in await service.list_owner_items(user.id)}
        archived = await service.list_owner_items(user.id, archived="archived")
        assert item.id in {i.id for i in archived}

        fetched = (
            await db_session.execute(
                select(PriceItem)
                .where(PriceItem.id == item.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert fetched.is_archived is True

    def test_owner_foreign_key_ondelete_cascade(self):
        owner_col = PriceItem.__table__.c.owner_id
        fks = list(owner_col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].column.table.name == "users"
        assert fks[0].column.name == "id"
        assert fks[0].ondelete == "CASCADE"

    def test_unique_owner_code_constraint_defined(self):
        names = {c.name for c in PriceItem.__table__.constraints}
        assert "uq_price_items_owner_code" in names

    def test_owner_archived_index_defined(self):
        assert "ix_price_items_owner_archived" in {i.name for i in PriceItem.__table__.indexes}


class TestValidation:
    def test_currency_pln_only(self):
        validate_currency("PLN")
        with pytest.raises(PriceBookValidationError, match="only PLN"):
            validate_currency("EUR")

    async def test_custom_item_requires_display_name(self, db_session):
        user = await _make_user(db_session, 2001)
        service = PriceBookService(db_session)
        with pytest.raises(PriceBookValidationError, match="display_name"):
            await service.create_custom_item(user.id, **_custom_kwargs(display_name="   "))

    async def test_seeded_rows_use_name_key_and_null_price(self, db_session):
        user = await _make_user(db_session, 2002)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(user.id)
        items = await service.list_owner_items(user.id)
        assert len(items) == 44
        for item in items:
            assert item.name_key is not None
            assert item.display_name is None  # seeded rows localize via name_key
            assert item.price is None  # 9E.7: NULL = owner price not set yet
            assert item.code.startswith("CENNIK_")


class TestSeedBootstrap:
    async def test_first_materialization_creates_every_seed(self, db_session):
        user = await _make_user(db_session, 3001)
        service = PriceBookService(db_session)
        created = await service.ensure_owner_catalog(user.id)
        assert {i.code for i in created} == {s.code for s in build_approved_price_book_items()}
        assert len(await service.list_owner_items(user.id)) == 44

    async def test_second_materialization_is_idempotent(self, db_session):
        user = await _make_user(db_session, 3002)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(user.id)
        assert await service.ensure_owner_catalog(user.id) == []
        assert len(await service.list_owner_items(user.id)) == 44

    async def test_owner_edit_preserved_on_rematerialize(self, db_session):
        user = await _make_user(db_session, 3003)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(user.id)
        prep = next(
            i for i in await service.list_owner_items(user.id)
            if i.code == "CENNIK_PREP_WALLP-01"
        )
        await service.update_item(user.id, prep.id, price=Decimal("12.50"))
        await service.ensure_owner_catalog(user.id)  # must not overwrite the edit
        refetched = await service.get_owned_item(user.id, prep.id)
        assert refetched.price == Decimal("12.50")

    async def test_new_seed_inserts_only_the_missing_row(self, db_session, monkeypatch):
        user = await _make_user(db_session, 3004)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(user.id)

        baseline = build_approved_price_book_items()
        extra = PriceItemSeed(
            code="CENNIK_PREP_EXTRA_M2",
            category=PriceCategory.PREPARATION,
            unit=PriceUnit.M2,
            price="9.99",
            name_key="pricebook.seed.prep_extra_m2",
        )
        monkeypatch.setattr(
            "app.domain.services.price_book_service.build_approved_price_book_items",
            lambda: [*baseline, extra],
        )
        created = await service.ensure_owner_catalog(user.id)
        assert [i.code for i in created] == ["CENNIK_PREP_EXTRA_M2"]
        assert len(await service.list_owner_items(user.id)) == 45

    async def test_no_cross_owner_leakage(self, db_session):
        user1 = await _make_user(db_session, 3005)
        user2 = await _make_user(db_session, 3006)
        service1 = PriceBookService(db_session)
        service2 = PriceBookService(db_session)

        await service1.ensure_owner_catalog(user1.id)
        assert await service2.list_owner_items(user2.id) == []

        await service2.ensure_owner_catalog(user2.id)
        owner1_ids = {i.id for i in await service1.list_owner_items(user1.id)}
        owner2_ids = {i.id for i in await service2.list_owner_items(user2.id)}
        assert owner1_ids.isdisjoint(owner2_ids)


class TestCustomCode:
    async def test_custom_code_shape(self, db_session):
        user = await _make_user(db_session, 4001)
        service = PriceBookService(db_session)
        code = await service.generate_custom_code(user.id)
        assert code.startswith("CUSTOM_")
        assert len(code) == len("CUSTOM_") + 12

    async def test_generated_codes_do_not_collide(self, db_session):
        user = await _make_user(db_session, 4002)
        service = PriceBookService(db_session)
        codes = {await service.generate_custom_code(user.id) for _ in range(50)}
        assert len(codes) == 50

    async def test_custom_rows_persist_generated_code(self, db_session):
        user = await _make_user(db_session, 4003)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(user.id, **_custom_kwargs())
        assert item.code.startswith("CUSTOM_")
        assert (await service.get_owned_item(user.id, item.id)).code == item.code

    async def test_code_immutable_through_update_path(self, db_session):
        user = await _make_user(db_session, 4004)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(user.id, **_custom_kwargs())
        original_code = item.code
        await service.update_item(
            user.id,
            item.id,
            price=Decimal("9.99"),
            display_name="Nowa nazwa",
            category=PriceCategory.SKIM_COAT,
        )
        fetched = (
            await db_session.execute(
                select(PriceItem)
                .where(PriceItem.id == item.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert fetched.code == original_code
        assert fetched.display_name == "Nowa nazwa"


class TestQualityHint:
    async def test_quality_level_nullable(self, db_session):
        user = await _make_user(db_session, 5001)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(user.id, **_custom_kwargs())
        assert item.quality_level is None

    async def test_quality_level_persisted(self, db_session):
        user = await _make_user(db_session, 5002)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(
            user.id, **_custom_kwargs(quality_level=QualityLevel.Q3)
        )
        assert item.quality_level == QualityLevel.Q3
        fetched = (
            await db_session.execute(
                select(PriceItem)
                .where(PriceItem.id == item.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert fetched.quality_level == QualityLevel.Q3

    def test_quality_level_reuses_stage6_enum(self):
        col = PriceItem.__table__.c.quality_level
        assert col.type.enum_class is QualityLevel  # not a duplicated Python enum
        assert col.type.name == "qualitylevel"  # same DB type owned by revision 0011


class TestOwnership:
    async def test_get_owned_item_owner_scoped(self, db_session):
        user1 = await _make_user(db_session, 6001)
        user2 = await _make_user(db_session, 6002)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(user1.id, **_custom_kwargs())
        assert (await service.get_owned_item(user1.id, item.id)).id == item.id
        with pytest.raises(PriceItemNotFoundError):
            await service.get_owned_item(user2.id, item.id)

    async def test_update_item_owner_scoped(self, db_session):
        user1 = await _make_user(db_session, 6003)
        user2 = await _make_user(db_session, 6004)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(user1.id, **_custom_kwargs())
        with pytest.raises(PriceItemNotFoundError):
            await service.update_item(user2.id, item.id, price=Decimal("9.99"))

    async def test_list_owner_items_owner_scoped(self, db_session):
        user1 = await _make_user(db_session, 6005)
        user2 = await _make_user(db_session, 6006)
        service = PriceBookService(db_session)
        await service.create_custom_item(user1.id, **_custom_kwargs())
        assert len(await service.list_owner_items(user2.id)) == 0