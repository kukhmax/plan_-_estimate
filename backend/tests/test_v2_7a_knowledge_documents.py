"""V2-7a -- the owner's own documents of the knowledge base: the rules, the API (add, change, search, the file, send to the chat), the owner's wall."""
import pytest
from sqlalchemy import select

from app.api.deps import get_document_delivery
from app.domain import knowledge_documents as rules
from app.domain.exceptions import (
    DocumentChatUnavailableError,
    DocumentDeliveryDisabledError,
)
from app.domain.knowledge_documents import OwnDocumentError
from app.main import app
from app.models.knowledge_document import KnowledgeDocument, KnowledgeDocumentFile
from tests.test_apply_template import _login
from tests.test_stage13h_execution_api import OTHER_USER

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
URL = "/api/knowledge/documents"


# --- the rules -----------------------------------------------------------------------------------------------------------------------


def test_tags_are_split_cleaned_and_made_unique_without_regard_to_case_and_accents():
    assert rules.normalise_tags("Grunt, #knauf ; GRUNT\n  gładź  gipsowa ,,") == ["Grunt", "knauf", "gładź gipsowa"]
    assert rules.normalise_tags(["Ścian", "scian"]) == ["Ścian"]
    assert rules.normalise_tags(None) == []
    with pytest.raises(OwnDocumentError) as many:
        rules.normalise_tags(",".join(f"t{i}" for i in range(11)))
    assert many.value.code == "TOO_MANY_TAGS"
    with pytest.raises(OwnDocumentError) as long:
        rules.normalise_tags("x" * 31)
    assert long.value.code == "TAG_TOO_LONG"


@pytest.mark.parametrize("url", ["https://www.knauf.pl/karta.pdf", "http://example.com/a?b=1", " https://a.pl/x "])
def test_a_link_is_http_or_https(url):
    assert rules.check_url(url) == url.strip()


@pytest.mark.parametrize("url", ["ftp://x.pl/a", "javascript:alert(1)", "knauf.pl/karta", "https://", "https://a b.pl", "//x.pl"])
def test_any_other_link_is_refused(url):
    with pytest.raises(OwnDocumentError) as error:
        rules.check_url(url)
    assert error.value.code == "URL_INVALID" and error.value.field == "source_url"
    assert rules.check_url("  ") is None


def test_the_file_is_judged_by_its_first_bytes_and_its_name_is_made_safe():
    assert rules.sniff_file(PDF) == ("application/pdf", ".pdf")
    assert rules.sniff_file(JPEG) == ("image/jpeg", ".jpg")
    assert rules.sniff_file(PNG) == ("image/png", ".png")
    for bad in (b"MZ\x90\x00", b"<html>", b"PK\x03\x04", b"GIF89a"):
        with pytest.raises(OwnDocumentError) as error:
            rules.sniff_file(bad)
        assert error.value.code == "FILE_TYPE_UNSUPPORTED"
    assert rules.safe_filename("../../etc/Karta Techniczna <1>.exe", ".pdf") == "Karta Techniczna 1.pdf"
    assert rules.safe_filename("C:\\dir\\Norma PN-EN 13300.PDF", ".pdf") == "Norma PN-EN 13300.pdf"
    assert rules.safe_filename("", ".png") == "document.png" and rules.safe_filename(None, ".jpg") == "document.jpg"
    with pytest.raises(OwnDocumentError) as empty:
        rules.check_file(b"")
    assert empty.value.code == "FILE_EMPTY"


def test_the_fields_are_cleaned_and_a_title_is_required():
    fields = rules.build_fields(title="  Karta   Knauf  ", kind="manufacturer", source_url="", doc_date="2026-03-01", when_to_use=" ", body="  ", tags="a,b")
    assert (fields.title, fields.kind, fields.source_url, str(fields.doc_date), fields.when_to_use, fields.body, fields.tags) == (
        "Karta Knauf", "MANUFACTURER", None, "2026-03-01", None, None, ["a", "b"])
    for bad, code in ((dict(title=" "), "TITLE_REQUIRED"), (dict(kind="X"), "KIND_UNKNOWN"), (dict(doc_date="01.03.2026"), "DATE_INVALID"),
                      (dict(title="x" * 201), "TOO_LONG"), (dict(body="x" * 100_001), "TOO_LONG")):
        base = dict(title="T", kind="OTHER", source_url=None, doc_date=None, when_to_use=None, body=None, tags=None)
        with pytest.raises(OwnDocumentError) as error:
            rules.build_fields(**{**base, **bad})
        assert error.value.code == code


def test_the_search_wants_every_word_at_the_beginning_of_a_word_and_ranks_the_title_first():
    def s(query, **kw):
        base = dict(title="Karta techniczna gruntu", tags=["Knauf"], when_to_use="przed gładzią", file_name="karta.pdf", body="Grunt głęboko penetrujący")
        return rules.score(query, **{**base, **kw})

    assert s("") == 0
    assert s("kart") == 100 + 0 or s("kart") == 100
    assert s("grunt knauf") == 100 + 50
    assert s("glad") == 30  # "gładzią": the letters are compared without their marks
    assert s("grunt rekojmia") is None
    assert s("penetruj") == 10


# --- the API -------------------------------------------------------------------------------------------------------------------------


def form(**fields):
    return {"title": "Karta techniczna gruntu", "kind": "MANUFACTURER", **fields}


def files(content=PDF, name="Karta Knauf.pdf"):
    return {"file": (name, content, "application/octet-stream")}


async def add(client, headers, data=None, upload=None):
    return await client.post(URL, headers=headers, data=data if data is not None else form(), files=upload)


async def test_a_document_with_a_text_is_added_read_changed_and_deleted(async_client, db_session):
    headers, _ = await _login(async_client, db_session)
    made = await add(async_client, headers, form(body="Gruntować przed gładzią.\nDwa razy.", tags="grunt, Knauf", doc_date="2026-03-01", when_to_use="Przed gładzią"))
    assert made.status_code == 201, made.text
    doc = made.json()
    assert (doc["title"], doc["kind"], doc["tags"], doc["doc_date"], doc["has_text"], doc["file_name"]) == (
        "Karta techniczna gruntu", "MANUFACTURER", ["grunt", "Knauf"], "2026-03-01", True, None)
    assert doc["snippet"] == "Gruntować przed gładzią. Dwa razy." and doc["body"].startswith("Gruntować") and doc["when_to_use"] == "Przed gładzią"
    one = await async_client.get(f"{URL}/{doc['id']}", headers=headers)
    assert one.status_code == 200 and one.json()["body"] == doc["body"]
    listed = (await async_client.get(URL, headers=headers)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == doc["id"] and "body" not in listed["items"][0]
    assert listed["max_documents"] == 100 and listed["max_file_bytes"] == 10_000_000
    changed = await async_client.put(f"{URL}/{doc['id']}", headers=headers, data=form(title="Nowa nazwa", kind="NORM", body="Tekst", source_url="https://knauf.pl/x"))
    assert changed.status_code == 200, changed.text
    assert (changed.json()["title"], changed.json()["kind"], changed.json()["source_url"], changed.json()["tags"], changed.json()["doc_date"]) == ("Nowa nazwa", "NORM", "https://knauf.pl/x", [], None)
    assert (await async_client.delete(f"{URL}/{doc['id']}", headers=headers)).status_code == 204
    assert (await async_client.get(f"{URL}/{doc['id']}", headers=headers)).status_code == 404
    assert (await async_client.delete(f"{URL}/{doc['id']}", headers=headers)).status_code == 404


async def test_a_file_is_stored_beside_the_document_served_back_replaced_and_removed(async_client, db_session):
    headers, _ = await _login(async_client, db_session)
    made = await add(async_client, headers, form(), files(PDF, "../Karta Knauf?.pdf"))
    assert made.status_code == 201, made.text
    doc = made.json()
    assert (doc["file_name"], doc["file_mime"], doc["file_size"], doc["has_text"]) == ("Karta Knauf.pdf", "application/pdf", len(PDF), False)
    got = await async_client.get(f"{URL}/{doc['id']}/file", headers=headers)
    assert got.status_code == 200 and got.content == PDF and got.headers["content-type"] == "application/pdf"
    assert got.headers["x-content-type-options"] == "nosniff" and "sandbox" in got.headers["content-security-policy"]
    assert "filename*=UTF-8''Karta%20Knauf.pdf" in got.headers["content-disposition"]
    rows = (await db_session.execute(select(KnowledgeDocumentFile))).scalars().all()
    assert len(rows) == 1 and bytes(rows[0].content) == PDF
    # replaced by a photo of a page; the old bytes are gone
    replaced = await async_client.put(f"{URL}/{doc['id']}", headers=headers, data=form(), files=files(PNG, "strona.png"))
    assert replaced.status_code == 200 and replaced.json()["file_mime"] == "image/png" and replaced.json()["file_name"] == "strona.png"
    assert (await async_client.get(f"{URL}/{doc['id']}/file", headers=headers)).content == PNG
    db_session.expire_all()
    assert len((await db_session.execute(select(KnowledgeDocumentFile))).scalars().all()) == 1
    # a change without a file keeps the file; a document that would be empty is refused; with a text the file may go
    kept = await async_client.put(f"{URL}/{doc['id']}", headers=headers, data=form(title="Inny"))
    assert kept.status_code == 200 and kept.json()["file_name"] == "strona.png"
    empty = await async_client.put(f"{URL}/{doc['id']}", headers=headers, data=form(remove_file="true"))
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "CONTENT_REQUIRED"
    removed = await async_client.put(f"{URL}/{doc['id']}", headers=headers, data=form(remove_file="true", body="Sam tekst"))
    assert removed.status_code == 200 and removed.json()["file_name"] is None and removed.json()["has_text"] is True
    assert (await async_client.get(f"{URL}/{doc['id']}/file", headers=headers)).status_code == 404
    db_session.expire_all()
    assert (await db_session.execute(select(KnowledgeDocumentFile))).scalars().all() == []


async def test_a_link_alone_is_enough_and_a_document_with_nothing_in_it_is_not(async_client, db_session):
    headers, _ = await _login(async_client, db_session)
    ok = await add(async_client, headers, form(source_url="https://www.knauf.pl/karta.pdf"))
    assert ok.status_code == 201 and ok.json()["source_url"] == "https://www.knauf.pl/karta.pdf"
    nothing = await add(async_client, headers, form())
    assert nothing.status_code == 422 and nothing.json()["detail"]["code"] == "CONTENT_REQUIRED"


@pytest.mark.parametrize(
    ("data", "upload", "status_code", "code"),
    [
        ({"kind": "NORM", "body": "x"}, None, 422, "TITLE_REQUIRED"),
        (form(body="x", kind="NOPE"), None, 422, "KIND_UNKNOWN"),
        (form(source_url="ftp://x"), None, 422, "URL_INVALID"),
        (form(body="x", doc_date="yesterday"), None, 422, "DATE_INVALID"),
        (form(body="x", tags=",".join(f"t{i}" for i in range(11))), None, 422, "TOO_MANY_TAGS"),
        (form(body="x", surprise="1"), None, 422, "FORM_INVALID"),
        (form(body="x", remove_file="maybe"), None, 422, "FORM_INVALID"),
        (form(), files(b"MZ\x90\x00 not a document"), 422, "FILE_TYPE_UNSUPPORTED"),
        (form(), files(b"%PDF-" + b"0" * 10_000_000), 413, "FILE_TOO_LARGE"),
    ],
)
async def test_a_wrong_form_says_what_is_wrong_and_stores_nothing(async_client, db_session, data, upload, status_code, code):
    headers, _ = await _login(async_client, db_session)
    resp = await add(async_client, headers, data, upload)
    assert resp.status_code == status_code and resp.json()["detail"]["code"] == code, resp.text[:200]
    assert (await db_session.execute(select(KnowledgeDocument))).scalars().all() == []


async def test_a_file_that_is_not_there_is_not_a_file(async_client, db_session):
    headers, _ = await _login(async_client, db_session)
    # the empty part a browser sends when no file was chosen
    resp = await add(async_client, headers, form(body="Tekst"), {"file": ("", b"", "application/octet-stream")})
    assert resp.status_code == 201 and resp.json()["file_name"] is None


async def test_the_list_filters_by_kind_and_searches_with_the_best_match_first(async_client, db_session):
    headers, _ = await _login(async_client, db_session)
    await add(async_client, headers, form(title="Rękojmia — art. 638", kind="STATUTE", body="Termin rękojmi to dwa lata", tags="kodeks"))
    await add(async_client, headers, form(title="Grunt Knauf Tiefengrund", kind="MANUFACTURER", body="Karta techniczna", tags="grunt"))
    await add(async_client, headers, form(title="Wzór pisma", kind="TEMPLATE", body="Wezwanie do usunięcia wady rękojmi"))
    titles = lambda r: [d["title"] for d in r.json()["items"]]  # noqa: E731
    assert titles(await async_client.get(URL, headers=headers, params={"q": "rekoj"})) == ["Rękojmia — art. 638", "Wzór pisma"]  # the title before the text
    assert titles(await async_client.get(URL, headers=headers, params={"q": "grunt karta"})) == ["Grunt Knauf Tiefengrund"]
    assert titles(await async_client.get(URL, headers=headers, params={"q": "nic takiego"})) == []
    assert titles(await async_client.get(URL, headers=headers, params={"kind": "TEMPLATE"})) == ["Wzór pisma"]
    assert (await async_client.get(URL, headers=headers, params={"kind": "NOPE"})).status_code == 422
    assert len((await async_client.get(URL, headers=headers)).json()["items"]) == 3


async def test_another_owner_sees_nothing_and_changes_nothing(async_client, db_session):
    headers, _ = await _login(async_client, db_session)
    other, _ = await _login(async_client, db_session, OTHER_USER)
    doc = (await add(async_client, headers, form(body="Prywatne"), files())).json()
    assert (await async_client.get(URL, headers=other)).json()["items"] == []
    for method, url, kw in (
        ("GET", f"{URL}/{doc['id']}", {}), ("GET", f"{URL}/{doc['id']}/file", {}), ("DELETE", f"{URL}/{doc['id']}", {}),
        ("PUT", f"{URL}/{doc['id']}", {"data": form(body="x")}), ("POST", f"{URL}/{doc['id']}/send", {}),
    ):
        resp = await async_client.request(method, url, headers=other, **kw)
        assert resp.status_code == 404, (method, url)
    assert (await async_client.get(f"{URL}/{doc['id']}", headers=headers)).json()["title"] == "Karta techniczna gruntu"


async def test_every_route_needs_a_login(async_client, db_session):
    for method, url in (("GET", URL), ("POST", URL), ("GET", f"{URL}/00000000-0000-0000-0000-000000000000"),
                        ("PUT", f"{URL}/00000000-0000-0000-0000-000000000000"), ("DELETE", f"{URL}/00000000-0000-0000-0000-000000000000"),
                        ("GET", f"{URL}/00000000-0000-0000-0000-000000000000/file"), ("POST", f"{URL}/00000000-0000-0000-0000-000000000000/send")):
        assert (await async_client.request(method, url)).status_code == 401, (method, url)


async def test_the_number_of_documents_and_the_space_of_the_files_are_bounded(async_client, db_session, monkeypatch):
    headers, _ = await _login(async_client, db_session)
    monkeypatch.setattr(rules, "MAX_DOCUMENTS", 2)
    assert (await add(async_client, headers, form(body="1"))).status_code == 201
    assert (await add(async_client, headers, form(body="2"))).status_code == 201
    third = await add(async_client, headers, form(body="3"))
    assert third.status_code == 409 and third.json()["detail"]["code"] == "TOO_MANY_DOCUMENTS"
    monkeypatch.setattr(rules, "MAX_DOCUMENTS", 100)
    monkeypatch.setattr(rules, "MAX_TOTAL_FILE_BYTES", len(PDF) * 2 - 1)
    first = await add(async_client, headers, form(), files())
    assert first.status_code == 201
    full = await add(async_client, headers, form(title="Druga"), files())
    assert full.status_code == 409 and full.json()["detail"]["code"] == "STORAGE_FULL"
    # replacing the only file of a document does not count it twice
    again = await async_client.put(f"{URL}/{first.json()['id']}", headers=headers, data=form(), files=files(PNG, "p.png"))
    assert again.status_code == 200


class FakeDelivery:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    async def send_document(self, chat_id, filename, pdf, caption):
        self.calls.append((chat_id, filename, pdf, caption))
        if self.error:
            raise self.error


async def test_the_file_goes_to_the_chat_of_the_owner_with_the_title_as_the_caption(async_client, db_session):
    headers, user = await _login(async_client, db_session)
    doc = (await add(async_client, headers, form(title="Norma PN-EN 13300"), files())).json()
    fake = FakeDelivery()
    app.dependency_overrides[get_document_delivery] = lambda: fake
    try:
        resp = await async_client.post(f"{URL}/{doc['id']}/send", headers=headers)
        assert resp.status_code == 200 and resp.json() == {"sent": True}
        assert fake.calls == [(user.telegram_user_id, "Karta Knauf.pdf", PDF, "Norma PN-EN 13300")]
        text_only = (await add(async_client, headers, form(body="Tylko tekst"))).json()
        none = await async_client.post(f"{URL}/{text_only['id']}/send", headers=headers)
        assert none.status_code == 404 and none.json()["detail"]["code"] == "KNOWLEDGE_DOCUMENT_HAS_NO_FILE"
        for error, status_code, code in (
            (DocumentChatUnavailableError("no chat"), 409, "TELEGRAM_CHAT_UNAVAILABLE"),
            (DocumentDeliveryDisabledError("off"), 503, None),
        ):
            app.dependency_overrides[get_document_delivery] = lambda error=error: FakeDelivery(error)
            refused = await async_client.post(f"{URL}/{doc['id']}/send", headers=headers)
            assert refused.status_code == status_code, refused.text
            assert code is None or refused.json()["detail"]["code"] == code
    finally:
        app.dependency_overrides.pop(get_document_delivery, None)
