"""Stage 15F.2 — issuing: the checks made in the request, the background run that renders and sends, every way it can end,
the queue limit, the preview of a draft."""

import asyncio
import hashlib
import io
import logging
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.domain.documents.issuer import DocumentIssuer, pdf_filename
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.exceptions import (
    DocumentChatUnavailableError,
    DocumentDataError,
    DocumentDeliveryDisabledError,
    DocumentDeliveryRejectedError,
    DocumentDeliveryUnavailableError,
    DocumentQueueFullError,
    DocumentRenderBusyError,
    DocumentRenderTimeoutError,
    DocumentTooLargeError,
    EstimateNotFoundError,
)
from app.models.estimate import Estimate, EstimateStatus
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocument
from app.models.photo_attachment import PhotoAttachment
from app.models.user import User
from tests.conftest import TestingSessionLocal
from tests.test_stage15d_estimate_document import seed as seed_estimate
from tests.test_stage15e_photo_report import seed as seed_photos

NOW = datetime(2026, 10, 8, 17, 53, 10, tzinfo=UTC)  # 19:53 in Poland


class Delivery:
    def __init__(self, error: Exception | None = None):
        self.sent: list[dict] = []
        self.error = error

    async def send_document(self, chat_id, filename, pdf, caption):
        if self.error:
            raise self.error
        self.sent.append({"chat_id": chat_id, "filename": filename, "pdf": pdf, "caption": caption})


class StubRenderer:
    def __init__(self, error: Exception | None = None, delay: float = 0.0):
        self.error, self.delay, self.calls = error, delay, 0

    async def render(self, html, assets=None) -> RenderedPdf:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        pdf = b"%PDF-1.4 stub"
        return RenderedPdf(pdf, 1, hashlib.sha256(pdf).hexdigest(), len(pdf), 0.0, 0)


class Gate:
    """The background run starts only when the test lets it: the test session and the run share the one in-memory SQLite
    connection, so they must never work at the same moment."""

    def __init__(self) -> None:
        self.event = asyncio.Event()

    def __call__(self):
        gate = self.event

        class Session:
            async def __aenter__(self):
                await gate.wait()
                self.inner = TestingSessionLocal()
                return await self.inner.__aenter__()

            async def __aexit__(self, *exc):
                return await self.inner.__aexit__(*exc)

        return Session()


class GatedIssuer(DocumentIssuer):
    def release(self) -> None:
        self.session_factory.event.set()

    async def drain(self) -> None:
        self.release()
        await super().drain()


def issuer(storage=None, *, renderer=None, delivery=None, **kw) -> GatedIssuer:
    return GatedIssuer(
        session_factory=Gate(),
        renderer=renderer or DocumentRenderer(),
        delivery=delivery or Delivery(),
        storage=lambda: storage,
        storage_name="r2-primary",
        max_photos=kw.pop("max_photos", 60),
        clock=lambda: NOW,
        **kw,
    )


async def user_of(db, owner_id) -> User:
    return (await db.execute(select(User).where(User.id == owner_id))).scalar_one()


async def journal(db) -> list[IssuedDocument]:
    db.expire_all()
    return list((await db.execute(select(IssuedDocument).order_by(IssuedDocument.project_seq))).scalars())


def text_of(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


# --- the estimate ---------------------------------------------------------------------------------------------------------------


async def test_an_estimate_is_numbered_rendered_sent_and_recorded(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9801)
    owner_id, project_id, estimate_id, telegram = owner.id, project.id, estimate.id, owner.telegram_user_id
    sender = Delivery()
    run = issuer(delivery=sender)
    reservation = await run.start_estimate(db_session, await user_of(db_session, owner_id), project_id, estimate_id)
    started = reservation.document
    assert (started.status, started.number, started.project_seq) == ("PENDING", "KOSZ/2026/10/08/1953", 1)
    await run.drain()
    (done,) = await journal(db_session)
    assert (done.status, done.error_code, done.kind, done.source_id) == ("SENT", None, "ESTIMATE", estimate_id)
    assert done.pages == 1 and done.byte_size and done.sha256 == hashlib.sha256(sender.sent[0]["pdf"]).hexdigest()
    (message,) = sender.sent
    assert message["chat_id"] == telegram and message["filename"] == "KOSZ-2026-10-08-1953.pdf"
    assert message["caption"] == "Kosztorys — wersja 1 — Mokotów\nKOSZ/2026/10/08/1953"
    text = text_of(message["pdf"])
    assert "KOSZ/2026/10/08/1953" in text and "Nr kolejny dokumentu dla obiektu" in text and "WERSJA ROBOCZA" not in text
    assert "147,00" in text.replace(" ", " ")


async def test_the_running_number_of_the_second_document_is_two(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9802)
    owner_id, project_id, estimate_id = owner.id, project.id, estimate.id
    run = issuer()
    user = await user_of(db_session, owner_id)
    await run.start_estimate(db_session, user, project_id, estimate_id)
    await run.drain()
    second = await run.start_estimate(db_session, user, project_id, estimate_id)
    await run.drain()
    assert (second.document.project_seq, second.document.number) == (2, "KOSZ/2026/10/08/1953-2")
    assert [d.status for d in await journal(db_session)] == ["SENT", "SENT"]


async def test_a_draft_a_foreign_estimate_and_a_missing_profile_are_refused_in_the_request_without_taking_a_number(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9803)
    stranger, _, _ = await seed_estimate(db_session, telegram_id=9804)
    owner_id, project_id, estimate_id, stranger_id = owner.id, project.id, estimate.id, stranger.id
    run = issuer()
    user, foreign = await user_of(db_session, owner_id), await user_of(db_session, stranger_id)
    with pytest.raises(EstimateNotFoundError):
        await run.start_estimate(db_session, foreign, project_id, estimate_id)
    est = (await db_session.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one()
    est.status = EstimateStatus.DRAFT
    await db_session.commit()
    with pytest.raises(DocumentDataError) as draft:
        await run.start_estimate(db_session, user, project_id, estimate_id)
    assert draft.value.reason == "ESTIMATE_NOT_FINAL"
    est = (await db_session.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one()
    est.status = EstimateStatus.FINAL
    await db_session.execute(ExecutorProfile.__table__.delete().where(ExecutorProfile.owner_id == owner_id))
    await db_session.commit()
    with pytest.raises(DocumentDataError) as no_profile:
        await run.start_estimate(db_session, user, project_id, estimate_id)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert await journal(db_session) == [] and run.active == 0


async def test_a_second_tap_before_the_first_ends_starts_nothing_new(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9805)
    owner_id, project_id, estimate_id = owner.id, project.id, estimate.id
    sender = Delivery()
    run = issuer(delivery=sender)
    user = await user_of(db_session, owner_id)
    first = await run.start_estimate(db_session, user, project_id, estimate_id)
    again = await run.start_estimate(db_session, user, project_id, estimate_id)
    assert again.reused and again.document.id == first.document.id and run.active == 1
    await run.drain()
    assert len(sender.sent) == 1 and len(await journal(db_session)) == 1


@pytest.mark.parametrize(
    ("renderer_error", "delivery_error", "code"),
    [
        (None, DocumentChatUnavailableError("x"), "TELEGRAM_CHAT_UNAVAILABLE"),
        (None, DocumentDeliveryUnavailableError("x"), "TELEGRAM_UNAVAILABLE"),
        (None, DocumentDeliveryRejectedError("x"), "TELEGRAM_REJECTED"),
        (None, DocumentDeliveryDisabledError("x"), "DELIVERY_DISABLED"),
        (DocumentRenderTimeoutError("x"), None, "DOCUMENT_RENDER_TIMEOUT"),
        (DocumentRenderBusyError("x"), None, "DOCUMENT_RENDER_BUSY"),
        (DocumentTooLargeError("x"), None, "DOCUMENT_TOO_LARGE"),
        (RuntimeError("boom"), None, "INTERNAL_ERROR"),
    ],
)
async def test_every_way_to_fail_ends_the_row_with_its_code_and_keeps_the_number(db_session, caplog, renderer_error, delivery_error, code):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9806)
    owner_id, project_id, estimate_id = owner.id, project.id, estimate.id
    run = issuer(renderer=StubRenderer(renderer_error), delivery=Delivery(delivery_error))
    user = await user_of(db_session, owner_id)
    caplog.set_level(logging.ERROR)
    await run.start_estimate(db_session, user, project_id, estimate_id)
    await run.drain()
    (row,) = await journal(db_session)
    assert (row.status, row.error_code, row.number, row.sent_at) == ("FAILED", code, "KOSZ/2026/10/08/1953", None)
    assert ("issuing document" in caplog.text) == (code == "INTERNAL_ERROR")  # an unexpected error is logged, a known one is not noise
    retry = await run.start_estimate(db_session, await user_of(db_session, owner_id), project_id, estimate_id)
    assert not retry.reused and retry.document.project_seq == 2  # a failed attempt does not block the next one
    await run.drain()


async def test_data_that_changed_between_the_request_and_the_run_fails_with_its_reason(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9807)
    owner_id, project_id, estimate_id = owner.id, project.id, estimate.id
    sender = Delivery()
    run = issuer(delivery=sender)
    await run.start_estimate(db_session, await user_of(db_session, owner_id), project_id, estimate_id)
    est = (await db_session.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one()
    est.status = EstimateStatus.ARCHIVED
    await db_session.commit()
    await run.drain()
    (row,) = await journal(db_session)
    assert (row.status, row.error_code) == ("FAILED", "ESTIMATE_ARCHIVED") and sender.sent == []


async def test_a_run_that_is_cancelled_ends_its_row_as_interrupted(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9808)
    owner_id, project_id, estimate_id = owner.id, project.id, estimate.id
    run = issuer(renderer=StubRenderer(delay=30))
    await run.start_estimate(db_session, await user_of(db_session, owner_id), project_id, estimate_id)
    run.release()
    await asyncio.sleep(0.3)
    for task in list(run._tasks):
        task.cancel()
    await run.drain()
    (row,) = await journal(db_session)
    assert (row.status, row.error_code) == ("FAILED", "INTERRUPTED") and run.active == 0


async def test_too_many_documents_at_once_are_refused_before_a_number_is_taken(db_session):
    owner, project, first = await seed_estimate(db_session, telegram_id=9809)
    owner_id, project_id, first_id = owner.id, project.id, first.id
    run = issuer(renderer=StubRenderer(delay=0.3), max_active=1)
    user = await user_of(db_session, owner_id)
    await run.start_estimate(db_session, user, project_id, first_id)
    with pytest.raises(DocumentQueueFullError):
        await run.start_estimate(db_session, user, project_id, first_id)  # the same one is also refused while the queue is full
    await run.drain()
    assert len(await journal(db_session)) == 1
    await run.start_estimate(db_session, await user_of(db_session, owner_id), project_id, first_id)  # the queue is free again
    await run.drain()
    assert len(await journal(db_session)) == 2


# --- the preview of a draft ------------------------------------------------------------------------------------------------------


async def test_a_draft_is_previewed_to_the_chat_with_the_watermark_and_without_a_journal_row(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9810)
    owner_id, project_id, estimate_id, telegram = owner.id, project.id, estimate.id, owner.telegram_user_id
    est = (await db_session.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one()
    est.status = EstimateStatus.DRAFT
    await db_session.commit()
    sender = Delivery()
    result = await issuer(delivery=sender).preview_estimate(db_session, await user_of(db_session, owner_id), project_id, estimate_id)
    (message,) = sender.sent
    assert message["chat_id"] == telegram and message["filename"] == "Kosztorys-wersja-robocza-1.pdf"
    assert message["caption"].startswith("WERSJA ROBOCZA — Kosztorys — ")
    text = text_of(message["pdf"])
    assert "WERSJA ROBOCZA" in text and "KOSZ/" not in text
    assert (result.pages, result.byte_size) == (1, len(message["pdf"])) and await journal(db_session) == []


async def test_only_a_draft_is_previewed_and_a_delivery_failure_is_not_hidden(db_session):
    owner, project, estimate = await seed_estimate(db_session, telegram_id=9811)
    owner_id, project_id, estimate_id = owner.id, project.id, estimate.id
    user = await user_of(db_session, owner_id)
    with pytest.raises(DocumentDataError) as caught:
        await issuer().preview_estimate(db_session, user, project_id, estimate_id)
    assert caught.value.reason == "PREVIEW_ONLY_FOR_DRAFT"
    est = (await db_session.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one()
    est.status = EstimateStatus.DRAFT
    await db_session.commit()
    with pytest.raises(DocumentChatUnavailableError):
        await issuer(delivery=Delivery(DocumentChatUnavailableError("x"))).preview_estimate(db_session, user, project_id, estimate_id)


# --- the photo report ---------------------------------------------------------------------------------------------------------------


async def test_a_photo_report_is_numbered_rendered_and_sent(db_session):
    w = await seed_photos(db_session, telegram_id=9812)
    owner_id, project_id = w.owner.id, w.project.id
    sender = Delivery()
    run = issuer(w.storage, delivery=sender)
    reservation = await run.start_photo_report(db_session, await user_of(db_session, owner_id), project_id)
    assert (reservation.document.number, reservation.document.title) == ("FOTO/2026/10/08/1953", "Raport fotograficzny")
    await run.drain()
    (row,) = await journal(db_session)
    assert (row.status, row.kind, row.scope, row.pages) == ("SENT", "PHOTO_REPORT", None, row.pages) and row.pages >= 1
    text = text_of(sender.sent[0]["pdf"])
    assert "FOTO/2026/10/08/1953" in text and "Liczba zdjęć: 5" in text and sender.sent[0]["filename"] == "FOTO-2026-10-08-1953.pdf"


async def test_a_report_over_the_limit_is_refused_with_counts_and_a_part_by_room_goes_out(db_session):
    w = await seed_photos(db_session, telegram_id=9813)
    owner_id, project_id, salon_id = w.owner.id, w.project.id, w.salon.id
    sender = Delivery()
    run = issuer(w.storage, delivery=sender, max_photos=3)
    user = await user_of(db_session, owner_id)
    with pytest.raises(DocumentDataError) as caught:
        await run.start_photo_report(db_session, user, project_id)
    assert caught.value.reason == "PHOTO_LIMIT_EXCEEDED" and caught.value.details["count"] == 5
    assert await journal(db_session) == []
    part = await run.start_photo_report(db_session, await user_of(db_session, owner_id), project_id, room_ids=frozenset({salon_id}))
    assert part.document.title == "Raport fotograficzny (część: Salon)"
    assert part.document.scope == {"room_ids": [str(salon_id)], "include_project_photos": False}
    await run.drain()
    assert (await journal(db_session))[0].status == "SENT"
    text = text_of(sender.sent[0]["pdf"])
    assert "Raport częściowy — pomieszczenia: Salon" in text and "Liczba zdjęć: 3" in text and "Kuchnia" not in text


async def test_the_same_part_twice_is_one_document_and_another_part_is_another(db_session):
    w = await seed_photos(db_session, telegram_id=9814)
    owner_id, project_id, salon_id, kuchnia_id = w.owner.id, w.project.id, w.salon.id, w.kuchnia.id
    run = issuer(w.storage, renderer=StubRenderer(delay=0.2), max_photos=3)
    user = await user_of(db_session, owner_id)
    a = await run.start_photo_report(db_session, user, project_id, room_ids=frozenset({salon_id}))
    a2 = await run.start_photo_report(db_session, user, project_id, room_ids=frozenset({salon_id}))
    b = await run.start_photo_report(db_session, user, project_id, room_ids=frozenset({kuchnia_id}))
    assert a2.reused and a2.document.id == a.document.id and not b.reused and b.document.id != a.document.id
    await run.drain()


async def test_a_photo_report_needs_the_profile_and_something_to_show(db_session):
    w = await seed_photos(db_session, telegram_id=9815, with_profile=False)
    owner_id, project_id = w.owner.id, w.project.id
    run = issuer(w.storage)
    with pytest.raises(DocumentDataError) as no_profile:
        await run.start_photo_report(db_session, await user_of(db_session, owner_id), project_id)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    empty = await seed_photos(db_session, telegram_id=9816)
    await db_session.execute(PhotoAttachment.__table__.update().where(PhotoAttachment.project_id == empty.project.id).values(include_in_report=False))
    await db_session.commit()
    with pytest.raises(DocumentDataError) as nothing:
        await issuer(empty.storage).start_photo_report(db_session, await user_of(db_session, empty.owner.id), empty.project.id)
    assert nothing.value.reason == "REPORT_EMPTY" and await journal(db_session) == []


async def test_a_photo_that_cannot_be_read_fails_the_run_not_the_request(db_session):
    w = await seed_photos(db_session, telegram_id=9817)
    owner_id, project_id = w.owner.id, w.project.id
    del w.storage._objects[w.assets[0].storage_key_display]
    run = issuer(w.storage)
    await run.start_photo_report(db_session, await user_of(db_session, owner_id), project_id)
    await run.drain()
    (row,) = await journal(db_session)
    assert (row.status, row.error_code) == ("FAILED", "PHOTO_UNAVAILABLE")


async def test_the_summary_counts_the_photos_without_reading_any(db_session):
    from app.domain.documents.photo_report_document import PhotoReportDocumentService
    w = await seed_photos(db_session, telegram_id=9818)
    owner_id, project_id = w.owner.id, w.project.id
    w.storage._objects.clear()  # nothing could be read: the summary must not try
    service = PhotoReportDocumentService(db_session, w.storage, storage_name="r2-primary", max_photos=4)
    summary = await service.summary(owner_id, project_id)
    assert (summary.photo_count, summary.project_photos, summary.limit, summary.over_limit, summary.has_content) == (5, 1, 4, True, True)
    assert [(r.name, r.photos) for r in summary.rooms] == [("Salon", 3), ("Kuchnia", 1)]


def test_the_file_name_is_safe():
    assert pdf_filename("KOSZ/2026/10/08/1953-2") == "KOSZ-2026-10-08-1953-2.pdf"
    assert pdf_filename("../../etc/passwd") == "etc-passwd.pdf" and pdf_filename("a b/ł") == "a-b.pdf"


def test_the_issuer_is_one_per_process_and_never_a_new_one_per_request():
    from app.api.deps import get_document_issuer

    assert get_document_issuer() is get_document_issuer()
