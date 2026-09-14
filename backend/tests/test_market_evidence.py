"""Focused Stage 9E.6A tests: price market evidence foundation.

Covers the PriceMarketReference / PriceSource model invariants, service input
validation (Decimal exactness, exactly-one quoting mode, unit/currency/region
contracts, checked_at), owner isolation through the parent PriceItem, the
read-only API surface, and the invariant that evidence operations never mutate
PriceItem.price.
"""
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.domain.exceptions import (
    MarketReferenceNotFoundError,
    PriceBookValidationError,
    PriceItemNotFoundError,
)
from app.domain.services.price_book_service import (
    PriceBookService,
    market_source_is_comparable,
    validate_region,
    validate_source_payload,
)
from app.models import User
from app.models.market_evidence import PriceMarketReference, PriceSource, SourceType
from app.models.price_item import PriceItem, PriceUnit

from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 111111111,
    "username": "owner",
    "first_name": "Owner",
    "last_name": "User",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 222222222,
    "username": "other",
    "first_name": "Other",
    "last_name": "Person",
    "language_code": "pl",
}

PAINT_CODE = "CENNIK_PAINT_GENERIC_M2"
CHECKED_AT = datetime(2026, 9, 14, 9, 0, 0, tzinfo=timezone.utc)
EARLIER_CHECKED_AT = datetime(2026, 9, 1, 9, 0, 0, tzinfo=timezone.utc)


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    init_data = make_telegram_init_data(user_dict)
    resp = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _seed_item(db, service: PriceBookService, owner_id: uuid.UUID) -> PriceItem:
    await service.ensure_owner_catalog(owner_id)
    items = await service.list_owner_items(owner_id)
    return next(i for i in items if i.code == PAINT_CODE)


def _source(**overrides) -> dict:
    payload = dict(
        source_name="Cennik wykończeniowy Firma X",
        source_type=SourceType.CONTRACTOR_PRICE_LIST,
        checked_at=CHECKED_AT,
        quoted_price_single=Decimal("15.00"),
    )
    payload.update(overrides)
    return payload


async def _create_evidence(
    db,
    owner_id: uuid.UUID,
    item: PriceItem,
    **ref_overrides,
) -> tuple[PriceBookService, PriceMarketReference]:
    service = PriceBookService(db)
    kwargs = dict(
        region="Kraków",
        unit=item.unit,
        market_min=Decimal("12.00"),
        market_max=Decimal("18.50"),
        checked_at=CHECKED_AT,
        sources=[_source()],
    )
    kwargs.update(ref_overrides)
    reference = await service.create_market_reference_with_sources(
        owner_id, item.id, **kwargs
    )
    return service, reference


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Model / DB invariants
# ---------------------------------------------------------------------------

def test_source_type_exact_members():
    assert [t.value for t in SourceType] == [
        "CONTRACTOR_PRICE_LIST",
        "MARKETPLACE",
        "MANUFACTURER",
        "MATERIAL_STORE",
        "INDUSTRY_ARTICLE",
        "OWN_PRICE",
        "OTHER",
    ]


def test_reference_unit_reuses_priceunit_enum():
    col = PriceMarketReference.__table__.c.unit
    assert col.type.name == "priceunit"
    assert col.type.enum_class is PriceUnit


def test_reference_money_columns_precision():
    for name in ("market_min", "market_max", "reference_price"):
        col = PriceMarketReference.__table__.c[name]
        assert col.type.precision == 12
        assert col.type.scale == 2
    for name in ("quoted_price_min", "quoted_price_max", "quoted_price_single"):
        col = PriceSource.__table__.c[name]
        assert col.type.precision == 12
        assert col.type.scale == 2


def test_reference_item_cascade_defined():
    col = PriceMarketReference.__table__.c.price_item_id
    fk = next(iter(col.foreign_keys))
    assert fk.column.table.name == "price_items"
    assert fk.ondelete == "CASCADE"


def test_source_reference_cascade_defined():
    col = PriceSource.__table__.c.market_reference_id
    fk = next(iter(col.foreign_keys))
    assert fk.column.table.name == "price_market_references"
    assert fk.ondelete == "CASCADE"


# ---------------------------------------------------------------------------
# MODEL / SERVICE — create + read
# ---------------------------------------------------------------------------

async def test_create_single_source_reference_persists(db_session):
    owner = await _make_user(db_session, 101)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(
        db_session, owner.id, item, sources=[_source(quoted_price_single=Decimal("15.00"))]
    )
    assert reference.region == "Kraków"
    assert reference.unit == item.unit
    assert reference.currency == "PLN"
    assert reference.market_min == Decimal("12.00")
    assert reference.market_max == Decimal("18.50")
    assert _utc(reference.checked_at) == CHECKED_AT
    assert [s.quoted_price_single for s in reference.sources] == [Decimal("15.00")]
    assert [s.quoted_price_min for s in reference.sources] == [None]
    assert [s.quoted_price_max for s in reference.sources] == [None]


async def test_create_range_source_reference_persists(db_session):
    owner = await _make_user(db_session, 102)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(
        db_session,
        owner.id,
        item,
        sources=[
            _source(
                quoted_price_single=None,
                quoted_price_min=Decimal("10.00"),
                quoted_price_max=Decimal("20.00"),
            )
        ],
    )
    source = reference.sources[0]
    assert source.quoted_price_min == Decimal("10.00")
    assert source.quoted_price_max == Decimal("20.00")
    assert source.quoted_price_single is None


async def test_create_qualitative_reference_persists(db_session):
    owner = await _make_user(db_session, 103)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(
        db_session,
        owner.id,
        item,
        sources=[
            _source(
                source_type=SourceType.INDUSTRY_ARTICLE,
                source_url="https://example.com/artykul",
                quoted_price_single=None,
                note="  Ceny uzależnione od sezonu; zakres podano wg artykułu  ",
            )
        ],
    )
    source = reference.sources[0]
    assert source.quoted_price_single is None
    assert source.quoted_price_min is None
    assert source.quoted_price_max is None
    assert source.note == "Ceny uzależnione od sezonu; zakres podano wg artykułu"
    assert source.quoted_unit is None


async def test_checked_at_naive_assumed_utc(db_session):
    owner = await _make_user(db_session, 104)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(
        db_session, owner.id, item, checked_at=datetime(2026, 9, 13, 12, 0, 0)
    )
    assert _utc(reference.checked_at) == datetime(
        2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc
    )


async def test_reference_decimal_exactness_preserved(db_session):
    owner = await _make_user(db_session, 105)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(
        db_session,
        owner.id,
        item,
        market_min=Decimal("12.50"),
        market_max=Decimal("18.25"),
        reference_price=Decimal("15.75"),
    )
    fetched = (await service.get_market_references(owner.id, item.id))[0]
    assert isinstance(fetched.market_min, Decimal)
    assert fetched.market_min == Decimal("12.50")
    assert fetched.market_max == Decimal("18.25")
    assert fetched.reference_price == Decimal("15.75")

async def test_reject_negative_market_min(db_session):
    owner = await _make_user(db_session, 106)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    with pytest.raises(PriceBookValidationError, match="greater than or equal to 0"):
        await _create_evidence(db_session, owner.id, item, market_min=Decimal("-1.00"))


async def test_reject_more_than_two_decimal_places(db_session):
    owner = await _make_user(db_session, 107)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    with pytest.raises(PriceBookValidationError, match="at most 2 decimal places"):
        await _create_evidence(db_session, owner.id, item, market_min=Decimal("12.345"))


async def test_reject_nan_and_infinity(db_session):
    owner = await _make_user(db_session, 108)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(PriceBookValidationError, match="finite"):
            await _create_evidence(db_session, owner.id, item, market_min=bad)


async def test_reject_min_exceeds_max(db_session):
    owner = await _make_user(db_session, 109)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    with pytest.raises(PriceBookValidationError, match="market_min must not exceed"):
        await _create_evidence(
            db_session, owner.id, item, market_min=Decimal("30.00"), market_max=Decimal("20.00")
        )


async def test_reject_unit_mismatch(db_session):
    owner = await _make_user(db_session, 110)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)  # M2 item
    assert item.unit == PriceUnit.M2
    with pytest.raises(PriceBookValidationError, match="unit must match"):
        await _create_evidence(db_session, owner.id, item, unit=PriceUnit.LM)


async def test_reject_non_pln_currency(db_session):
    owner = await _make_user(db_session, 111)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    with pytest.raises(PriceBookValidationError, match="only PLN"):
        await _create_evidence(db_session, owner.id, item, currency="EUR")


async def test_reject_region_outside_mvp_set():
    with pytest.raises(PriceBookValidationError, match="region must be one of"):
        validate_region("Warszawa")
    assert validate_region("Kraków / Małopolskie") == "Kraków / Małopolskie"


async def test_reject_empty_sources(db_session):
    owner = await _make_user(db_session, 112)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    with pytest.raises(PriceBookValidationError, match="at least one source"):
        await _create_evidence(db_session, owner.id, item, sources=[])


async def test_reject_missing_checked_at(db_session):
    owner = await _make_user(db_session, 113)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    with pytest.raises(PriceBookValidationError, match="checked_at"):
        kwargs = dict(
            region="Kraków",
            unit=item.unit,
            market_min=Decimal("12.00"),
            market_max=Decimal("18.50"),
            sources=[_source()],
        )
        await service.create_market_reference_with_sources(owner.id, item.id, **kwargs)


async def test_get_market_references_orders_newest_first(db_session):
    owner = await _make_user(db_session, 114)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, _ = await _create_evidence(
        db_session, owner.id, item, checked_at=EARLIER_CHECKED_AT, region="Małopolskie"
    )
    _, _ = await _create_evidence(db_session, owner.id, item, checked_at=CHECKED_AT)
    references = await service.get_market_references(owner.id, item.id)
    assert [_utc(r.checked_at) for r in references] == [CHECKED_AT, EARLIER_CHECKED_AT]
    assert [r.region for r in references] == ["Kraków", "Małopolskie"]


# ---------------------------------------------------------------------------
# MODEL / SERVICE — update (re-check in place)
# ---------------------------------------------------------------------------

async def test_update_market_reference_recheck_in_place(db_session):
    owner = await _make_user(db_session, 201)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(db_session, owner.id, item)
    new_checked = datetime(2026, 10, 1, 8, 0, 0, tzinfo=timezone.utc)
    updated = await service.update_market_reference(
        owner.id,
        reference.id,
        market_min=Decimal("13.00"),
        market_max=Decimal("19.00"),
        reference_price=Decimal("16.00"),
        methodology_note="Re-check after 2026 Q3 quotes",
        checked_at=new_checked,
    )
    assert updated.market_min == Decimal("13.00")
    assert updated.market_max == Decimal("19.00")
    assert updated.reference_price == Decimal("16.00")
    assert updated.methodology_note == "Re-check after 2026 Q3 quotes"
    assert _utc(updated.checked_at) == new_checked
    assert len(updated.sources) == 1  # evidence preserved when sources omitted


async def test_update_market_reference_replaces_sources(db_session):
    owner = await _make_user(db_session, 202)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(db_session, owner.id, item)
    updated = await service.update_market_reference(
        owner.id,
        reference.id,
        market_min=Decimal("13.00"),
        market_max=Decimal("19.00"),
        checked_at=CHECKED_AT,
        sources=[
            _source(source_name="Nowe źródło A", quoted_price_single=Decimal("16.00")),
            _source(source_name="Nowe źródło B", quoted_price_single=Decimal("17.00")),
        ],
    )
    assert [s.source_name for s in updated.sources] == ["Nowe źródło A", "Nowe źródło B"]
    refetched = (await service.get_market_references(owner.id, item.id))[0]
    assert [s.source_name for s in refetched.sources] == ["Nowe źródło A", "Nowe źródło B"]


async def test_update_foreign_reference_not_found(db_session):
    owner = await _make_user(db_session, 203)
    other = await _make_user(db_session, 204)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(db_session, owner.id, item)
    with pytest.raises(MarketReferenceNotFoundError):
        await service.update_market_reference(
            other.id,
            reference.id,
            market_min=Decimal("9.00"),
            market_max=Decimal("11.00"),
            checked_at=CHECKED_AT,
        )


# ---------------------------------------------------------------------------
# MODEL / SERVICE — archive / cascade
# ---------------------------------------------------------------------------

async def test_archive_does_not_destroy_evidence(db_session):
    owner = await _make_user(db_session, 301)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    await _create_evidence(db_session, owner.id, item)
    await service.archive_item(owner.id, item.id)
    references = await service.get_market_references(owner.id, item.id)
    assert len(references) == 1
    assert len(references[0].sources) == 1
    await service.restore_item(owner.id, item.id)
    assert len(await service.get_market_references(owner.id, item.id)) == 1


async def test_db_level_item_delete_cascades_evidence(db_session):
    owner = await _make_user(db_session, 302)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(
        db_session, owner.id, item, sources=[_source(), _source()]
    )
    reference_id = reference.id
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(PriceSource)
            .where(PriceSource.market_reference_id == reference_id)
        )
    ).scalar_one() == 2
    await db_session.delete(item)
    await db_session.commit()
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(PriceMarketReference)
            .where(PriceMarketReference.price_item_id == item.id)
        )
    ).scalar_one() == 0
    assert (
        await db_session.execute(
            select(func.count())
            .select_from(PriceSource)
            .where(PriceSource.market_reference_id == reference_id)
        )
    ).scalar_one() == 0


# ---------------------------------------------------------------------------
# SOURCE VALIDATION (exactly one quoting mode)
# ---------------------------------------------------------------------------

def test_validate_source_valid_single():
    result = validate_source_payload(
        dict(
            source_name="Allegro Usługi",
            source_type=SourceType.MARKETPLACE,
            checked_at=CHECKED_AT,
            quoted_price_single=Decimal("24.50"),
            quoted_unit=PriceUnit.M2,
            source_url="https://allegro.pl/oferta",
        )
    )
    assert result["quoted_price_single"] == Decimal("24.50")
    assert result["quoted_price_min"] is None
    assert result["quoted_price_max"] is None


def test_validate_source_valid_range():
    result = validate_source_payload(
        dict(
            source_name="store-wykonczeniowy-krakow.pl",
            source_type="MATERIAL_STORE",
            checked_at=CHECKED_AT,
            quoted_price_min=Decimal("8.00"),
            quoted_price_max=Decimal("12.00"),
        )
    )
    assert result["quoted_price_min"] == Decimal("8.00")
    assert result["quoted_price_max"] == Decimal("12.00")
    assert result["quoted_price_single"] is None


def test_validate_source_valid_qualitative():
    result = validate_source_payload(
        dict(
            source_name="Artykuł branżowy",
            source_type=SourceType.INDUSTRY_ARTICLE,
            checked_at=CHECKED_AT,
            note="Wycena zależna od zakresu; brak cen jednostkowych",
        )
    )
    assert result["note"] == "Wycena zależna od zakresu; brak cen jednostkowych"


def test_validate_source_rejects_single_and_range_together():
    with pytest.raises(PriceBookValidationError, match="exactly one quoting mode"):
        validate_source_payload(
            dict(
                source_name="X",
                source_type=SourceType.OTHER,
                checked_at=CHECKED_AT,
                quoted_price_single=Decimal("10.00"),
                quoted_price_min=Decimal("8.00"),
            )
        )


def test_validate_source_rejects_half_range():
    with pytest.raises(PriceBookValidationError, match="requires both"):
        validate_source_payload(
            dict(
                source_name="X",
                source_type=SourceType.OTHER,
                checked_at=CHECKED_AT,
                quoted_price_max=Decimal("12.00"),
            )
        )


def test_validate_source_rejects_range_min_exceeds_max():
    with pytest.raises(PriceBookValidationError, match="must not exceed"):
        validate_source_payload(
            dict(
                source_name="X",
                source_type=SourceType.OTHER,
                checked_at=CHECKED_AT,
                quoted_price_min=Decimal("15.00"),
                quoted_price_max=Decimal("10.00"),
            )
        )


def test_validate_source_rejects_empty_qualitative():
    with pytest.raises(PriceBookValidationError, match="QUALITATIVE source requires"):
        validate_source_payload(
            dict(source_name="X", source_type=SourceType.OTHER, checked_at=CHECKED_AT)
        )


def test_validate_source_rejects_blank_name():
    with pytest.raises(PriceBookValidationError, match="source_name"):
        validate_source_payload(
            dict(source_name="   ", source_type=SourceType.OTHER, checked_at=CHECKED_AT)
        )


def test_validate_source_rejects_invalid_source_type():
    with pytest.raises(PriceBookValidationError, match="source type"):
        validate_source_payload(
            dict(source_name="X", source_type="SHADY_VENDOR", checked_at=CHECKED_AT)
        )


def test_validate_source_rejects_numeric_precision():
    with pytest.raises(PriceBookValidationError, match="at most 2 decimal places"):
        validate_source_payload(
            dict(
                source_name="X",
                source_type=SourceType.OTHER,
                checked_at=CHECKED_AT,
                quoted_price_single=Decimal("10.999"),
            )
        )


async def test_own_price_source_without_url_accepted(db_session):
    owner = await _make_user(db_session, 401)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    _, reference = await _create_evidence(
        db_session,
        owner.id,
        item,
        sources=[
            _source(
                source_type=SourceType.OWN_PRICE,
                quoted_price_single=None,
                note="Cena własna z ostatniego kosztorysu",
            )
        ],
    )
    source = reference.sources[0]
    assert source.source_url is None


async def test_no_automatic_unit_conversion(db_session):
    owner = await _make_user(db_session, 402)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)  # M2
    _, reference = await _create_evidence(
        db_session,
        owner.id,
        item,
        sources=[
            _source(
                source_name="Cennik za metr bieżący",
                quoted_price_single=Decimal("10.00"),
                quoted_unit=PriceUnit.LM,
            )
        ],
    )
    source = reference.sources[0]
    # The LM quote is preserved as-is, never converted to M2.
    assert source.quoted_price_single == Decimal("10.00")
    assert source.quoted_unit == PriceUnit.LM
    assert market_source_is_comparable(item.unit, dict(quoted_unit=source.quoted_unit)) is False
    assert market_source_is_comparable(item.unit, dict(quoted_unit=PriceUnit.M2)) is True
    assert market_source_is_comparable(item.unit, dict(quoted_unit=None)) is True


# ---------------------------------------------------------------------------
# OWNERSHIP
# ---------------------------------------------------------------------------

async def test_owner_reads_own_references(db_session):
    owner = await _make_user(db_session, 501)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    await _create_evidence(db_session, owner.id, item)
    references = await service.get_market_references(owner.id, item.id)
    assert len(references) == 1
    assert references[0].price_item_id == item.id


async def test_foreign_owner_item_not_found(db_session):
    owner = await _make_user(db_session, 502)
    other = await _make_user(db_session, 503)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    await _create_evidence(db_session, owner.id, item)
    with pytest.raises(PriceItemNotFoundError):
        await service.get_market_references(other.id, item.id)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

async def test_api_unauthenticated_401(async_client: AsyncClient):
    resp = await async_client.get(
        "/api/price-items/00000000-0000-0000-0000-000000000000/market-reference"
    )
    assert resp.status_code == 401


async def test_api_nested_sources_with_decimal_strings(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    items = (
        await async_client.get("/api/price-items", headers=headers)
    ).json()["items"]
    item = next(i for i in items if i["code"] == PAINT_CODE)

    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    service = PriceBookService(db_session)
    await service.create_market_reference_with_sources(
        owner.id,
        uuid.UUID(item["id"]),
        region="Kraków",
        unit=PriceUnit.M2,
        market_min=Decimal("12.00"),
        market_max=Decimal("18.50"),
        reference_price=Decimal("15.00"),
        methodology_note="Próba 3 źródeł",
        checked_at=CHECKED_AT,
        sources=[
            _source(quoted_price_single=Decimal("15.00")),
            _source(
                source_name="Sklep materiałowy",
                source_type=SourceType.MATERIAL_STORE,
                quoted_price_single=None,
                quoted_price_min=Decimal("12.00"),
                quoted_price_max=Decimal("18.50"),
            ),
        ],
    )

    resp = await async_client.get(
        f"/api/price-items/{item['id']}/market-reference", headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    reference = data["items"][0]
    # Decimal money serializes as JSON strings, never binary floats.
    assert reference["market_min"] == "12.00"
    assert reference["market_max"] == "18.50"
    assert reference["reference_price"] == "15.00"
    assert reference["region"] == "Kraków"
    assert reference["unit"] == "M2"
    assert reference["currency"] == "PLN"
    assert reference["methodology_note"] == "Próba 3 źródeł"

    by_name = {s["source_name"]: s for s in reference["sources"]}
    assert len(by_name) == 2
    single = by_name["Cennik wykończeniowy Firma X"]
    assert single["source_type"] == "CONTRACTOR_PRICE_LIST"
    assert single["quoted_price_single"] == "15.00"
    assert single["quoted_price_min"] is None
    range_source = by_name["Sklep materiałowy"]
    assert range_source["source_type"] == "MATERIAL_STORE"
    assert range_source["quoted_price_min"] == "12.00"
    assert range_source["quoted_price_max"] == "18.50"
    assert range_source["quoted_price_single"] is None


async def test_api_missing_reference_returns_empty_list(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    items = (
        await async_client.get("/api/price-items", headers=headers)
    ).json()["items"]
    item = next(i for i in items if i["code"] == PAINT_CODE)
    resp = await async_client.get(
        f"/api/price-items/{item['id']}/market-reference", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


async def test_api_foreign_item_404(async_client: AsyncClient):
    token_owner = await get_token(async_client, VALID_USER)
    await get_token(async_client, OTHER_USER)
    headers = auth_header(token_owner)
    items = (
        await async_client.get("/api/price-items", headers=headers)
    ).json()["items"]
    item = next(i for i in items if i["code"] == PAINT_CODE)
    other_headers = auth_header(await get_token(async_client, OTHER_USER))
    resp = await async_client.get(
        f"/api/price-items/{item['id']}/market-reference", headers=other_headers
    )
    assert resp.status_code == 404


async def test_api_archived_item_evidence_readable(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    items = (
        await async_client.get("/api/price-items", headers=headers)
    ).json()["items"]
    item = next(i for i in items if i["code"] == PAINT_CODE)

    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    service = PriceBookService(db_session)
    await service.create_market_reference_with_sources(
        owner.id,
        uuid.UUID(item["id"]),
        region="Kraków",
        unit=PriceUnit.M2,
        market_min=Decimal("12.00"),
        market_max=Decimal("18.50"),
        checked_at=CHECKED_AT,
        sources=[_source()],
    )
    await async_client.post(
        f"/api/price-items/{item['id']}/archive", headers=headers
    )

    resp = await async_client.get(
        f"/api/price-items/{item['id']}/market-reference", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 1


async def test_api_patch_price_does_not_mutate_evidence(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    items = (
        await async_client.get("/api/price-items", headers=headers)
    ).json()["items"]
    item = next(i for i in items if i["code"] == PAINT_CODE)

    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    service = PriceBookService(db_session)
    await service.create_market_reference_with_sources(
        owner.id,
        uuid.UUID(item["id"]),
        region="Kraków",
        unit=PriceUnit.M2,
        market_min=Decimal("12.00"),
        market_max=Decimal("18.50"),
        checked_at=CHECKED_AT,
        sources=[_source(quoted_price_single=Decimal("15.00"))],
    )

    resp = await async_client.patch(
        f"/api/price-items/{item['id']}",
        headers=headers,
        json={"price": "9.99", "display_name": "Nowa cena własna"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] == "9.99"

    evidence = (
        await async_client.get(
            f"/api/price-items/{item['id']}/market-reference", headers=headers
        )
    ).json()
    reference = evidence["items"][0]
    assert reference["market_min"] == "12.00"
    assert reference["market_max"] == "18.50"
    assert reference["sources"][0]["quoted_price_single"] == "15.00"


# ---------------------------------------------------------------------------
# INVARIANT — evidence operations never mutate PriceItem.price
# ---------------------------------------------------------------------------

async def test_evidence_operations_never_mutate_item_price(db_session):
    owner = await _make_user(db_session, 601)
    service = PriceBookService(db_session)
    item = await _seed_item(db_session, service, owner.id)
    original_price = item.price

    _, reference = await _create_evidence(
        db_session,
        owner.id,
        item,
        reference_price=Decimal("99.00"),
        sources=[_source(quoted_price_single=Decimal("99.00"))],
    )
    assert (await service.get_owned_item(owner.id, item.id)).price == original_price

    await service.create_market_reference_with_sources(
        owner.id,
        item.id,
        region="Małopolskie",
        unit=item.unit,
        market_min=Decimal("5.00"),
        market_max=Decimal("9.00"),
        checked_at=EARLIER_CHECKED_AT,
        sources=[_source(quoted_price_single=Decimal("9.00"))],
    )
    assert (await service.get_owned_item(owner.id, item.id)).price == original_price

    await service.update_market_reference(
        owner.id,
        reference.id,
        market_min=Decimal("1.00"),
        market_max=Decimal("2.00"),
        checked_at=CHECKED_AT,
    )
    assert (await service.get_owned_item(owner.id, item.id)).price == original_price

    fetched = (
        await db_session.execute(
            select(PriceItem)
            .where(PriceItem.id == item.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert fetched.price == original_price