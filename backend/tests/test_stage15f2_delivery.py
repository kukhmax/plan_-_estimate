"""Stage 15F.2 — handing a document to the owner's Telegram chat: the Bot API call, error mapping, and the token that must
never be seen anywhere."""

import logging

import httpx
import pytest

from app.core.config import Settings
from app.domain.documents import delivery as delivery_module
from app.domain.documents.delivery import (
    DisabledDelivery,
    TelegramBotApiDelivery,
    delivery_from_settings,
)
from app.domain.exceptions import (
    DocumentChatUnavailableError,
    DocumentDeliveryDisabledError,
    DocumentDeliveryRejectedError,
    DocumentDeliveryUnavailableError,
)

TOKEN = "123456789:AAH-secret-token_VALUE"
PDF = b"%PDF-1.4 test document"


def delivery(handler) -> TelegramBotApiDelivery:
    return TelegramBotApiDelivery(TOKEN, transport=httpx.MockTransport(handler))


def reply(status: int, description: str = "") -> httpx.Response:
    return httpx.Response(status, json={"ok": status == 200, "description": description, "error_code": status})


async def send(handler, **kw):
    return await delivery(handler).send_document(kw.get("chat_id", 777), kw.get("filename", "KOSZ-1.pdf"), kw.get("pdf", PDF), kw.get("caption", "Kosztorys"))


async def test_the_document_is_posted_as_a_pdf_to_the_chat_of_the_owner():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"], seen["type"] = str(request.url), request.read(), request.headers["content-type"]
        return reply(200)

    await send(handler, chat_id=424242, filename="KOSZ-2026-10-08-1953.pdf", caption="Kosztorys — Mokotów\nKOSZ/2026/10/08/1953")
    assert seen["url"] == f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    assert seen["type"].startswith("multipart/form-data")
    body = seen["body"]
    assert b'name="chat_id"' in body and b"424242" in body
    assert b'name="document"; filename="KOSZ-2026-10-08-1953.pdf"' in body and b"Content-Type: application/pdf" in body and PDF in body
    assert "Kosztorys — Mokotów\nKOSZ/2026/10/08/1953".encode() in body


async def test_a_long_caption_is_cut_to_the_telegram_limit():
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return reply(200)

    await send(handler, caption="x" * 3000)
    assert seen["body"].count(b"x") == 1024


@pytest.mark.parametrize(
    ("status", "description", "error"),
    [
        (403, "Forbidden: bot was blocked by the user", DocumentChatUnavailableError),
        (403, "Forbidden: bot can't initiate conversation with a user", DocumentChatUnavailableError),
        (400, "Bad Request: chat not found", DocumentChatUnavailableError),
        (400, "Bad Request: wrong file identifier", DocumentDeliveryRejectedError),
        (413, "Request Entity Too Large", DocumentDeliveryRejectedError),
        (401, "Unauthorized", DocumentDeliveryRejectedError),
        (429, "Too Many Requests: retry after 5", DocumentDeliveryUnavailableError),
        (500, "Internal Server Error", DocumentDeliveryUnavailableError),
        (502, "Bad Gateway", DocumentDeliveryUnavailableError),
    ],
)
async def test_telegram_answers_become_stable_errors(status, description, error):
    with pytest.raises(error) as caught:
        await send(lambda request: reply(status, description))
    assert type(caught.value) is error


async def test_an_answer_that_is_not_json_is_still_an_error_not_a_crash():
    with pytest.raises(DocumentDeliveryUnavailableError):
        await send(lambda request: httpx.Response(502, text="<html>bad gateway</html>"))
    with pytest.raises(DocumentDeliveryRejectedError):
        await send(lambda request: httpx.Response(400, text="not json"))


@pytest.mark.parametrize("failure", [httpx.ConnectError("boom"), httpx.ReadTimeout("slow"), httpx.WriteError("broken pipe")])
async def test_a_network_failure_is_unavailable(failure):
    def handler(request):
        raise failure

    with pytest.raises(DocumentDeliveryUnavailableError):
        await send(handler)


async def test_the_token_is_nowhere_in_an_error_a_repr_or_a_chained_exception(caplog):
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")  # a transport error that names the URL

    sender = delivery(handler)
    with pytest.raises(DocumentDeliveryUnavailableError) as caught:
        await sender.send_document(1, "a.pdf", PDF, "c")
    error = caught.value
    assert TOKEN not in str(error) and TOKEN not in repr(error) and TOKEN not in repr(sender) and TOKEN not in str(sender)
    assert error.__cause__ is None and error.__suppress_context__
    for status in (403, 429, 400):
        with pytest.raises(Exception) as other:
            await delivery(lambda request, s=status: reply(s, "x")).send_document(1, "a.pdf", PDF, "c")
        assert TOKEN not in str(other.value) and TOKEN not in repr(other.value)


async def test_the_http_client_loggers_do_not_write_the_url_with_the_token(caplog):
    # httpx logs "HTTP Request: POST <url>" at INFO; the module raises its loggers above INFO when it is imported
    assert delivery_module and logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
    caplog.set_level(logging.INFO)
    await send(lambda request: reply(200))
    assert TOKEN not in caplog.text and "api.telegram.org" not in caplog.text


async def test_the_disabled_delivery_refuses():
    with pytest.raises(DocumentDeliveryDisabledError):
        await DisabledDelivery().send_document(1, "a.pdf", PDF, "c")


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_the_delivery_follows_the_settings():
    assert isinstance(delivery_from_settings(settings(TELEGRAM_BOT_TOKEN=TOKEN)), TelegramBotApiDelivery)
    assert isinstance(delivery_from_settings(settings(TELEGRAM_BOT_TOKEN="")), DisabledDelivery)
    assert isinstance(delivery_from_settings(settings(TELEGRAM_BOT_TOKEN=TOKEN, DOCUMENT_DELIVERY="disabled")), DisabledDelivery)


def test_a_delivery_needs_a_token():
    with pytest.raises(ValueError):
        TelegramBotApiDelivery("")
