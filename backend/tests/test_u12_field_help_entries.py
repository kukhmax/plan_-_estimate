"""U-12 — the "?" help at the fields Podłoże / Klasa jakości reads the knowledge base by the substrate and the quality of an entry.

The attachment is data in the catalogue (no schema change): the list of titles carries `substrates` and `qualities`, so the
screen finds the entries of a field with one cached request. A substrate or a class without any entry gets no help button.
"""

from httpx import AsyncClient

from app.domain.knowledge.catalog import CATALOG_DIR, application_references, read_catalog
from app.models.checklist import QualityLevel, Substrate
from tests.test_clients import VALID_USER, auth_header, get_token

CATALOG = read_catalog(CATALOG_DIR, application_references())


def test_every_substrate_has_at_least_one_technical_entry():
    for substrate in Substrate:
        assert any(substrate.value in entry.substrates for entry in CATALOG.entries), substrate


def test_every_quality_class_is_explained_by_an_entry():
    explained = {quality for entry in CATALOG.entries for quality in entry.qualities}
    assert explained == {level.value for level in QualityLevel}  # Q1-Q4 (drywall) and S1-S4 (the contractor's own standard)


def test_the_coefficient_help_has_its_entry_and_it_is_a_draft_until_the_owner_approves():
    found = [entry for entry in CATALOG.entries if "wspolczynnik" in entry.tags]
    assert [entry.code for entry in found] == ["APP.COEFFICIENT"] and found[0].status == "DRAFT"
    assert "S1" in next(e for e in CATALOG.entries if e.code == "APP.QUALITY-S").summary_pl  # the classes are not price coefficients


async def test_the_list_tells_where_an_entry_applies(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    body = (await async_client.get("/api/knowledge/entries", params={"limit": 200}, headers=headers)).json()
    by_code = {item["code"]: item for item in body["items"]}
    assert by_code["TECH.GK-Q"]["qualities"] == ["Q1", "Q2", "Q3", "Q4"]
    assert "GYPSUM_BOARD" in by_code["TECH.GK-Q"]["substrates"]
    assert by_code["KC.627"]["substrates"] == [] and by_code["KC.627"]["qualities"] == []
