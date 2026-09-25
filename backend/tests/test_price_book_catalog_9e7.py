"""Stage 9E.7 tests: approved 49-row catalog (44 9E.7 + 5 Stage 13D) + seeded market evidence (9E.7).

Covers the owner-approved catalog shape (28 MARKET_SUPPORTED / 16 OWN_PRICE),
the idempotent per-owner bootstrap (including one-time retirement of the 9B
GENERIC placeholders), the 28 seeded market references with verbatim sources,
evidence idempotency, owner isolation, and the read-only API exposure.
Price.init policy: every seeded row carries ``price=None`` and bootstrap never
writes ``PriceItem.price`` — evidence is application-maintained and separate.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.data.price_book_seed import (
    LEGACY_GENERIC_CODES,
    build_approved_market_references,
    build_approved_price_book_items,
)
from app.domain.services.price_book_service import PriceBookService
from app.models.checklist import QualityLevel
from app.models.market_evidence import PriceMarketReference, SourceType
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.user import User
from tests.conftest import make_telegram_init_data

ALLOWED_REGIONS = frozenset({"Kraków", "Małopolskie", "Kraków / Małopolskie"})

VALID_USER = {
    "id": 333333333,
    "username": "owner9e7",
    "first_name": "Owner",
    "last_name": "NineE7",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 444444444,
    "username": "other9e7",
    "first_name": "Other",
    "last_name": "NineE7",
    "language_code": "pl",
}

ITEMS = build_approved_price_book_items()
ITEM_BY_CODE = {seed.code: seed for seed in ITEMS}
REFERENCES = build_approved_market_references()
MS_CODES = frozenset(REFERENCES)
OP_CODES = frozenset(ITEM_BY_CODE) - MS_CODES


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _bootstrap(db, owner_id: uuid.UUID) -> tuple[PriceBookService, list[PriceItem]]:
    service = PriceBookService(db)
    created = await service.ensure_owner_catalog(owner_id)
    return service, created


async def _own_items(service: PriceBookService, owner_id: uuid.UUID) -> dict[str, PriceItem]:
    return {i.code: i for i in await service.list_owner_items(owner_id, archived="all")}


async def _refs_for(service: PriceBookService, owner_id: uuid.UUID, code: str) -> list:
    item = (await _own_items(service, owner_id))[code]
    return await service.get_market_references(owner_id, item.id)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# TestCatalogSeed — approved 49-row shape (1–10)
# ---------------------------------------------------------------------------

class TestCatalogSeed:
    def test_catalog_has_exactly_49_rows(self):
        assert len(ITEMS) == 49

    def test_market_supported_count_is_28(self):
        assert len(MS_CODES) == 28

    def test_own_price_count_is_21(self):
        assert len(OP_CODES) == 21  # 16 9E.5 + 5 Stage 13D (no market evidence)
        assert len(MS_CODES) + len(OP_CODES) == len(ITEMS)

    def test_dropped_rows_absent(self):
        for dropped in ("CENNIK_SKIM_3L-01", "CENNIK_SKIM_PKG-01"):
            assert dropped not in ITEM_BY_CODE

    def test_folded_reveal_rows_absent_rev_work_lm_present(self):
        reveal_codes = {
            code for code, seed in ITEM_BY_CODE.items() if seed.category is PriceCategory.REVEAL
        }
        assert reveal_codes == {"CENNIK_REV_WORK_LM-01"}
        for folded in (
            "CENNIK_REV_PREP-01",
            "CENNIK_REV_SKIM-01",
            "CENNIK_REV_SAND-01",
            "CENNIK_REV_PAINT-01",
            "CENNIK_REV_PAINT_LM-01",
        ):
            assert folded not in ITEM_BY_CODE

    def test_rev_work_lm_linear_unit(self):
        seed = ITEM_BY_CODE["CENNIK_REV_WORK_LM-01"]
        assert seed.unit is PriceUnit.LM
        assert seed.price_scope is PriceScope.LABOR

    def test_gk_joint_unit_lm(self):
        assert ITEM_BY_CODE["CENNIK_GK_JOINT-01"].unit is PriceUnit.LM

    def test_mc_stairs_unit_pcs(self):
        seed = ITEM_BY_CODE["CENNIK_MC_STAIRS-01"]
        assert seed.unit is PriceUnit.PCS
        assert seed.price_scope is PriceScope.LABOR_AND_MATERIAL

    def test_dec_generic_restricted_row(self):
        seed = ITEM_BY_CODE["CENNIK_DEC_GENERIC-01"]
        assert seed.name_key == "pricebook.seed.dec_generic"
        assert seed.price_scope is PriceScope.LABOR
        assert seed.unit is PriceUnit.M2

    def test_gf_fliz_is_own_price(self):
        for code in ("CENNIK_GF_FLIZ_L-01", "CENNIK_GF_FLIZ_M-01"):
            assert code in OP_CODES

    def test_quality_seeded_only_for_unambiguous_tier(self):
        assert ITEM_BY_CODE["CENNIK_GK_FULL-01"].quality_level is QualityLevel.Q3
        assert ITEM_BY_CODE["CENNIK_GK_Q4-01"].quality_level is QualityLevel.Q4
        # Dual-tier research hints are not representable and stay NULL.
        assert ITEM_BY_CODE["CENNIK_GK_JOINT-01"].quality_level is None
        assert ITEM_BY_CODE["CENNIK_SKIM_SQ-01"].quality_level is None

    def test_every_seed_price_is_none(self):
        assert all(seed.price is None for seed in ITEMS)

    def test_all_codes_unique_and_cennik_prefixed(self):
        codes = [seed.code for seed in ITEMS]
        assert len(codes) == len(set(codes))
        assert all(code.startswith("CENNIK_") and code.endswith("-01") for code in codes)


# ---------------------------------------------------------------------------
# TestBootstrap — per-owner lazy materialization (11–17)
# ---------------------------------------------------------------------------

class TestBootstrap:
    async def test_first_bootstrap_creates_every_seed(self, db_session):
        owner = await _make_user(db_session, 7001)
        service, created = await _bootstrap(db_session, owner.id)
        assert {i.code for i in created} == set(ITEM_BY_CODE)
        for item in created:
            assert item.price is None
            assert item.display_name is None
            assert item.name_key is not None

    async def test_second_bootstrap_is_idempotent(self, db_session):
        owner = await _make_user(db_session, 7002)
        service, created = await _bootstrap(db_session, owner.id)
        assert len(created) == 49
        assert await service.ensure_owner_catalog(owner.id) == []
        assert len(await service.list_owner_items(owner.id)) == 49

    async def test_custom_items_untouched_by_bootstrap(self, db_session):
        owner = await _make_user(db_session, 7003)
        service = PriceBookService(db_session)
        custom = await service.create_custom_item(
            owner.id,
            category=PriceCategory.PAINTING,
            unit=PriceUnit.M2,
            price=Decimal("8.80"),
            display_name="Pozycja własna",
        )
        await service.ensure_owner_catalog(owner.id)
        fetched = await service.get_owned_item(owner.id, custom.id)
        assert fetched.price == Decimal("8.80")
        assert fetched.code == custom.code
        assert fetched.display_name == "Pozycja własna"

    async def test_edits_and_archive_survive_rebootstrap(self, db_session):
        owner = await _make_user(db_session, 7004)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner.id)
        items = await _own_items(service, owner.id)
        wallp = items["CENNIK_PREP_WALLP-01"]
        await service.update_item(
            owner.id,
            wallp.id,
            price=Decimal("25.00"),
            display_name="Usuwanie tapet (moja cena)",
        )
        await service.archive_item(owner.id, items["CENNIK_PREP_PROT-01"].id)

        await service.ensure_owner_catalog(owner.id)

        wallp2 = await service.get_owned_item(owner.id, wallp.id)
        assert wallp2.price == Decimal("25.00")
        assert wallp2.display_name == "Usuwanie tapet (moja cena)"
        prot = await service.get_owned_item(owner.id, items["CENNIK_PREP_PROT-01"].id)
        assert prot.is_archived is True

    async def test_legacy_generic_seeds_retired_once_on_bootstrap(self, db_session):
        """A pre-9E.7 owner (4 GENERIC rows present) gets them archived on first contact.

        Retirement is soft: ids, names, and prices are preserved, never deleted.
        """
        owner = await _make_user(db_session, 7005)
        legacy_rows = []
        for idx, code in enumerate(LEGACY_GENERIC_CODES):
            row = PriceItem(
                owner_id=owner.id,
                code=code,
                name_key=f"pricebook.seed.{code.lower()}",
                category=PriceCategory.OTHER,
                unit=PriceUnit.M2 if not code.endswith("_LM") else PriceUnit.LM,
                price=Decimal(f"{idx + 1}.11"),
            )
            db_session.add(row)
            legacy_rows.append(row)
        await db_session.flush()  # assign ids before capturing them
        legacy_id_by_code = {row.code: row.id for row in legacy_rows}
        await db_session.commit()

        service, created = await _bootstrap(db_session, owner.id)
        assert len(created) == 49  # canonical catalog added alongside the legacy rows

        active = await service.list_owner_items(owner.id)
        assert len(active) == 49  # legacy rows are archived, not active
        archived = await service.list_owner_items(owner.id, archived="archived")
        assert {i.code for i in archived} == set(LEGACY_GENERIC_CODES)
        for row in archived:
            assert row.id == legacy_id_by_code[row.code]  # same rows, not new copies
            assert row.price is not None  # retired placeholder price preserved

    async def test_legacy_retirement_is_idempotent(self, db_session):
        owner = await _make_user(db_session, 7006)
        for idx, code in enumerate(LEGACY_GENERIC_CODES):
            db_session.add(
                PriceItem(
                    owner_id=owner.id,
                    code=code,
                    name_key=f"pricebook.seed.{code.lower()}",
                    category=PriceCategory.OTHER,
                    unit=PriceUnit.M2 if not code.endswith("_LM") else PriceUnit.LM,
                    price=Decimal(f"{idx + 1}.11"),
                )
            )
        await db_session.commit()

        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner.id)
        await service.ensure_owner_catalog(owner.id)
        assert len(await service.list_owner_items(owner.id)) == 49
        assert len(await service.list_owner_items(owner.id, archived="archived")) == 4

    async def test_fresh_owner_has_no_archived_rows(self, db_session):
        owner = await _make_user(db_session, 7007)
        service, _ = await _bootstrap(db_session, owner.id)
        assert await service.list_owner_items(owner.id, archived="archived") == []
        assert len(await service.list_owner_items(owner.id)) == 49


# ---------------------------------------------------------------------------
# TestEvidenceSeed — 28 MS references with verbatim sources (18–31)
# ---------------------------------------------------------------------------

class TestEvidenceSeed:
    async def test_every_ms_item_has_exactly_one_reference(self, db_session):
        owner = await _make_user(db_session, 7101)
        service, _ = await _bootstrap(db_session, owner.id)
        counts = {}
        for code in MS_CODES:
            counts[code] = len(await _refs_for(service, owner.id, code))
        assert counts == {code: 1 for code in MS_CODES}

    async def test_spot_checked_windows_exact(self, db_session):
        owner = await _make_user(db_session, 7102)
        service, _ = await _bootstrap(db_session, owner.id)
        expected = {
            "CENNIK_SKIM_1L-01": ("30", "50", "40"),
            "CENNIK_PAINT_3K-01": ("21.80", "48", None),
            "CENNIK_MC_SHOWER-01": ("450", "650", "550"),
            "CENNIK_GK_JOINT-01": ("12", "24", None),
            "CENNIK_REV_WORK_LM-01": ("30", "110", "60"),
        }
        for code, (lo, hi, ref) in expected.items():
            reference = (await _refs_for(service, owner.id, code))[0]
            assert reference.market_min == Decimal(lo)
            assert reference.market_max == Decimal(hi)
            assert (reference.reference_price and Decimal(reference.reference_price) == Decimal(ref)) or (
                reference.reference_price is None and ref is None
            )

    async def test_reference_unit_equals_item_unit(self, db_session):
        owner = await _make_user(db_session, 7103)
        service, _ = await _bootstrap(db_session, owner.id)
        items = await _own_items(service, owner.id)
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            assert reference.unit is items[code].unit, code

    async def test_reference_currency_pln(self, db_session):
        owner = await _make_user(db_session, 7104)
        service, _ = await _bootstrap(db_session, owner.id)
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            assert reference.currency == "PLN", code

    async def test_checked_at_from_research_dates(self, db_session):
        owner = await _make_user(db_session, 7105)
        service, _ = await _bootstrap(db_session, owner.id)
        seen_dates = set()
        for code, seed in REFERENCES.items():
            reference = (await _refs_for(service, owner.id, code))[0]
            assert _utc(reference.checked_at) == seed.checked_at, code
            seen_dates.add(_utc(reference.checked_at).date())
        # Batch A researched 2026-09-13; Batches B/C/D/E on 2026-09-14.
        assert seen_dates == {
            datetime(2026, 9, 13, tzinfo=timezone.utc).date(),
            datetime(2026, 9, 14, tzinfo=timezone.utc).date(),
        }

    async def test_sources_present_with_metadata(self, db_session):
        owner = await _make_user(db_session, 7106)
        service, _ = await _bootstrap(db_session, owner.id)
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            assert reference.sources, code
            for source in reference.sources:
                assert source.source_name.strip(), (code, source.source_name)
                assert source.source_type in set(SourceType), code
                assert source.source_url is not None and source.source_url.startswith("https://")

    async def test_source_urls_verbatim_from_docs(self, db_session):
        """Every seeded source URL appears verbatim in the research docs."""
        root = Path(__file__).resolve().parents[2]
        corpus = "\n".join(
            (root / "docs" / f"price-research-batch-{letter}.md").read_text(
                encoding="utf-8"
            )
            for letter in "abcde"
        )
        corpus += "\n" + (root / "docs" / "price-research-catalog.md").read_text(
            encoding="utf-8"
        )
        owner = await _make_user(db_session, 7107)
        service, _ = await _bootstrap(db_session, owner.id)
        checked = 0
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            for source in reference.sources:
                assert source.source_url in corpus, (code, source.source_url)
                checked += 1
        assert checked == 112  # every source in the 28 references carries a doc URL

    async def test_quote_mode_single_sources(self, db_session):
        owner = await _make_user(db_session, 7108)
        service, _ = await _bootstrap(db_session, owner.id)
        single_sources = 0
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            for source in reference.sources:
                if source.quoted_price_single is not None:
                    single_sources += 1
                    assert source.quoted_price_min is None
                    assert source.quoted_price_max is None
        assert single_sources >= 1

    async def test_quote_mode_range_sources(self, db_session):
        owner = await _make_user(db_session, 7109)
        service, _ = await _bootstrap(db_session, owner.id)
        range_sources = 0
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            for source in reference.sources:
                if source.quoted_price_min is not None or source.quoted_price_max is not None:
                    range_sources += 1
                    assert source.quoted_price_single is None
                    assert source.quoted_price_min is not None
                    assert source.quoted_price_max is not None
                    assert source.quoted_price_min <= source.quoted_price_max
        assert range_sources >= 1

    async def test_quote_mode_never_ambiguous(self, db_session):
        """Every source obeys exactly one quoting mode (SINGLE / RANGE)."""
        owner = await _make_user(db_session, 7110)
        service, _ = await _bootstrap(db_session, owner.id)
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            for source in reference.sources:
                single = source.quoted_price_single is not None
                lo = source.quoted_price_min is not None
                hi = source.quoted_price_max is not None
                assert (single and not lo and not hi) or (not single and lo and hi)
                for value in (
                    source.quoted_price_single,
                    source.quoted_price_min,
                    source.quoted_price_max,
                ):
                    if value is not None:
                        assert value >= 0
                        assert value.as_tuple().exponent >= -2  # never silently rounded

    async def test_noncomparable_unit_source_kept_uncropped(self, db_session):
        """A source quoting a different unit keeps its own numbers (qualitative context)."""
        owner = await _make_user(db_session, 7111)
        service, _ = await _bootstrap(db_session, owner.id)
        reference = (await _refs_for(service, owner.id, "CENNIK_SKIM_CRACK-01"))[0]
        assert reference.unit is PriceUnit.LM
        pcs_sources = [s for s in reference.sources if s.quoted_unit is PriceUnit.PCS]
        assert pcs_sources, "PCS-quoting source must be preserved, not dropped"
        assert pcs_sources[0].quoted_price_min == Decimal("200")

    async def test_own_price_rows_get_no_evidence(self, db_session):
        owner = await _make_user(db_session, 7112)
        service, _ = await _bootstrap(db_session, owner.id)
        for code in OP_CODES:
            assert await _refs_for(service, owner.id, code) == [], code

    async def test_gf_fliz_no_fiberglass_evidence(self, db_session):
        owner = await _make_user(db_session, 7113)
        service, _ = await _bootstrap(db_session, owner.id)
        for code in ("CENNIK_GF_FLIZ_L-01", "CENNIK_GF_FLIZ_M-01"):
            assert await _refs_for(service, owner.id, code) == []

    async def test_mc_stairs_no_unit_converted_range(self, db_session):
        owner = await _make_user(db_session, 7114)
        service, _ = await _bootstrap(db_session, owner.id)
        assert await _refs_for(service, owner.id, "CENNIK_MC_STAIRS-01") == []

    async def test_reference_region_labelled(self, db_session):
        owner = await _make_user(db_session, 7115)
        service, _ = await _bootstrap(db_session, owner.id)
        for code in MS_CODES:
            reference = (await _refs_for(service, owner.id, code))[0]
            assert reference.region in ALLOWED_REGIONS, code


# ---------------------------------------------------------------------------
# TestEvidenceIdempotency (32–34)
# ---------------------------------------------------------------------------

class TestEvidenceIdempotency:
    async def _reference_ids(self, db, owner_id) -> set[uuid.UUID]:
        rows = (
            await db.execute(
                select(PriceMarketReference)
                .join(PriceItem, PriceItem.id == PriceMarketReference.price_item_id)
                .where(PriceItem.owner_id == owner_id)
            )
        ).scalars().all()
        return {r.id for r in rows}

    async def test_rebootstrap_no_duplicate_references(self, db_session):
        owner = await _make_user(db_session, 7201)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner.id)
        first = await self._reference_ids(db_session, owner.id)
        assert len(first) == 28

        await service.ensure_owner_catalog(owner.id)
        second = await self._reference_ids(db_session, owner.id)
        assert second == first  # same ids, not duplicated

    async def test_rebootstrap_no_duplicate_sources(self, db_session):
        owner = await _make_user(db_session, 7202)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner.id)

        async def total_sources() -> int:
            total = 0
            for code in MS_CODES:
                for reference in await _refs_for(service, owner.id, code):
                    total += len(reference.sources)
            return total

        count_before = await total_sources()
        await service.ensure_owner_catalog(owner.id)
        count_after = await total_sources()
        assert count_before == count_after
        assert count_before >= 28

    async def test_bootstrap_never_writes_item_price(self, db_session):
        owner = await _make_user(db_session, 7203)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner.id)
        items = await _own_items(service, owner.id)
        assert all(item.price is None for item in items.values())

        await service.update_item(owner.id, items["CENNIK_SKIM_1L-01"].id, price=Decimal("45.00"))
        await service.ensure_owner_catalog(owner.id)  # reconcile must not touch the edit
        refetched = await service.get_owned_item(owner.id, items["CENNIK_SKIM_1L-01"].id)
        assert refetched.price == Decimal("45.00")


# ---------------------------------------------------------------------------
# TestOwnerIsolation (35–37)
# ---------------------------------------------------------------------------

class TestOwnerIsolation:
    async def _reference_ids(self, db, owner_id) -> set[uuid.UUID]:
        rows = (
            await db.execute(
                select(PriceMarketReference)
                .join(PriceItem, PriceItem.id == PriceMarketReference.price_item_id)
                .where(PriceItem.owner_id == owner_id)
            )
        ).scalars().all()
        return {r.id for r in rows}

    async def test_independent_catalogs(self, db_session):
        owner_a = await _make_user(db_session, 7301)
        owner_b = await _make_user(db_session, 7302)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner_a.id)
        await service.ensure_owner_catalog(owner_b.id)
        a = await _own_items(service, owner_a.id)
        b = await _own_items(service, owner_b.id)
        assert len(a) == len(b) == 49
        assert {i.id for i in a.values()}.isdisjoint({i.id for i in b.values()})

    async def test_independent_evidence(self, db_session):
        owner_a = await _make_user(db_session, 7303)
        owner_b = await _make_user(db_session, 7304)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner_a.id)
        await service.ensure_owner_catalog(owner_b.id)
        a = await self._reference_ids(db_session, owner_a.id)
        b = await self._reference_ids(db_session, owner_b.id)
        assert len(a) == len(b) == 28
        assert a.isdisjoint(b)

    async def test_edits_isolated(self, db_session):
        owner_a = await _make_user(db_session, 7305)
        owner_b = await _make_user(db_session, 7306)
        service = PriceBookService(db_session)
        await service.ensure_owner_catalog(owner_a.id)
        await service.ensure_owner_catalog(owner_b.id)
        a = await _own_items(service, owner_a.id)
        await service.update_item(owner_a.id, a["CENNIK_PAINT_2K-01"].id, price=Decimal("19.00"))
        b = await _own_items(service, owner_b.id)
        assert b["CENNIK_PAINT_2K-01"].price is None


# ---------------------------------------------------------------------------
# TestApiIntegration — read-only evidence over HTTP (38–41)
# ---------------------------------------------------------------------------

class TestApiIntegration:
    async def _token(self, async_client: AsyncClient, user: dict) -> str:
        resp = await async_client.post(
            "/api/auth/telegram", json={"init_data": make_telegram_init_data(user)}
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]

    async def test_api_ms_item_returns_seeded_evidence(self, async_client: AsyncClient):
        headers = {"Authorization": f"Bearer {await self._token(async_client, VALID_USER)}"}
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        skim = next(i for i in items if i["code"] == "CENNIK_SKIM_1L-01")
        resp = await async_client.get(
            f"/api/price-items/{skim['id']}/market-reference", headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        reference = body["items"][0]
        assert reference["region"] == "Kraków"
        assert reference["unit"] == "M2"
        assert reference["currency"] == "PLN"
        assert reference["sources"]

    async def test_api_nested_sources_verbatim(self, async_client: AsyncClient):
        headers = {"Authorization": f"Bearer {await self._token(async_client, VALID_USER)}"}
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        skim = next(i for i in items if i["code"] == "CENNIK_SKIM_1L-01")
        reference = (
            await async_client.get(
                f"/api/price-items/{skim['id']}/market-reference", headers=headers
            )
        ).json()["items"][0]
        urls = {s["source_url"] for s in reference["sources"]}
        assert "https://s-szpachlowanie.pl/szpachlowanie-krakow-cennik" in urls

    async def test_api_op_item_empty_envelope(self, async_client: AsyncClient):
        headers = {"Authorization": f"Bearer {await self._token(async_client, VALID_USER)}"}
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        mask = next(i for i in items if i["code"] == "CENNIK_PAINT_MASK-01")
        resp = await async_client.get(
            f"/api/price-items/{mask['id']}/market-reference", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}

    async def test_api_money_serialized_as_string(self, async_client: AsyncClient):
        headers = {"Authorization": f"Bearer {await self._token(async_client, VALID_USER)}"}
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        skim = next(i for i in items if i["code"] == "CENNIK_SKIM_1L-01")
        reference = (
            await async_client.get(
                f"/api/price-items/{skim['id']}/market-reference", headers=headers
            )
        ).json()["items"][0]
        assert isinstance(reference["market_min"], str)
        assert isinstance(reference["market_max"], str)
        assert Decimal(reference["market_min"]) == Decimal("30")
        assert Decimal(reference["market_max"]) == Decimal("50")