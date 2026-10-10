"""Stage 17B — the knowledge base: the files and their checks, the search, the read-only API.

The test catalogue below is invented (a "test act" and a "test norm"): Stage 17B holds no real legal text.
"""

import copy
import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.api.v1.endpoints import knowledge as knowledge_endpoint
from app.domain.knowledge.catalog import (
    CATALOG_DIR,
    KnowledgeCatalogError,
    application_references,
    read_catalog,
)
from app.domain.knowledge.search import Filters, fold, search, words
from tests.test_clients import VALID_USER, auth_header, get_token

REFS = application_references()
PHRASE = min(REFS.phrases)
RISK = min(REFS.risks)
CLAUSE = min(REFS.clauses)

APPROVED = {"status": "APPROVED", "approved_by": "Właściciel", "approved_on": "2026-10-11", "checked_on": "2026-10-10"}

SAMPLE = {
    "meta": {"version": 3, "updated_on": "2026-10-11", "disclaimer_pl": None, "disclaimer_ru": None, "disclaimer_status": "DRAFT"},
    "sources": [
        {"code": "TEST_ACT", "kind": "STATUTE", "title_pl": "Ustawa testowa o robotach", "designation": "Dz.U. TEST poz. 1",
         "url": "https://example.org/act", **APPROVED},
        {"code": "TEST_NORM", "kind": "NORM", "title_pl": "Norma testowa farb", "designation": "PN-EN TEST-1", "status": "DRAFT"},
    ],
    "entries": [
        {"code": "ACT.1", "source": "TEST_ACT", "locator": "art. 1", "title_pl": "Rękojmia za wady robót",
         "title_ru": "Ответственность за недостатки", "summary_pl": "Wykonawca odpowiada za wady.", "explanation_ru": "Пояснение.",
         "tags": ["rekojmia", "odbior"], "works": ["SKIM_COAT"], "substrates": ["CONCRETE"], "qualities": ["S2"], **APPROVED},
        {"code": "ACT.2", "source": "TEST_ACT", "locator": "art. 2", "title_pl": "Odbiór robót", "title_ru": "Приёмка работ",
         "summary_pl": "Zasady odbioru, rękojmia nie dotyczy.", "tags": ["odbior"], "status": "DRAFT"},
        {"code": "NORM.1", "source": "TEST_NORM", "locator": "pkt 4", "title_pl": "Łódź — farby wewnętrzne",
         "title_ru": "Ёлка — краски для помещений", "tags": ["farby", "rekojmia"], "works": ["PAINTING"], "status": "DRAFT"},
    ],
    "situations": [
        {"code": "SIT.PRIMER", "status": "DRAFT", "title_pl": "Klient odmawia gruntowania", "title_ru": "Клиент отказывается от грунтовки",
         "start": "q1",
         "questions": [
             {"id": "q1", "text_pl": "Czy klient podpisze protokół?", "text_ru": "Подпишет ли клиент протокол?",
              "answers": [{"text_pl": "Tak", "text_ru": "Да", "next": "signs"}, {"text_pl": "Nie", "text_ru": "Нет", "next": "q2"}]},
             {"id": "q2", "text_pl": "Czy jest świadek?", "text_ru": "Есть ли свидетель?",
              "answers": [{"text_pl": "Tak", "text_ru": "Да", "next": "witness"}, {"text_pl": "Nie", "text_ru": "Нет", "next": "alone"}]},
         ],
         "outcomes": [
             {"id": "signs", "steps_pl": ["Wydaj protokół decyzji."], "steps_ru": ["Выдайте протокол решений."],
              "entries": ["ACT.1"], "phrases": [PHRASE], "documents": ["DECISION_PROTOCOL"]},
             {"id": "witness", "steps_pl": ["Zapisz świadka."], "steps_ru": ["Запишите свидетеля."], "lawyer": True},
             {"id": "alone", "steps_pl": ["Zapisz odmowę podpisu."], "steps_ru": ["Запишите отказ от подписи."]},
         ]},
    ],
    "links": [
        {"target_kind": "RISK", "target": RISK, "entries": ["ACT.1", "NORM.1"]},
        {"target_kind": "CLAUSE", "target": CLAUSE, "entries": ["ACT.2"]},
        {"target_kind": "DOCUMENT", "target": "DECISION_PROTOCOL", "entries": ["ACT.1"]},
    ],
}


def write(directory: Path, data: dict) -> Path:
    for name, file_name in (("meta", "meta.json"), ("sources", "sources.json"), ("entries", "entries.json"),
                            ("situations", "situations.json"), ("links", "links.json")):
        (directory / file_name).write_text(json.dumps(data[name], ensure_ascii=False), encoding="utf-8")
    return directory


def sample() -> dict:
    return copy.deepcopy(SAMPLE)


def load(tmp_path: Path, data: dict | None = None):
    return read_catalog(write(tmp_path, data or sample()), REFS)


# --- the files of the repository ---------------------------------------------------------------------------------------------


def test_the_repository_catalogue_is_valid():
    catalog = read_catalog(CATALOG_DIR, REFS)
    assert catalog.meta.version >= 1
    assert catalog.meta.disclaimer_status == "DRAFT"  # the lawyer has not approved a disclaimer yet (Q9)
    # the content itself (Stage 17C onwards) is checked in tests/test_stage17c_knowledge_content.py


def test_a_norm_tells_its_key_points_in_own_words_and_links_its_source(tmp_path):
    data = sample()
    data["entries"][2].update(summary_pl="Kluczowe punkty normy, własnymi słowami.", explanation_ru="Ключевые моменты своими словами.")
    catalog = load(tmp_path, data)
    assert catalog.entry("NORM.1").summary_pl.startswith("Kluczowe punkty")


def test_a_valid_catalogue_is_read_with_its_links(tmp_path):
    catalog = load(tmp_path)
    assert [e.code for e in catalog.entries] == ["ACT.1", "ACT.2", "NORM.1"]
    assert catalog.source("TEST_ACT").status == "APPROVED"
    assert [link.target_kind for link in catalog.links_to("ACT.1")] == ["RISK", "DOCUMENT"]
    assert catalog.situation("SIT.PRIMER").start == "q1"


# --- every rule of the content -----------------------------------------------------------------------------------------------


def broken(change):
    data = sample()
    change(data)
    return data


CASES = {
    "duplicate entry": (lambda d: d["entries"].append(copy.deepcopy(d["entries"][0])), "duplicate 'ACT.1'"),
    "unknown source": (lambda d: d["entries"][1].update(source="NOPE"), "unknown source 'NOPE'"),
    "approved entry, draft source": (lambda d: d["entries"][2].update(**APPROVED), "its source 'TEST_NORM' is not"),
    "approved without the key points": (lambda d: d["entries"][0].pop("summary_pl"), "tells its key points"),
    "approved with a source without a link": (lambda d: d["sources"][0].pop("url"), "links its source"),
    "approved without a check date": (lambda d: d["entries"][0].pop("checked_on"), "checked_on"),
    "draft signed by someone": (lambda d: d["entries"][1].update(approved_by="X"), "not approved by anyone"),
    "unknown work": (lambda d: d["entries"][0].update(works=["DIGGING"]), "unknown works"),
    "unknown substrate": (lambda d: d["entries"][0].update(substrates=["SAND"]), "unknown substrates"),
    "unknown quality": (lambda d: d["entries"][0].update(qualities=["S9"]), "unknown qualities"),
    "tag with capitals": (lambda d: d["entries"][0].update(tags=["Rekojmia"]), "lowercase"),
    "wrong code": (lambda d: d["entries"][0].update(code="act 1"), "code"),
    "extra field": (lambda d: d["entries"][0].update(text_of_norm="..."), "text_of_norm"),
    "plain http link": (lambda d: d["sources"][0].update(url="http://example.org"), "url"),
    "start is not a question": (lambda d: d["situations"][0].update(start="signs"), "is not a question"),
    "answer to nowhere": (lambda d: d["situations"][0]["questions"][0]["answers"][1].update(next="nowhere"), "unknown 'nowhere'"),
    "answers come back": (lambda d: d["situations"][0]["questions"][1]["answers"][1].update(next="q1"), "come back to 'q1'"),
    "outcome never reached": (lambda d: d["situations"][0]["outcomes"].append({"id": "orphan", "steps_pl": ["x"], "steps_ru": ["x"]}), "never reached ['orphan']"),
    "one answer only": (lambda d: d["situations"][0]["questions"][0].update(answers=d["situations"][0]["questions"][0]["answers"][:1]), "answers"),
    "steps not translated": (lambda d: d["situations"][0]["outcomes"][0].update(steps_ru=["a", "b"]), "same number of steps"),
    "unknown entry in an outcome": (lambda d: d["situations"][0]["outcomes"][0].update(entries=["NOPE"]), "unknown entry 'NOPE'"),
    "unknown phrase": (lambda d: d["situations"][0]["outcomes"][0].update(phrases=["COMM_NOPE"]), "unknown phrase"),
    "unknown document": (lambda d: d["situations"][0]["outcomes"][0].update(documents=["LETTER"]), "unknown document"),
    "a risk the application does not have": (lambda d: d["links"][0].update(target="NO_SUCH_RISK"), "no such risk"),
    "a clause the application does not have": (lambda d: d["links"][1].update(target="definitions.999"), "no such clause"),
    "a link to an unknown entry": (lambda d: d["links"][2].update(entries=["NOPE"]), "unknown entry 'NOPE'"),
    "the same place linked twice": (lambda d: d["links"].append(copy.deepcopy(d["links"][0])), "duplicate"),
    "approved disclaimer without text": (lambda d: d["meta"].update(disclaimer_status="APPROVED"), "disclaimer"),
}


@pytest.mark.parametrize("case", CASES)
def test_a_wrong_catalogue_is_refused_with_the_reason(tmp_path, case):
    change, reason = CASES[case]
    with pytest.raises(KnowledgeCatalogError) as refused:
        load(tmp_path, broken(change))
    assert reason in str(refused.value)


def test_a_missing_or_broken_file_is_refused(tmp_path):
    write(tmp_path, sample())
    (tmp_path / "links.json").unlink()
    with pytest.raises(KnowledgeCatalogError, match="links.json"):
        read_catalog(tmp_path, REFS)
    (tmp_path / "links.json").write_text("[ not json", encoding="utf-8")
    with pytest.raises(KnowledgeCatalogError, match="links.json"):
        read_catalog(tmp_path, REFS)


# --- the search --------------------------------------------------------------------------------------------------------------


def test_letters_are_compared_without_marks_and_case():
    assert fold("Rękojmia ŁÓDŹ żółć") == "rekojmia lodz zolc"
    assert fold("Ёлка Йод") == "елка иод"
    assert words("art. 638 § 1 KC — rękojmia") == ["art", "638", "1", "kc", "rekojmia"]


def test_every_word_must_be_found_at_the_start_of_a_word(tmp_path):
    catalog = load(tmp_path)
    assert [e.code for e in search(catalog, "rekoj")] == ["ACT.1", "NORM.1", "ACT.2"]
    assert [e.code for e in search(catalog, "Rękojmia wady")] == ["ACT.1"]
    assert search(catalog, "rekoj nieistnieje") == []
    assert search(catalog, "ojmia") == []  # not from the middle of a word
    assert [e.code for e in search(catalog, "лодз")] == []  # Latin "Łódź" is not Cyrillic
    assert [e.code for e in search(catalog, "елка")] == ["NORM.1"]


def test_the_order_is_explainable_title_then_tags_then_place_then_text(tmp_path):
    catalog = load(tmp_path)
    # "rekojmia": in the title of ACT.1 (100), in the tags of NORM.1 (50), only in the text of ACT.2 (10)
    assert [e.code for e in search(catalog, "rekojmia")] == ["ACT.1", "NORM.1", "ACT.2"]
    # the exact code first, whatever the words
    assert search(catalog, "ACT.2")[0].code == "ACT.2"
    # the place in the source and the designation are searched too
    assert [e.code for e in search(catalog, "pkt 4")] == ["NORM.1"]
    assert [e.code for e in search(catalog, "dz.u.")] == ["ACT.1", "ACT.2"]


def test_an_empty_query_lists_the_titles_alphabetically_without_marks(tmp_path):
    catalog = load(tmp_path)
    assert [e.title_pl for e in search(catalog)] == ["Łódź — farby wewnętrzne", "Odbiór robót", "Rękojmia za wady robót"]


def test_filters_narrow_the_list(tmp_path):
    catalog = load(tmp_path)
    def codes(f: Filters) -> list[str]:
        return [e.code for e in search(catalog, "", f)]

    assert codes(Filters(kind="NORM")) == ["NORM.1"]
    assert codes(Filters(source="TEST_ACT")) == ["ACT.2", "ACT.1"]
    assert codes(Filters(tag="odbior")) == ["ACT.2", "ACT.1"]
    assert codes(Filters(work="PAINTING")) == ["NORM.1"]
    assert codes(Filters(substrate="CONCRETE")) == ["ACT.1"]
    assert codes(Filters(quality="S2")) == ["ACT.1"]
    assert codes(Filters(status="APPROVED")) == ["ACT.1"]
    assert codes(Filters(status="DRAFT", kind="STATUTE")) == ["ACT.2"]


def test_the_search_is_the_same_every_time(tmp_path):
    catalog = load(tmp_path)
    first = [e.code for e in search(catalog, "o")]
    assert all([e.code for e in search(catalog, "o")] == first for _ in range(5))


# --- the API -----------------------------------------------------------------------------------------------------------------


@pytest.fixture
def knowledge(tmp_path, monkeypatch):
    catalog = load(tmp_path)
    monkeypatch.setattr(knowledge_endpoint, "load_knowledge_catalog", lambda: catalog)
    return catalog


ROUTES = ["/api/knowledge/meta", "/api/knowledge/entries", "/api/knowledge/entries/ACT.1", "/api/knowledge/situations",
          "/api/knowledge/situations/SIT.PRIMER", f"/api/knowledge/links?target_kind=RISK&target={RISK}"]


@pytest.mark.parametrize("route", ROUTES)
async def test_every_route_needs_a_token(async_client: AsyncClient, knowledge, route):
    assert (await async_client.get(route)).status_code == 401


@pytest.mark.parametrize("route", ROUTES[:2])
async def test_nothing_can_be_written(async_client: AsyncClient, knowledge, route):
    headers = auth_header(await get_token(async_client, VALID_USER))
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert (await async_client.request(method, route, headers=headers)).status_code == 405


async def test_meta_tells_the_version_the_counts_and_the_draft_disclaimer(async_client: AsyncClient, knowledge):
    body = (await async_client.get("/api/knowledge/meta", headers=auth_header(await get_token(async_client, VALID_USER)))).json()
    assert body == {"version": 3, "updated_on": "2026-10-11", "disclaimer_pl": None, "disclaimer_ru": None,
                    "disclaimer_status": "DRAFT", "sources": 2, "entries": 3, "situations": 1}


async def test_the_list_is_titles_first_with_what_is_needed_to_choose(async_client: AsyncClient, knowledge):
    headers = auth_header(await get_token(async_client, VALID_USER))
    body = (await async_client.get("/api/knowledge/entries", headers=headers)).json()
    assert body["total"] == 3
    assert [i["code"] for i in body["items"]] == ["NORM.1", "ACT.2", "ACT.1"]
    assert body["items"][2] == {
        "code": "ACT.1", "kind": "STATUTE", "source": "TEST_ACT", "source_designation": "Dz.U. TEST poz. 1", "locator": "art. 1",
        "title_pl": "Rękojmia za wady robót", "title_ru": "Ответственность за недостатки", "status": "APPROVED",
        "tags": ["rekojmia", "odbior"],
    }
    found = (await async_client.get("/api/knowledge/entries", params={"q": "rekojmia", "kind": "STATUTE"}, headers=headers)).json()
    assert [i["code"] for i in found["items"]] == ["ACT.1", "ACT.2"]
    page = (await async_client.get("/api/knowledge/entries", params={"limit": 1, "offset": 1}, headers=headers)).json()
    assert page["total"] == 3 and [i["code"] for i in page["items"]] == ["ACT.2"]
    drafts = (await async_client.get("/api/knowledge/entries", params={"status": "DRAFT"}, headers=headers)).json()
    assert [i["code"] for i in drafts["items"]] == ["NORM.1", "ACT.2"]


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "kind=LAW", "status=OK", f"q={'x' * 101}"])
async def test_a_wrong_query_is_a_plain_422(async_client: AsyncClient, knowledge, query):
    headers = auth_header(await get_token(async_client, VALID_USER))
    assert (await async_client.get(f"/api/knowledge/entries?{query}", headers=headers)).status_code == 422


async def test_one_entry_with_its_source_and_where_it_is_linked_from(async_client: AsyncClient, knowledge):
    headers = auth_header(await get_token(async_client, VALID_USER))
    body = (await async_client.get("/api/knowledge/entries/ACT.1", headers=headers)).json()
    assert body["entry"]["summary_pl"] == "Wykonawca odpowiada za wady."
    assert body["source"]["designation"] == "Dz.U. TEST poz. 1"
    assert [(link["target_kind"], link["target"]) for link in body["linked_from"]] == [("RISK", RISK), ("DOCUMENT", "DECISION_PROTOCOL")]
    missing = await async_client.get("/api/knowledge/entries/NOPE", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "KNOWLEDGE_ENTRY_NOT_FOUND"


async def test_the_situations_and_one_situation_with_its_tree(async_client: AsyncClient, knowledge):
    headers = auth_header(await get_token(async_client, VALID_USER))
    listed = (await async_client.get("/api/knowledge/situations", headers=headers)).json()
    assert listed == {"items": [{"code": "SIT.PRIMER", "title_pl": "Klient odmawia gruntowania",
                                 "title_ru": "Клиент отказывается от грунтовки", "status": "DRAFT"}]}
    one = (await async_client.get("/api/knowledge/situations/SIT.PRIMER", headers=headers)).json()
    assert one["start"] == "q1" and [q["id"] for q in one["questions"]] == ["q1", "q2"]
    assert one["outcomes"][0]["documents"] == ["DECISION_PROTOCOL"] and one["outcomes"][1]["lawyer"] is True
    missing = await async_client.get("/api/knowledge/situations/NOPE", headers=headers)
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "KNOWLEDGE_SITUATION_NOT_FOUND"


async def test_the_entries_of_a_place_in_the_application_and_none_for_an_unlinked_one(async_client: AsyncClient, knowledge):
    headers = auth_header(await get_token(async_client, VALID_USER))
    body = (await async_client.get("/api/knowledge/links", params={"target_kind": "RISK", "target": RISK}, headers=headers)).json()
    assert [i["code"] for i in body["entries"]] == ["ACT.1", "NORM.1"]
    none = (await async_client.get("/api/knowledge/links", params={"target_kind": "PHRASE", "target": PHRASE}, headers=headers)).json()
    assert none == {"target_kind": "PHRASE", "target": PHRASE, "entries": []}
    assert (await async_client.get("/api/knowledge/links", params={"target_kind": "LAW", "target": "x"}, headers=headers)).status_code == 422


async def test_the_link_index_gives_every_place_with_its_entries_in_one_answer(async_client: AsyncClient, knowledge):
    headers = auth_header(await get_token(async_client, VALID_USER))
    assert (await async_client.get("/api/knowledge/links/index")).status_code in (401, 403)
    body = (await async_client.get("/api/knowledge/links/index", headers=headers)).json()
    assert [(i["target_kind"], i["target"]) for i in body["items"]] == [("RISK", RISK), ("CLAUSE", CLAUSE), ("DOCUMENT", "DECISION_PROTOCOL")]
    first = body["items"][0]
    assert [e["code"] for e in first["entries"]] == ["ACT.1", "NORM.1"]
    assert first["entries"][0]["title_pl"] == "Rękojmia za wady robót"  # the row of the list, enough to name the entry


async def test_a_broken_catalogue_is_a_plain_500_not_a_guess(async_client: AsyncClient, monkeypatch):
    def refuse():
        raise KnowledgeCatalogError("entries.json: broken")

    monkeypatch.setattr(knowledge_endpoint, "load_knowledge_catalog", refuse)
    response = await async_client.get("/api/knowledge/entries", headers=auth_header(await get_token(async_client, VALID_USER)))
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "KNOWLEDGE_UNAVAILABLE"
    assert "broken" not in response.text  # the reason is for the log, not for the screen


async def test_the_application_does_not_start_on_a_broken_catalogue(monkeypatch):
    from app import main

    def refuse():
        raise KnowledgeCatalogError("sources.json: broken")

    monkeypatch.setattr(main, "load_knowledge_catalog", refuse)
    with pytest.raises(KnowledgeCatalogError):
        async with main.lifespan(main.app):
            pass
