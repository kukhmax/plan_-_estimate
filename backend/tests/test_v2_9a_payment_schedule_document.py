"""V2-9a -- the payment schedule as a document for the client (Harmonogram płatności): the numbers are those of the screen, what is printed, what never is, the two forms."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.domain.documents import formatting
from app.domain.documents.payment_schedule_document import (
    PaymentScheduleDocumentService,
)
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.domain.services.payment_schedule_service import PaymentScheduleService
from app.domain.services.payment_service import PaymentService
from app.domain.services.work_hours_service import WorkHoursService
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocument
from httpx import AsyncClient
from sqlalchemy import select

from tests.test_clients import OTHER_USER
from tests.test_stage15e_photo_report import seed
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer
from tests.test_v2_8c_measurements import OWNER_TG, page_text, pdf_text

DAY = date(2026, 10, 28)
D = Decimal


def money(value: str) -> str:
    return formatting.format_money(D(value)).replace(" ", " ")


async def world(db, telegram_id=OWNER_TG):
    """An object agreed at 40 000 with three stages (30 % due 5.11, a fixed 15 000, 20 %), an advance of 12 000 on the first, and what is the owner's own
    business: two expenses, hours with a note."""
    w = await seed(db, telegram_id=telegram_id)
    payments, schedule = PaymentService(db), PaymentScheduleService(db)
    await payments.set_agreed_amount(w.owner.id, w.project.id, D("40000"))
    w.first = await schedule.create(w.owner.id, w.project.id, {"title": "Zaliczka na start", "percent": D("30"), "due_on": date(2026, 11, 5)})
    w.second = await schedule.create(w.owner.id, w.project.id, {"title": "Po gładziach", "amount": D("15000")})
    w.third = await schedule.create(w.owner.id, w.project.id, {"title": "Odbiór końcowy", "percent": D("20")})
    w.advance = await payments.create_payment(
        w.owner.id, w.project.id, {"kind": "ADVANCE", "title": "Zaliczka", "amount_gross": D("12000"), "occurred_on": date(2026, 10, 20), "stage_id": w.first.id}
    )
    for title, amount in (("Farba tajna", "1234.56"), ("Gładź tajna", "2765.44")):
        await payments.create_payment(w.owner.id, w.project.id, {"kind": "EXPENSE", "title": title, "amount_gross": D(amount), "occurred_on": date(2026, 10, 21)})
    await WorkHoursService(db).create(w.owner.id, w.project.id, {"worked_on": date(2026, 10, 22), "hours": D("8"), "note": "notatka godzin tajna"})
    return w


def service(db) -> PaymentScheduleDocumentService:
    return PaymentScheduleDocumentService(db)


async def build(db, w, **kw):
    return await service(db).build(w.owner.id, w.project.id, working=kw.pop("working", False), issued_on=kw.pop("issued_on", DAY), **kw)


async def html_of(db, w, **kw) -> str:
    return page_text(PaymentScheduleDocumentService.html(await build(db, w, **kw)))


# --- the numbers are those of the screen -------------------------------------------------------------------------------------------------------


async def test_the_stages_are_the_ones_of_the_screen_in_its_order_with_its_amounts_and_states(db_session):
    w = await world(db_session)
    screen = await PaymentScheduleService(db_session).schedule(w.owner.id, w.project.id, today=DAY)
    document = await build(db_session, w)
    assert [r.title for r in document.stages] == [v.stage.title for v in screen.items] == ["Zaliczka na start", "Po gładziach", "Odbiór końcowy"]  # the day first, none last
    for row, view in zip(document.stages, screen.items, strict=True):
        assert row.amount == formatting.format_money(view.standing.amount)
        assert row.paid == formatting.format_money(view.standing.received) and row.left == formatting.format_money(view.standing.remaining)
    first, second, third = document.stages
    assert (first.number, first.share, first.amount, first.state, first.due) == (1, "30%", money("12000"), "Zapłacony", date(2026, 11, 5))
    assert (second.share, second.amount, second.state, second.due) == ("—", money("15000"), "Do zapłaty", None)
    assert (third.share, third.amount, third.left) == ("20%", money("8000"), money("8000"))


async def test_the_totals_and_the_gap_against_the_agreed_amount(db_session):
    w = await world(db_session)
    totals = (await build(db_session, w)).totals
    assert (totals.agreed, totals.total, totals.received, totals.left) == (money("40000"), money("35000"), money("12000"), money("23000"))
    assert totals.note == f"Harmonogram nie obejmuje całej umówionej kwoty: poza harmonogramem pozostaje {money('5000')}."
    await PaymentScheduleService(db_session).create(w.owner.id, w.project.id, {"title": "Dodatek", "amount": D("7000")})
    assert (await build(db_session, w)).totals.note == f"Suma etapów przekracza umówioną kwotę o {money('2000')}."
    await PaymentScheduleService(db_session).create(w.owner.id, w.project.id, {"title": "Grosz", "amount": D("0.01")})  # a grosz more is still above the agreed amount
    assert (await build(db_session, w)).totals.note == f"Suma etapów przekracza umówioną kwotę o {money('2000.01')}."


async def test_an_exactly_covered_agreed_amount_has_no_note(db_session):
    w = await world(db_session)
    await PaymentScheduleService(db_session).create(w.owner.id, w.project.id, {"title": "Reszta", "amount": D("5000")})
    assert (await build(db_session, w)).totals.note is None


async def test_the_state_is_as_of_the_day_of_the_document(db_session):
    w = await world(db_session)
    await PaymentScheduleService(db_session).change(w.owner.id, w.project.id, w.third.id, {"due_on": date(2026, 11, 1)})
    early = await build(db_session, w, issued_on=date(2026, 10, 28))
    late = await build(db_session, w, issued_on=date(2026, 11, 2))
    assert early.stages[0].title == "Odbiór końcowy" and early.stages[0].state == "Do zapłaty"
    assert late.stages[0].state == "Po terminie"
    assert "Stan na dzień 02.11.2026" in page_text(PaymentScheduleDocumentService.html(late))


async def test_an_archived_payment_does_not_count_and_the_payment_of_another_stage_does_not_move_this_one(db_session):
    w = await world(db_session)
    await PaymentService(db_session).set_archived(w.owner.id, w.project.id, w.advance.id, True)
    document = await build(db_session, w)
    assert document.stages[0].state == "Do zapłaty" and document.stages[0].paid == money("0") and document.totals.received == money("0")


# --- what never gets in -----------------------------------------------------------------------------------------------------------------------


async def test_the_expenses_the_hours_and_the_margin_of_the_owner_never_reach_the_page(db_session):
    w = await world(db_session)
    for working in (True, False):
        text = await html_of(db_session, w, working=working)
        for secret in ("tajna", "Farba", "Gładź", "notatka", money("1234.56"), money("2765.44"), money("4000"), "Marża", "godzin", "marż", "Wynik"):
            assert secret not in text, secret


async def test_the_page_lays_out_the_object_the_stages_the_totals_and_says_it_is_not_an_invoice(db_session):
    w = await world(db_session)
    text = await html_of(db_session, w)
    for expected in ("Harmonogram płatności", "Mokotów", "Anna Nowak", "Etapy płatności", "Zaliczka na start", "30%", "05.11.2026", "Zapłacony", "Podsumowanie",
                     "Umówiona kwota za całość prac", "Do zapłaty według harmonogramu", "nie jest fakturą ani dokumentem księgowym", "bez terminu"):
        assert expected in text, expected
    assert "WERSJA ROBOCZA" not in text


async def test_a_title_that_is_long_or_has_markup_cannot_break_the_page(db_session):
    w = await world(db_session)
    await PaymentScheduleService(db_session).change(w.owner.id, w.project.id, w.second.id, {"title": "<b>Bardzo długi tytuł etapu płatności</b> " * 6})
    html = PaymentScheduleDocumentService.html(await build(db_session, w))
    assert "<b>Bardzo" not in html and "&lt;b&gt;" in html


# --- the two forms -------------------------------------------------------------------------------------------------------------------------------


async def test_the_issued_form_needs_a_stage_a_known_amount_and_a_profile_and_the_working_form_never_refuses(db_session):
    w = await seed(db_session, telegram_id=OWNER_TG)
    with pytest.raises(DocumentDataError) as empty:
        await build(db_session, w)
    assert empty.value.reason == "PAYMENT_SCHEDULE_EMPTY"
    working = await build(db_session, w, working=True)
    assert working.stages == () and "Brak etapów." in page_text(PaymentScheduleDocumentService.html(working))
    await PaymentScheduleService(db_session).create(w.owner.id, w.project.id, {"title": "Udział", "percent": D("30")})  # no agreed amount yet
    with pytest.raises(DocumentDataError) as unpriced:
        await build(db_session, w)
    assert unpriced.value.reason == "PAYMENT_SCHEDULE_UNPRICED" and unpriced.value.details == {"count": 1}
    waiting = await build(db_session, w, working=True)
    assert waiting.stages[0].amount == "do ustalenia" and waiting.stages[0].left == "—" and waiting.totals.left is None
    await PaymentService(db_session).set_agreed_amount(w.owner.id, w.project.id, D("1000"))
    assert (await build(db_session, w)).stages[0].amount == money("300")
    profile = (await db_session.execute(select(ExecutorProfile))).scalar_one()
    await db_session.delete(profile)
    await db_session.commit()
    with pytest.raises(DocumentDataError) as no_profile:
        await build(db_session, w)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert (await build(db_session, w, working=True)).layout.executor is None


async def test_a_working_version_is_never_numbered_and_an_issued_one_has_no_watermark(db_session):
    w = await world(db_session)
    with pytest.raises(DocumentDataError) as caught:
        await build(db_session, w, working=True, number="HPL/1")
    assert caught.value.reason == "DRAFT_NUMBERED"
    assert "WERSJA ROBOCZA" in PaymentScheduleDocumentService.html(await build(db_session, w, working=True))
    assert "WERSJA ROBOCZA" not in PaymentScheduleDocumentService.html(await build(db_session, w, number="HPL/2026/1", sequence=1))


async def test_the_payment_schedule_is_the_template_of_its_kind():
    template = get_template(DocumentKind.PAYMENT_SCHEDULE)
    assert (template.number_prefix, template.file, template.version) == ("HPL", "payment_schedule.html.j2", "1")


async def test_another_owner_cannot_print_it_and_another_object_does_not_leak_in(db_session):
    w = await world(db_session)
    stranger = await seed(db_session, telegram_id=OWNER_TG + 91)
    with pytest.raises(ProjectNotFoundError):
        await service(db_session).build(stranger.owner.id, w.project.id, working=True, issued_on=DAY)
    other = await build(db_session, stranger, working=True)
    assert other.stages == ()


# --- the real routes and a real PDF ------------------------------------------------------------------------------------------------------------------------


async def test_the_routes_need_a_token(async_client: AsyncClient, use_issuer):  # noqa: F811
    use_issuer(issuer())
    pid = uuid.uuid4()
    assert (await async_client.post(f"/api/projects/{pid}/documents", json={"kind": "PAYMENT_SCHEDULE"})).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/payment-schedule/preview")).status_code == 401


async def test_it_takes_no_other_fields(async_client: AsyncClient, use_issuer):  # noqa: F811
    run = use_issuer(issuer())
    headers = await login(async_client)
    for body in ({"kind": "PAYMENT_SCHEDULE", "estimate_id": str(uuid.uuid4())}, {"kind": "PAYMENT_SCHEDULE", "room_ids": [str(uuid.uuid4())]},
                 {"kind": "PAYMENT_SCHEDULE", "with_photos": True}, {"kind": "PAYMENT_SCHEDULE", "include_project_photos": True}):
        assert (await async_client.post(f"/api/projects/{uuid.uuid4()}/documents", json=body, headers=headers)).status_code == 422
    assert run.active == 0


async def test_issuing_gives_a_numbered_pdf_with_the_stages_in_the_chat_and_a_row_in_the_journal(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await world(db_session)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "PAYMENT_SCHEDULE"}, headers=headers)
    assert response.status_code == 202, response.text
    row = response.json()
    assert row["kind"] == "PAYMENT_SCHEDULE" and row["status"] == "PENDING" and row["number"].startswith("HPL/") and row["title"] == "Harmonogram płatności"
    await run.drain()
    shown = await async_client.get(f"/api/projects/{w.project.id}/documents/{row['id']}", headers=headers)
    assert shown.json()["status"] == "SENT" and len(sender.sent) == 1
    sent = sender.sent[0]
    assert sent["filename"].startswith("HPL-") and sent["caption"].startswith("Harmonogram płatności — Mokotów")
    text = pdf_text(sent["pdf"])
    assert row["number"] in text and "Etapy płatności" in text and "Zaliczka na start" in text and "30%" in text and "WERSJA ROBOCZA" not in text and "?" not in text
    for secret in ("tajna", "Marża", "godzin"):
        assert secret not in text
    listed = await async_client.get(f"/api/projects/{w.project.id}/documents", headers=headers)
    assert [d["kind"] for d in listed.json()["items"]] == ["PAYMENT_SCHEDULE"]


async def test_an_object_without_a_stage_is_a_422_that_takes_no_number(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    run = use_issuer(issuer())
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "PAYMENT_SCHEDULE"}, headers=headers)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "PAYMENT_SCHEDULE_EMPTY")
    assert run.active == 0 and (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_a_stage_without_a_known_amount_is_a_422_with_the_count_and_takes_no_number(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    await PaymentScheduleService(db_session).create(w.owner.id, w.project.id, {"title": "Udział", "percent": D("30")})
    run = use_issuer(issuer())
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "PAYMENT_SCHEDULE"}, headers=headers)
    detail = response.json()["detail"]
    assert (response.status_code, detail["code"], detail["details"]) == (422, "PAYMENT_SCHEDULE_UNPRICED", {"count": 1})
    assert run.active == 0 and (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_the_preview_is_a_watermarked_pdf_without_a_number_or_a_journal_row(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await world(db_session)
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents/payment-schedule/preview", headers=headers)
    assert response.status_code == 200 and response.json()["sent"] is True
    (sent,) = sender.sent
    assert sent["filename"] == "Harmonogram-platnosci-wersja-robocza.pdf" and sent["caption"].startswith("WERSJA ROBOCZA — Harmonogram płatności")
    assert "WERSJA ROBOCZA" in pdf_text(sent["pdf"]) and "HPL/" not in pdf_text(sent["pdf"])
    assert (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_another_owner_gets_a_404_for_both_routes(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await world(db_session)
    use_issuer(issuer())
    headers = await login(async_client, OTHER_USER)
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "PAYMENT_SCHEDULE"}, headers=headers)).status_code == 404
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents/payment-schedule/preview", headers=headers)).status_code == 404
