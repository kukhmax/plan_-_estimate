"""Owner 2026-10-27: an estimate whose prices already include the VAT ("вычесть НДС из сметы") -- the VAT is taken out of the sum, not added on top."""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect, text

from app.domain.client_link import estimate_hash
from app.domain.rules.vat import vat_split, vat_totals
from tests.test_stage15d_estimate_document import STANDARD, build, estimate, html_of
from tests.test_stage16e2_contract import contract_engine, load_migration, run
from tests.test_v2_6_vat import _price, _profile, _quick, _signed_in, web  # noqa: F401  (the fixture is used by name)


@pytest.mark.parametrize(
    "gross,rate,net,vat",
    [
        ("3064.09", 8, "2837.12", "226.97"),  # the gross of a net 2837.12 + 8 % gives the net back
        ("3489.66", 23, "2837.12", "652.54"),
        ("100.00", 23, "81.30", "18.70"),  # 81.3008 -> 81.30, the VAT is the rest
        ("108.00", 8, "100.00", "8.00"),
        ("0.01", 8, "0.01", "0.00"),
    ],
)
def test_the_vat_is_taken_out_of_a_gross_sum_and_net_plus_vat_is_the_gross(gross, rate, net, vat):
    split = vat_split(Decimal(gross), "RATE", rate, included=True)
    assert split == (Decimal(net), Decimal(vat), Decimal(gross))
    assert split[0] + split[1] == split[2]
    assert vat_totals(Decimal(gross), "RATE", rate, True) == (Decimal(vat), Decimal(gross))


def test_included_means_nothing_without_a_rate():
    assert vat_split(Decimal("100"), "EXEMPT", None, included=True) == (Decimal("100"), None, Decimal("100"))
    assert vat_split(Decimal("100"), None, None, included=True) == (Decimal("100"), None, None)
    assert vat_split(None, "RATE", 8, included=True) == (None, None, None)


def test_net_prices_are_counted_as_before():
    assert vat_split(Decimal("2837.12"), "RATE", 8) == (Decimal("2837.12"), Decimal("226.97"), Decimal("3064.09"))


# --- the document --------------------------------------------------------------------------------------------------------------------


def test_the_pdf_of_gross_prices_shows_the_gross_and_takes_the_net_and_the_vat_out():
    doc = build(estimate(STANDARD).model_copy(update={"vat_mode": "RATE", "vat_rate_percent": 8, "vat_included": True}))
    assert doc.vat_included is True and doc.gross == doc.total and doc.net + doc.vat_amount == doc.total
    html = html_of(doc)
    assert "Razem brutto" in html and "w tym wartość netto" in html and "w tym VAT 8%" in html and "kwotami brutto" in html
    assert "Razem netto" not in html


def test_the_pdf_of_net_prices_is_unchanged():
    html = html_of(build(estimate(STANDARD).model_copy(update={"vat_mode": "RATE", "vat_rate_percent": 8})))
    assert "Razem netto" in html and "w tym VAT" not in html and "kwotami netto" in html


def test_the_hash_of_an_estimate_made_before_does_not_change():
    plain = estimate(STANDARD).model_copy(update={"vat_mode": "RATE", "vat_rate_percent": 8})
    assert estimate_hash(plain) == estimate_hash(plain.model_copy(update={"vat_included": False}))
    assert estimate_hash(plain) != estimate_hash(plain.model_copy(update={"vat_included": True}))


# --- the API -------------------------------------------------------------------------------------------------------------------------


async def test_a_draft_can_say_its_prices_include_the_vat(async_client: AsyncClient, db_session, web):  # noqa: F811
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    await _profile(async_client, headers, vat_mode="RATE", vat_rate_percent=8)
    made = await _quick(async_client, headers)
    url = f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}"
    added = (await async_client.get(url, headers=headers)).json()
    assert added["vat_included"] is False and Decimal(added["net_total"]) == Decimal("2837.12") and Decimal(added["gross_total"]) == Decimal("3064.09")

    put = await async_client.put(f"{url}/vat", json={"vat_mode": "RATE", "vat_rate_percent": 8, "vat_included": True}, headers=headers)
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["vat_included"] is True
    assert Decimal(body["total"]) == Decimal("2837.12")  # the lines do not change
    assert Decimal(body["gross_total"]) == Decimal("2837.12") and Decimal(body["net_total"]) == Decimal("2626.96") and Decimal(body["vat_amount"]) == Decimal("210.16")
    full = (await async_client.get(url, headers=headers)).json()
    assert full["vat_included"] is True and Decimal(full["net_total"]) == Decimal("2626.96")
    listed = (await async_client.get(f"/api/projects/{made['project_id']}/estimates", headers=headers)).json()["items"][0]
    assert listed["vat_included"] is True and Decimal(listed["vat_amount"]) == Decimal("210.16")

    back = await async_client.put(f"{url}/vat", json={"vat_mode": "RATE", "vat_rate_percent": 8}, headers=headers)  # an older screen: added on top again
    assert back.json()["vat_included"] is False and Decimal(back.json()["gross_total"]) == Decimal("3064.09")


async def test_included_is_dropped_for_exempt_and_for_no_vat(async_client: AsyncClient, db_session, web):  # noqa: F811
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    made = await _quick(async_client, headers)
    url = f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}/vat"
    exempt = (await async_client.put(url, json={"vat_mode": "EXEMPT", "vat_included": True}, headers=headers)).json()
    assert exempt["vat_included"] is False and Decimal(exempt["gross_total"]) == Decimal("2837.12")
    none = (await async_client.put(url, json={"vat_included": True}, headers=headers)).json()
    assert none["vat_included"] is False and none["gross_total"] is None


# --- the migration -------------------------------------------------------------------------------------------------------------------


def test_revision_chain():
    module = load_migration("0087_estimate_vat_included")
    assert module.down_revision == "0086_transfer_source" and len(module.revision) <= 32


def test_the_migration_adds_a_false_flag_and_the_downgrade_drops_it():
    engine = contract_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE estimates (id CHAR(32) PRIMARY KEY, vat_mode VARCHAR(8), vat_rate_percent INTEGER)"))
        conn.execute(text("INSERT INTO estimates (id, vat_mode, vat_rate_percent) VALUES ('a', 'RATE', 8)"))
    run(engine, "0087_estimate_vat_included", "upgrade")
    column = next(c for c in inspect(engine).get_columns("estimates") if c["name"] == "vat_included")
    assert column["nullable"] is False
    with engine.connect() as conn:
        assert conn.execute(text("SELECT vat_included FROM estimates")).scalar() in (False, 0)
    run(engine, "0087_estimate_vat_included", "downgrade")
    assert "vat_included" not in {c["name"] for c in inspect(engine).get_columns("estimates")}
