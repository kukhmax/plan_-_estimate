"""V2-6 -- the VAT of an estimate (docs/V2_6_PLAN_RU.md)."""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.domain.rules.vat import VatError, validate_vat, vat_totals
from app.domain.services.password_login_service import PasswordLoginService
from app.models.estimate import Estimate
from app.models.executor_profile import ExecutorProfile
from tests.test_stage15d_estimate_document import STANDARD, build, estimate, html_of

PASSWORD = "correct horse battery"
PRICES = {"CENNIK_PRIM_STD-01": "7.00", "CENNIK_SKIM_2L-01": "35.00", "CENNIK_SKIM_SAND-01": "10.00", "CENNIK_PAINT_2K-01": "10.00"}
WORKS = list(PRICES)
SALON = {"name": "Salon", "length": "5.200", "width": "3.600", "height": "2.600"}  # 45.76 m2 of walls: net 45.76 x 62 = 2837.12


# --- the rule ------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,rate,expected",
    [(None, None, (None, None)), ("EXEMPT", None, ("EXEMPT", None)), ("RATE", 8, ("RATE", 8)), ("RATE", 23, ("RATE", 23))],
)
def test_the_allowed_pairs(mode, rate, expected):
    assert validate_vat(mode, rate) == expected


@pytest.mark.parametrize("mode,rate", [(None, 23), ("EXEMPT", 8), ("RATE", None), ("RATE", 5), ("RATE", 0), ("RATE", 24), ("zw", None), ("rate", 23)])
def test_the_wrong_pairs_are_refused(mode, rate):
    with pytest.raises(VatError):
        validate_vat(mode, rate)


@pytest.mark.parametrize(
    "net,mode,rate,vat,gross",
    [
        ("2837.12", "RATE", 23, "652.54", "3489.66"),  # 652.5376 -> 652.54
        ("2837.12", "RATE", 8, "226.97", "3064.09"),  # 226.9696 -> 226.97
        ("100.10", "RATE", 23, "23.02", "123.12"),  # 23.023 -> 23.02
        ("0.05", "RATE", 8, "0.00", "0.05"),  # 0.004 -> 0.00
        ("0.07", "RATE", 8, "0.01", "0.08"),  # 0.0056 -> 0.01
        ("10.50", "RATE", 23, "2.42", "12.92"),  # 2.415 -> half up -> 2.42
        ("2837.12", "EXEMPT", None, None, "2837.12"),
        ("2837.12", None, None, None, None),
        (None, "RATE", 23, None, None),
    ],
)
def test_the_totals_are_counted_once_on_the_net_and_rounded_half_up(net, mode, rate, vat, gross):
    expected = (Decimal(vat) if vat is not None else None, Decimal(gross) if gross is not None else None)
    assert vat_totals(Decimal(net) if net is not None else None, mode, rate) == expected


# --- the document --------------------------------------------------------------------------------------------------------------------


def _with(vat_mode, vat_rate):
    return estimate(STANDARD).model_copy(update={"vat_mode": vat_mode, "vat_rate_percent": vat_rate})


def test_an_estimate_without_a_vat_prints_as_it_always_did():
    doc = build(_with(None, None))
    assert (doc.vat_mode, doc.vat_amount, doc.gross) == (None, None, None)
    html = html_of(doc)
    assert "Razem" in html and "VAT" not in html and "brutto" not in html and "netto" not in html


def test_a_rate_adds_the_vat_and_the_gross_under_the_net():
    doc = build(_with("RATE", 23))
    net = doc.total
    assert net is not None and doc.vat_amount == (net * 23 / 100).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP") and doc.gross == net + doc.vat_amount
    html = html_of(doc)
    assert "Razem netto" in html and "VAT 23%" in html and "Razem brutto" in html
    assert "kwotami netto" in html


def test_an_exempt_sale_says_so_and_adds_nothing():
    doc = build(_with("EXEMPT", None))
    assert doc.vat_amount is None and doc.gross == doc.total
    html = html_of(doc)
    assert "zw." in html and "zwolniona z podatku VAT" in html and "Razem brutto" not in html and "VAT 8%" not in html


def test_a_draft_with_unpriced_lines_has_no_vat_amounts():
    from tests.test_stage15d_estimate_document import line

    unpriced = [line(1, "Gładź", "Salon", "Ściana A", "10", None)]
    doc = build(estimate(unpriced, status=__import__("app.models.estimate", fromlist=["EstimateStatus"]).EstimateStatus.DRAFT, total=None).model_copy(update={"vat_mode": "RATE", "vat_rate_percent": 23}))
    assert doc.total is None and doc.vat_amount is None and doc.gross is None
    assert "VAT 23%" not in html_of(doc)


# --- the API -------------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD_ENABLED", True)


async def _signed_in(client: AsyncClient, db, email="jan@example.pl") -> dict:
    await PasswordLoginService(db).create_account(email, "Jan", PASSWORD)
    token = (await client.post("/api/auth/password", json={"email": email, "password": PASSWORD})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _price(client: AsyncClient, headers) -> None:
    for item in (await client.get("/api/quick-estimate/options", headers=headers)).json()["items"]:
        if item["code"] in PRICES:
            await client.patch(f"/api/price-items/{item['id']}", json={"price": PRICES[item["code"]]}, headers=headers)


async def _quick(client: AsyncClient, headers) -> dict:
    body = {
        "client_name": "Jan Kowalski", "address": "ul. Długa 5", "city": "Kraków", "rooms": [SALON], "work_codes": WORKS,
        "include_ceiling": False, "substrate": "GYPSUM_PLASTER", "quality_target": "S2",
    }
    made = await client.post("/api/quick-estimate", json=body, headers=headers)
    assert made.status_code == 201, made.text
    return made.json()


async def _profile(client: AsyncClient, headers, **vat) -> dict:
    response = await client.put("/api/executor-profile", json={"name": "Vvv Remonty", **vat}, headers=headers)
    return response


async def test_the_profile_keeps_a_vat_and_an_older_screen_never_clears_it(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    saved = await _profile(async_client, headers, vat_mode="RATE", vat_rate_percent=23)
    assert saved.status_code == 200 and (saved.json()["vat_mode"], saved.json()["vat_rate_percent"]) == ("RATE", 23)
    again = await _profile(async_client, headers)  # a body without the VAT (an older screen): the VAT stays
    assert (again.json()["vat_mode"], again.json()["vat_rate_percent"]) == ("RATE", 23)
    cleared = await _profile(async_client, headers, vat_mode=None, vat_rate_percent=None)  # an explicit null clears it
    assert (cleared.json()["vat_mode"], cleared.json()["vat_rate_percent"]) == (None, None)
    exempt = await _profile(async_client, headers, vat_mode="EXEMPT")
    assert (exempt.json()["vat_mode"], exempt.json()["vat_rate_percent"]) == ("EXEMPT", None)


@pytest.mark.parametrize("vat", [{"vat_mode": "RATE"}, {"vat_mode": "RATE", "vat_rate_percent": 5}, {"vat_mode": "EXEMPT", "vat_rate_percent": 8}, {"vat_rate_percent": 23}])
async def test_a_wrong_vat_in_the_profile_is_refused_with_a_code_and_nothing_is_saved(async_client: AsyncClient, db_session, web, vat):
    headers = await _signed_in(async_client, db_session)
    response = await _profile(async_client, headers, **vat)
    assert response.status_code == 422 and response.json()["detail"]["fields"] == {"vat": "VAT_INVALID"}
    assert (await db_session.execute(select(ExecutorProfile))).scalars().first() is None


async def test_a_new_estimate_takes_the_vat_of_the_profile_and_shows_the_gross(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    await _profile(async_client, headers, vat_mode="RATE", vat_rate_percent=23)
    made = await _quick(async_client, headers)
    body = (await async_client.get(f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}", headers=headers)).json()
    assert (body["vat_mode"], body["vat_rate_percent"]) == ("RATE", 23)
    assert Decimal(body["total"]) == Decimal("2837.12") and Decimal(body["vat_amount"]) == Decimal("652.54") and Decimal(body["gross_total"]) == Decimal("3489.66")
    listed = (await async_client.get(f"/api/projects/{made['project_id']}/estimates", headers=headers)).json()["items"][0]
    assert Decimal(listed["gross_total"]) == Decimal("3489.66")


async def test_without_a_profile_or_a_vat_an_estimate_has_none_and_shows_no_gross(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    made = await _quick(async_client, headers)
    body = (await async_client.get(f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}", headers=headers)).json()
    assert (body["vat_mode"], body["vat_rate_percent"], body["vat_amount"], body["gross_total"]) == (None, None, None, None)
    assert Decimal(body["total"]) == Decimal("2837.12")


async def test_the_vat_of_a_draft_can_be_changed_and_a_finished_estimate_keeps_it(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    await _profile(async_client, headers, vat_mode="RATE", vat_rate_percent=23)
    made = await _quick(async_client, headers)
    url = f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}"
    changed = await async_client.put(f"{url}/vat", json={"vat_mode": "RATE", "vat_rate_percent": 8}, headers=headers)
    assert changed.status_code == 200 and Decimal(changed.json()["vat_amount"]) == Decimal("226.97") and Decimal(changed.json()["gross_total"]) == Decimal("3064.09")
    exempt = await async_client.put(f"{url}/vat", json={"vat_mode": "EXEMPT"}, headers=headers)
    assert exempt.json()["vat_amount"] is None and Decimal(exempt.json()["gross_total"]) == Decimal("2837.12")
    cleared = await async_client.put(f"{url}/vat", json={}, headers=headers)
    assert cleared.json()["vat_mode"] is None and cleared.json()["gross_total"] is None
    await async_client.put(f"{url}/vat", json={"vat_mode": "RATE", "vat_rate_percent": 23}, headers=headers)
    assert (await async_client.post(f"{url}/finalize", headers=headers)).status_code == 200
    refused = await async_client.put(f"{url}/vat", json={"vat_mode": "EXEMPT"}, headers=headers)
    assert refused.status_code == 422
    kept = (await async_client.get(url, headers=headers)).json()
    assert (kept["vat_mode"], kept["vat_rate_percent"]) == ("RATE", 23)


async def test_a_new_version_after_a_finished_one_takes_the_current_vat_of_the_profile(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    await _profile(async_client, headers, vat_mode="RATE", vat_rate_percent=23)
    made = await _quick(async_client, headers)
    url = f"/api/projects/{made['project_id']}/estimates"
    assert (await async_client.post(f"{url}/{made['estimate_id']}/finalize", headers=headers)).status_code == 200
    await _profile(async_client, headers, vat_mode="EXEMPT")
    second = await async_client.post(f"{url}/generate", headers=headers)
    assert second.status_code in (200, 201), second.text
    versions = {e.version: e for e in (await db_session.execute(select(Estimate))).scalars()}
    assert (versions[1].vat_mode, versions[1].vat_rate_percent) == ("RATE", 23)
    assert (versions[2].vat_mode, versions[2].vat_rate_percent) == ("EXEMPT", None)


@pytest.mark.parametrize("body", [{"vat_mode": "RATE"}, {"vat_mode": "RATE", "vat_rate_percent": 5}, {"vat_mode": "EXEMPT", "vat_rate_percent": 8}, {"vat_rate_percent": 23}])
async def test_a_wrong_vat_of_an_estimate_is_refused_and_nothing_changes(async_client: AsyncClient, db_session, web, body):
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    made = await _quick(async_client, headers)
    url = f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}"
    response = await async_client.put(f"{url}/vat", json=body, headers=headers)
    assert response.status_code == 422
    assert (await async_client.get(url, headers=headers)).json()["vat_mode"] is None


async def test_another_owners_estimate_is_not_found(async_client: AsyncClient, db_session, web):
    first = await _signed_in(async_client, db_session)
    await _price(async_client, first)
    made = await _quick(async_client, first)
    other = await _signed_in(async_client, db_session, "ola@example.pl")
    url = f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}/vat"
    assert (await async_client.put(url, json={"vat_mode": "EXEMPT"}, headers=other)).status_code == 404


async def test_the_vat_route_needs_a_token(async_client: AsyncClient):
    assert (await async_client.put("/api/projects/00000000-0000-0000-0000-000000000000/estimates/00000000-0000-0000-0000-000000000000/vat", json={})).status_code == 401
