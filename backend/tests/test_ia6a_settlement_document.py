"""Invoices and advances IA-6a -- the statement of settlements (Rozliczenie): what is printed, what never is, the issue and the preview."""
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select

from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.settlement_document import SettlementDocumentService, build_settlement_document, Sources
from app.domain.exceptions import DocumentDataError
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocument
from app.models.project_payment import ProjectFinance, ProjectPayment
from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15e_photo_report import seed
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer

OWNER_TG, STRANGER_TG = VALID_USER["id"], OTHER_USER["id"]
DAY = date(2026, 10, 18)


def text_of(pdf: bytes) -> str:
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).replace("\u00a0", " ")
    return " ".join(text.split())  # a narrow column may wrap a phrase onto two lines


async def add(db, w, kind, title, amount, *, on=DAY, **fields) -> ProjectPayment:
    row = ProjectPayment(owner_id=w.owner.id, project_id=w.project.id, kind=kind, title=title, amount_gross=Decimal(amount), occurred_on=on, **fields)
    db.add(row)
    await db.commit()
    return row


async def world(db, telegram_id=OWNER_TG):
    """An object with an invoice of 1 000 zł (400 paid), an advance, an expense and a finished agreed amount of 5 000 zł."""
    w = await seed(db, telegram_id=telegram_id)
    invoice = await add(db, w, "INVOICE", "Prace malarskie etap 1", "1000.00", on=DAY - timedelta(days=10), number="FV 1/2026", due_on=DAY + timedelta(days=4))
    await add(db, w, "ADVANCE", "Zaliczka na start", "300.00", on=DAY - timedelta(days=20))
    await add(db, w, "PAYMENT", "Wpłata za etap 1", "400.00", on=DAY - timedelta(days=2), settles_id=invoice.id)
    await add(db, w, "EXPENSE", "Farba Tajna Marka", "777.77", counterparty="Sklep Poufny", document_kind="RECEIPT")
    db.add(ProjectFinance(project_id=w.project.id, owner_id=w.owner.id, agreed_amount=Decimal("5000.00")))
    await db.commit()
    return w, invoice


async def html_of(db, w, **kw) -> str:
    service = SettlementDocumentService(db)
    document = await service.build(w.owner.id, w.project.id, working=kw.pop("working", False), issued_on=kw.pop("issued_on", DAY), **kw)
    return service.html(document)


# ------------------------------------------------------------------ what is printed

async def test_the_statement_names_the_invoices_the_payments_and_the_sums(db_session):
    w, _ = await world(db_session)
    page = (await html_of(db_session, w)).replace("\u00a0", " ")
    for text in ("Rozliczenie", "Stan rozliczeń na dzień 18.10.2026", "FV 1/2026", "Prace malarskie etap 1", "Częściowo opłacona", "1 000,00 zł",
                 "Zaliczka", "Wpłata za etap 1", "Wpłacono", "700,00 zł", "Umówiona kwota za całość prac", "5 000,00 zł", "Do zapłaty według faktur", "600,00 zł",
                 "Pozostało do zapłaty z umówionej kwoty", "4 300,00 zł", "Nie jest fakturą"):
        assert text in page, text
    assert "Anna Nowak" in page and "Mokotów" in page  # the client and the object


async def test_a_payment_names_the_invoice_it_settles_and_an_advance_names_none(db_session):
    w, _ = await world(db_session)
    document = await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    assert [(m.kind, m.title, m.amount.replace("\u00a0", " "), m.invoice) for m in document.money] == [
        ("Zaliczka", "Zaliczka na start", "300,00 zł", None),
        ("Wpłata", "Wpłata za etap 1", "400,00 zł", "FV 1/2026"),
    ]
    assert [(i.number, i.state) for i in document.invoices] == [("FV 1/2026", "Częściowo opłacona")]


async def test_the_expenses_of_the_owner_never_reach_the_client(db_session):
    w, _ = await world(db_session)
    page = await html_of(db_session, w)
    for secret in ("Farba Tajna Marka", "Sklep Poufny", "777,77", "777.77", "Paragon"):
        assert secret not in page, secret
    # not even when it is the only record of the object
    await db_session.execute(ProjectPayment.__table__.delete().where(ProjectPayment.kind != "EXPENSE"))
    await db_session.commit()
    with pytest.raises(DocumentDataError) as empty:
        await html_of(db_session, w)
    assert empty.value.reason == "SETTLEMENT_EMPTY"


async def test_an_archived_record_is_not_printed_and_counts_for_nothing(db_session):
    w, invoice = await world(db_session)
    extra = await add(db_session, w, "INVOICE", "Pomyłkowa faktura", "9999.00", number="FV 9/2026")
    extra.is_archived = True
    await db_session.commit()
    document = await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    assert [i.number for i in document.invoices] == ["FV 1/2026"]
    assert "Pomyłkowa" not in (await html_of(db_session, w))
    assert document.totals.invoiced.replace("\u00a0", " ") == "1 000,00 zł"


@pytest.mark.parametrize(("today_offset", "state"), [(0, "Częściowo opłacona"), (5, "Po terminie")])
async def test_an_invoice_is_overdue_after_its_term_as_of_the_day_of_the_statement(db_session, today_offset, state):
    w, _ = await world(db_session)
    document = await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY + timedelta(days=today_offset))
    assert document.invoices[0].state == state  # a part paid is "partial" until the term passes, then "overdue" (the order of the screen)


async def test_a_paid_invoice_says_so_and_an_overpayment_is_named_as_one(db_session):
    w, invoice = await world(db_session)
    await add(db_session, w, "PAYMENT", "Reszta", "600.00", settles_id=invoice.id)
    await add(db_session, w, "ADVANCE", "Nadpłata", "5000.00")
    document = await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    assert document.invoices[0].state == "Opłacona" and document.invoices[0].remaining.replace("\u00a0", " ") == "0,00 zł"
    assert document.totals.left_label == "Nadpłata względem umówionej kwoty" and document.totals.left.replace("\u00a0", " ") == "1 300,00 zł"
    assert "-" not in document.totals.left


async def test_without_an_agreed_amount_the_lines_that_depend_on_it_are_left_out(db_session):
    w, _ = await world(db_session)
    await db_session.execute(ProjectFinance.__table__.delete())
    await db_session.commit()
    page = await html_of(db_session, w)
    assert "Umówiona kwota" not in page and "z umówionej kwoty" not in page and "Do zapłaty według faktur" in page


async def test_invoices_are_listed_by_their_day_and_one_without_a_number_says_so(db_session):
    w, _ = await world(db_session)
    await add(db_session, w, "INVOICE", "Wcześniejsza bez numeru", "50.00", on=DAY - timedelta(days=40))
    await add(db_session, w, "INVOICE", "Późniejsza", "60.00", on=DAY - timedelta(days=1), number="FV 3/2026")
    document = await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    assert [(i.title, i.number) for i in document.invoices] == [
        ("Wcześniejsza bez numeru", "bez numeru"), ("Prace malarskie etap 1", "FV 1/2026"), ("Późniejsza", "FV 3/2026"),
    ]


async def test_the_statement_has_no_signature_lines_it_is_not_a_contract(db_session):
    w, _ = await world(db_session)
    page = await html_of(db_session, w)
    assert "Podpis wykonawcy" not in page and "Podpis zamawiającego" not in page


async def test_the_words_of_a_record_cannot_break_the_page(db_session):
    w, _ = await world(db_session)
    await add(db_session, w, "INVOICE", "<script>alert(1)</script> {{ 7*7 }}", "10.00", number="<b>FV</b>")
    page = await html_of(db_session, w)
    assert "<script>" not in page and "&lt;script&gt;" in page and "&lt;b&gt;FV&lt;/b&gt;" in page and "49" not in page.replace("2026", "")


# ------------------------------------------------------------------ the two forms of the document

async def test_the_issued_form_needs_something_to_state_and_a_profile_and_the_working_form_never_refuses(db_session):
    w = await seed(db_session, telegram_id=9611)
    with pytest.raises(DocumentDataError) as empty:
        await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    assert empty.value.reason == "SETTLEMENT_EMPTY"
    draft = await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=True, issued_on=DAY)
    page = SettlementDocumentService.html(draft)
    assert "WERSJA ROBOCZA" in page and "Brak wystawionych faktur." in page and "Brak wpłat." in page and draft.layout.meta.number is None
    await add(db_session, w, "INVOICE", "FV", "10.00")
    await db_session.execute(ExecutorProfile.__table__.delete().where(ExecutorProfile.owner_id == w.owner.id))
    await db_session.commit()
    with pytest.raises(DocumentDataError) as no_profile:
        await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert SettlementDocumentService.html(await SettlementDocumentService(db_session).build(w.owner.id, w.project.id, working=True, issued_on=DAY))


async def test_a_working_version_is_never_numbered_and_an_issued_one_has_no_watermark(db_session):
    w, _ = await world(db_session)
    sources = await SettlementDocumentService(db_session).sources(w.owner.id, w.project.id)
    with pytest.raises(DocumentDataError) as numbered:
        build_settlement_document(sources, None, working=True, issued_on=DAY, number="ROZL/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    issued = await html_of(db_session, w, number="ROZL/2026/10/18/1200", sequence=3)
    assert "WERSJA ROBOCZA" not in issued and "ROZL/2026/10/18/1200" in issued


async def test_the_statement_is_the_template_of_its_kind(db_session):
    template = get_template(DocumentKind.SETTLEMENT)
    assert (template.number_prefix, template.file, template.version) == ("ROZL", "settlement.html.j2", "1")


async def test_another_owner_has_no_access_to_the_object(db_session):
    from app.domain.exceptions import ProjectNotFoundError

    w, _ = await world(db_session)
    stranger = await seed(db_session, telegram_id=STRANGER_TG + 5)
    with pytest.raises(ProjectNotFoundError):
        await SettlementDocumentService(db_session).build(stranger.owner.id, w.project.id, working=False, issued_on=DAY)


# ------------------------------------------------------------------ the real routes and a real PDF

async def test_the_routes_need_a_token(async_client: AsyncClient, use_issuer):  # noqa: F811
    use_issuer(issuer())
    pid = uuid.uuid4()
    assert (await async_client.post(f"/api/projects/{pid}/documents", json={"kind": "SETTLEMENT"})).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/settlement/preview")).status_code == 401


async def test_it_takes_no_other_fields(async_client: AsyncClient, use_issuer):  # noqa: F811
    run = use_issuer(issuer())
    headers = await login(async_client)
    for body in ({"kind": "SETTLEMENT", "estimate_id": str(uuid.uuid4())}, {"kind": "SETTLEMENT", "room_ids": [str(uuid.uuid4())]},
                 {"kind": "SETTLEMENT", "include_project_photos": True}, {"kind": "SETTLEMENT", "owner_id": str(uuid.uuid4())}):
        assert (await async_client.post(f"/api/projects/{uuid.uuid4()}/documents", json=body, headers=headers)).status_code == 422
    assert run.active == 0


async def test_issuing_gives_a_numbered_pdf_in_the_chat_and_a_row_in_the_journal(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w, _ = await world(db_session)
    project_id = str(w.project.id)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "SETTLEMENT"}, headers=headers)
    assert response.status_code == 202, response.text
    row = response.json()
    assert row["kind"] == "SETTLEMENT" and row["status"] == "PENDING" and row["number"].startswith("ROZL/") and row["source_id"] is None
    await run.drain()
    shown = await async_client.get(f"/api/projects/{project_id}/documents/{row['id']}", headers=headers)
    assert shown.json()["status"] == "SENT" and len(sender.sent) == 1
    sent = sender.sent[0]
    assert sent["filename"].startswith("ROZL-") and sent["caption"].startswith("Rozliczenie — Mokotów")
    text = text_of(sent["pdf"])
    assert row["number"] in text and "FV 1/2026" in text and "Częściowo opłacona" in text and "4 300,00 zł" in text and "?" not in text  # no glyph missing from the font
    for secret in ("Farba Tajna Marka", "Sklep Poufny", "777,77", "WERSJA ROBOCZA"):
        assert secret not in text, secret
    listed = await async_client.get(f"/api/projects/{project_id}/documents", headers=headers)
    assert [d["kind"] for d in listed.json()["items"]] == ["SETTLEMENT"]


async def test_nothing_to_state_is_a_422_that_takes_no_number(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    await add(db_session, w, "EXPENSE", "Tylko wydatek", "10.00", counterparty="Sklep", document_kind="RECEIPT")
    run = use_issuer(issuer())
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "SETTLEMENT"}, headers=headers)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "SETTLEMENT_EMPTY")
    assert run.active == 0
    assert (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_the_preview_is_a_watermarked_pdf_without_a_number_or_a_journal_row(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)  # nothing to state yet: the preview still works
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents/settlement/preview", headers=headers)
    assert response.status_code == 200 and response.json()["sent"] is True
    (sent,) = sender.sent
    assert sent["filename"] == "Rozliczenie-wersja-robocza.pdf" and sent["caption"].startswith("WERSJA ROBOCZA — Rozliczenie")
    assert "WERSJA ROBOCZA" in text_of(sent["pdf"]) and "ROZL/" not in text_of(sent["pdf"])
    assert (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_another_owner_gets_a_404_for_both_routes(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w, _ = await world(db_session)
    use_issuer(issuer())
    stranger = await login(async_client, OTHER_USER)
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "SETTLEMENT"}, headers=stranger)).status_code == 404
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents/settlement/preview", headers=stranger)).status_code == 404
