"""Stage 12G: coefficient descriptions + the owner-approved v1 default catalog.

Covers description persistence (service + HTTP), the exact v1 catalog
(docs/stage-12-architecture.md Sec 27.3), and bootstrap safety: repeated
bootstrap never duplicates rows and never overwrites or reactivates an
owner's customization.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.data.price_coefficients import build_baseline_price_coefficients
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.models import User
from app.models.price_coefficient import (
    CoefficientGroup,
    CoefficientOption,
    CoefficientSelectionMode,
)
from tests.conftest import make_telegram_init_data

EXPECTED_CATALOG = {
    "WYSOKOSC_PRACY": [
        ("STANDARDOWA", "Standardowa", Decimal("0"), True),
        ("PODWYZSZONA", "Podwyższona", Decimal("15"), False),
        ("WYSOKA", "Wysoka", Decimal("25"), False),
    ],
    "DOSTEP_DO_POWIERZCHNI": [
        ("SWOBODNY", "Swobodny", Decimal("0"), True),
        ("UTRUDNIONY", "Utrudniony", Decimal("10"), False),
        ("BARDZO_UTRUDNIONY", "Bardzo utrudniony", Decimal("20"), False),
    ],
    "ZLOZONOSC_POWIERZCHNI": [
        ("STANDARDOWA", "Standardowa", Decimal("0"), True),
        ("ZLOZONA", "Złożona", Decimal("10"), False),
        ("BARDZO_ZLOZONA", "Bardzo złożona", Decimal("20"), False),
    ],
    "ORGANIZACJA_PRACY": [
        ("CIAGLA", "Ciągła", Decimal("0"), True),
        ("OGRANICZONA", "Ograniczona", Decimal("10"), False),
        ("ETAPOWA", "Etapowa / przerywana", Decimal("20"), False),
    ],
}

OWNER = {"id": 126000001, "username": "owner12g", "first_name": "O", "language_code": "pl"}
OTHER = {"id": 126000002, "username": "other12g", "first_name": "X", "language_code": "pl"}


async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _groups(db, owner_id) -> list[CoefficientGroup]:
    from sqlalchemy.orm import selectinload

    return list(
        (
            await db.execute(
                select(CoefficientGroup)
                .options(selectinload(CoefficientGroup.options))
                .execution_options(populate_existing=True)
                .where(CoefficientGroup.owner_id == owner_id)
                .order_by(CoefficientGroup.position)
            )
        ).scalars()
    )


async def _token(client: AsyncClient, user: dict) -> dict:
    resp = await client.post(
        "/api/auth/telegram", json={"init_data": make_telegram_init_data(user)}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# v1 default catalog content
# ---------------------------------------------------------------------------


class TestV1DefaultCatalog:
    async def test_bootstrap_creates_exactly_four_groups_and_twelve_options(self, db_session):
        user = await _make_user(db_session, 126100)
        await PriceCoefficientService(db_session).ensure_owner_catalog(user.id)
        groups = await _groups(db_session, user.id)
        assert [g.code for g in groups] == list(EXPECTED_CATALOG)
        assert sum(len(g.options) for g in groups) == 12

    async def test_exact_codes_names_percentages_and_base_flags(self, db_session):
        user = await _make_user(db_session, 126101)
        await PriceCoefficientService(db_session).ensure_owner_catalog(user.id)
        for group in await _groups(db_session, user.id):
            assert group.selection_mode == CoefficientSelectionMode.SINGLE_SELECT
            assert group.is_archived is False
            actual = [
                (o.code, o.display_name, o.percentage, o.is_base)
                for o in sorted(group.options, key=lambda o: o.position)
            ]
            assert actual == EXPECTED_CATALOG[group.code]

    async def test_exactly_one_active_base_option_per_group_at_zero_percent(self, db_session):
        user = await _make_user(db_session, 126102)
        await PriceCoefficientService(db_session).ensure_owner_catalog(user.id)
        for group in await _groups(db_session, user.id):
            bases = [o for o in group.options if o.is_base and not o.is_archived]
            assert len(bases) == 1
            assert bases[0].percentage == Decimal("0")

    async def test_every_default_group_and_option_has_a_description(self, db_session):
        user = await _make_user(db_session, 126103)
        await PriceCoefficientService(db_session).ensure_owner_catalog(user.id)
        for group in await _groups(db_session, user.id):
            assert group.description and len(group.description.strip()) > 80
            for option in group.options:
                assert option.description and option.description.strip()

    def test_descriptions_cover_the_double_counting_boundaries(self):
        by_code = {g.code: g for g in build_baseline_price_coefficients()}
        assert "rusztowania" in by_code["WYSOKOSC_PRACY"].description
        assert "przesunięcie mebli" in by_code["DOSTEP_DO_POWIERZCHNI"].description
        assert "ościeża" in by_code["ZLOZONOSC_POWIERZCHNI"].description
        assert "zabezpieczenie" in by_code["ORGANIZACJA_PRACY"].description

    def test_seed_text_matches_the_frontend_canonical_polish_catalog(self):
        """The frontend shows a translated built-in label only while the
        stored value equals the canonical Polish text in pl.json
        (`coefficients.builtin`); both copies must stay byte-identical."""
        locale = Path(__file__).resolve().parents[2] / "frontend/src/locales/pl.json"
        if not locale.exists():
            pytest.skip("frontend locale not available in this checkout")
        builtin = json.loads(locale.read_text(encoding="utf-8"))["coefficients"]["builtin"]
        seed = {
            g.code: {
                "name": g.display_name,
                "description": g.description,
                "options": {
                    o.code: {"name": o.display_name, "description": o.description}
                    for o in g.options
                },
            }
            for g in build_baseline_price_coefficients()
        }
        assert builtin == seed

    def test_no_quality_target_group_is_seeded(self):
        text = " ".join(
            f"{g.code} {g.display_name} "
            + " ".join(f"{o.code} {o.display_name}" for o in g.options)
            for g in build_baseline_price_coefficients()
        ).upper()
        for forbidden in ("S1", "S2", "S3", "S4", "Q1", "Q2", "Q3", "Q4", "PSG", "QUALITY", "JAKOS"):
            assert forbidden not in text

    def test_no_negative_default_option(self):
        for group in build_baseline_price_coefficients():
            for option in group.options:
                assert Decimal(option.percentage) >= 0

    def test_no_forbidden_surcharge_or_commercial_group(self):
        codes = " ".join(g.code for g in build_baseline_price_coefficients()).upper()
        for forbidden in (
            "MEBL", "FURNITURE", "SUFIT", "CEILING", "KOLOR", "COLOUR", "COLOR",
            "MALE_ZLEC", "SMALL", "PILN", "URGEN", "NOC", "NIGHT", "WEEKEND",
            "DOJAZD", "TRAVEL", "RUSZTOW", "SCAFFOLD", "SPRZET", "EQUIPMENT",
            "RABAT", "DISCOUNT", "DOPLAT", "SURCHARGE",
        ):
            assert forbidden not in codes


# ---------------------------------------------------------------------------
# Bootstrap safety
# ---------------------------------------------------------------------------


class TestBootstrapPreservesOwnerCustomization:
    async def test_repeated_bootstrap_is_idempotent(self, db_session):
        user = await _make_user(db_session, 126200)
        service = PriceCoefficientService(db_session)
        first = await service.ensure_owner_catalog(user.id)
        second = await service.ensure_owner_catalog(user.id)
        assert len(first) == 4
        assert second == []
        groups = await _groups(db_session, user.id)
        assert len(groups) == 4
        assert sum(len(g.options) for g in groups) == 12

    async def test_owner_edits_survive_repeated_bootstrap(self, db_session):
        user = await _make_user(db_session, 126201)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        height = (await _groups(db_session, user.id))[0]
        high = next(o for o in height.options if o.code == "WYSOKA")
        await service.update_group(
            user.id, height.id, display_name="Moja wysokość", description="Mój opis grupy"
        )
        await service.update_option(
            user.id,
            high.id,
            display_name="Bardzo wysoko",
            description="Mój opis opcji",
            percentage=Decimal("30"),
        )

        await service.ensure_owner_catalog(user.id)

        height = (await _groups(db_session, user.id))[0]
        high = next(o for o in height.options if o.code == "WYSOKA")
        assert height.display_name == "Moja wysokość"
        assert height.description == "Mój opis grupy"
        assert high.display_name == "Bardzo wysoko"
        assert high.description == "Mój opis opcji"
        assert high.percentage == Decimal("30")

    async def test_owner_cleared_description_is_not_restored(self, db_session):
        user = await _make_user(db_session, 126202)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        group = (await _groups(db_session, user.id))[1]
        await service.update_group(user.id, group.id, description=None)
        await service.ensure_owner_catalog(user.id)
        group = (await _groups(db_session, user.id))[1]
        assert group.description is None

    async def test_owner_base_choice_survives_repeated_bootstrap(self, db_session):
        user = await _make_user(db_session, 126203)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        height = (await _groups(db_session, user.id))[0]
        raised = next(o for o in height.options if o.code == "PODWYZSZONA")
        await service.update_option(user.id, raised.id, is_base=True)
        await service.ensure_owner_catalog(user.id)
        height = (await _groups(db_session, user.id))[0]
        bases = [o.code for o in height.options if o.is_base and not o.is_archived]
        assert bases == ["PODWYZSZONA"]

    async def test_archived_defaults_are_not_reactivated(self, db_session):
        user = await _make_user(db_session, 126204)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        groups = await _groups(db_session, user.id)
        await service.archive_group(user.id, groups[3].id)
        option = next(o for o in groups[0].options if o.code == "WYSOKA")
        await service.archive_option(user.id, option.id)

        await service.ensure_owner_catalog(user.id)

        groups = await _groups(db_session, user.id)
        assert len(groups) == 4
        assert groups[3].is_archived is True
        option = next(o for o in groups[0].options if o.code == "WYSOKA")
        assert option.is_archived is True
        assert sum(len(g.options) for g in groups) == 12

    async def test_missing_default_never_creates_a_second_active_base(
        self, db_session, monkeypatch
    ):
        """If an owner already has an active base in a default group, a later
        insertion of a missing default base option joins as a plain option."""
        user = await _make_user(db_session, 126205)
        service = PriceCoefficientService(db_session)
        await service.ensure_owner_catalog(user.id)
        height = (await _groups(db_session, user.id))[0]
        standard = next(o for o in height.options if o.code == "STANDARDOWA")
        raised = next(o for o in height.options if o.code == "PODWYZSZONA")
        await service.update_option(user.id, raised.id, is_base=True)
        # Simulate a default that is missing for this owner (e.g. added to the
        # catalog after the owner's first bootstrap).
        await db_session.delete(standard)
        await db_session.commit()

        await service.ensure_owner_catalog(user.id)

        height = (await _groups(db_session, user.id))[0]
        bases = [o.code for o in height.options if o.is_base and not o.is_archived]
        assert bases == ["PODWYZSZONA"]
        assert "STANDARDOWA" in [o.code for o in height.options]


# ---------------------------------------------------------------------------
# Description persistence (HTTP)
# ---------------------------------------------------------------------------


class TestDescriptionApi:
    async def test_group_description_create_read_update_and_clear(self, async_client: AsyncClient):
        headers = await _token(async_client, OWNER)
        created = await async_client.post(
            "/api/price-coefficient-groups",
            headers=headers,
            json={"display_name": "Własna", "description": "  Opis grupy  "},
        )
        assert created.status_code == 201, created.text
        group = created.json()
        assert group["description"] == "Opis grupy"

        read = await async_client.get(
            f"/api/price-coefficient-groups/{group['id']}", headers=headers
        )
        assert read.json()["description"] == "Opis grupy"

        renamed = await async_client.patch(
            f"/api/price-coefficient-groups/{group['id']}",
            headers=headers,
            json={"display_name": "Inna"},
        )
        assert renamed.json()["description"] == "Opis grupy"  # omitted = unchanged

        updated = await async_client.patch(
            f"/api/price-coefficient-groups/{group['id']}",
            headers=headers,
            json={"description": "Nowy opis"},
        )
        assert updated.json()["description"] == "Nowy opis"

        cleared = await async_client.patch(
            f"/api/price-coefficient-groups/{group['id']}",
            headers=headers,
            json={"description": None},
        )
        assert cleared.json()["description"] is None

    async def test_group_description_is_nullable(self, async_client: AsyncClient):
        headers = await _token(async_client, OWNER)
        created = await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "Bez opisu"}
        )
        assert created.status_code == 201
        assert created.json()["description"] is None

    async def test_option_description_create_read_update_and_clear(self, async_client: AsyncClient):
        headers = await _token(async_client, OWNER)
        group = (
            await async_client.post(
                "/api/price-coefficient-groups", headers=headers, json={"display_name": "G"}
            )
        ).json()
        created = await async_client.post(
            f"/api/price-coefficient-groups/{group['id']}/options",
            headers=headers,
            json={"display_name": "O", "percentage": "5", "description": "Opis opcji"},
        )
        assert created.status_code == 201, created.text
        option = created.json()
        assert option["description"] == "Opis opcji"

        listed = await async_client.get(
            f"/api/price-coefficient-groups/{group['id']}", headers=headers
        )
        assert listed.json()["options"][0]["description"] == "Opis opcji"

        pct_only = await async_client.patch(
            f"/api/price-coefficient-options/{option['id']}",
            headers=headers,
            json={"percentage": "7"},
        )
        assert pct_only.json()["description"] == "Opis opcji"

        blank = await async_client.patch(
            f"/api/price-coefficient-options/{option['id']}",
            headers=headers,
            json={"description": "   "},
        )
        assert blank.json()["description"] is None

    async def test_option_description_is_nullable(self, async_client: AsyncClient):
        headers = await _token(async_client, OWNER)
        group = (
            await async_client.post(
                "/api/price-coefficient-groups", headers=headers, json={"display_name": "G"}
            )
        ).json()
        created = await async_client.post(
            f"/api/price-coefficient-groups/{group['id']}/options",
            headers=headers,
            json={"display_name": "O", "percentage": "0"},
        )
        assert created.json()["description"] is None

    async def test_default_catalog_descriptions_are_served(self, async_client: AsyncClient):
        headers = await _token(async_client, OWNER)
        body = (await async_client.get("/api/price-coefficient-groups", headers=headers)).json()
        assert body["total"] == 4
        for group in body["items"]:
            assert group["description"]
            assert all(o["description"] for o in group["options"])

    async def test_description_update_is_owner_isolated(self, async_client: AsyncClient):
        owner = await _token(async_client, OWNER)
        other = await _token(async_client, OTHER)
        group = (
            await async_client.post(
                "/api/price-coefficient-groups",
                headers=owner,
                json={"display_name": "G", "description": "Owner"},
            )
        ).json()
        option = (
            await async_client.post(
                f"/api/price-coefficient-groups/{group['id']}/options",
                headers=owner,
                json={"display_name": "O", "percentage": "1", "description": "Owner"},
            )
        ).json()
        r1 = await async_client.patch(
            f"/api/price-coefficient-groups/{group['id']}",
            headers=other,
            json={"description": "Hacked"},
        )
        r2 = await async_client.patch(
            f"/api/price-coefficient-options/{option['id']}",
            headers=other,
            json={"description": "Hacked"},
        )
        assert r1.status_code == 404
        assert r2.status_code == 404
        read = (
            await async_client.get(f"/api/price-coefficient-groups/{group['id']}", headers=owner)
        ).json()
        assert read["description"] == "Owner"
        assert read["options"][0]["description"] == "Owner"

    async def test_description_is_bounded(self, async_client: AsyncClient):
        headers = await _token(async_client, OWNER)
        resp = await async_client.post(
            "/api/price-coefficient-groups",
            headers=headers,
            json={"display_name": "G", "description": "x" * 4001},
        )
        assert resp.status_code == 422
