"""Stage 18D -- a text message to the owner's chat: the Bot API call, the "Open" button, the error mapping, and the token that must never be seen."""
import json
import logging

import httpx
import pytest

from app.core.config import Settings
from app.domain.documents.delivery import (
    DisabledMessageSender,
    TelegramMessageSender,
    message_sender_from_settings,
)
from app.domain.exceptions import (
    MessageChatUnavailableError,
    MessageDeliveryDisabledError,
    MessageRejectedError,
    MessageUnavailableError,
)

TOKEN = "123456789:AAH-secret-token_VALUE"


def sender(handler) -> TelegramMessageSender:
    return TelegramMessageSender(TOKEN, transport=httpx.MockTransport(handler))


def reply(status: int, description: str = "", **extra) -> httpx.Response:
    return httpx.Response(status, json={"ok": status == 200, "description": description, "error_code": status, **extra})


async def test_the_message_is_posted_as_json_to_the_chat_with_an_open_button():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["json"] = str(request.url), json.loads(request.read())
        return reply(200)

    await sender(handler).send_message(424242, "Koniec przerwy", open_url="https://plan-estimate.pl?open=calendar", button_text="Otwórz")
    assert seen["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert seen["json"]["chat_id"] == 424242 and seen["json"]["text"] == "Koniec przerwy"
    assert seen["json"]["reply_markup"] == {"inline_keyboard": [[{"text": "Otwórz", "web_app": {"url": "https://plan-estimate.pl?open=calendar"}}]]}


async def test_without_an_address_there_is_no_button():
    seen = {}

    def handler(request):
        seen["json"] = json.loads(request.read())
        return reply(200)

    await sender(handler).send_message(1, "x")
    assert "reply_markup" not in seen["json"]


async def test_a_long_text_is_cut_to_the_telegram_limit():
    seen = {}

    def handler(request):
        seen["json"] = json.loads(request.read())
        return reply(200)

    await sender(handler).send_message(1, "x" * 6000)
    assert len(seen["json"]["text"]) == 4096


@pytest.mark.parametrize(
    ("status", "description", "error"),
    [
        (403, "Forbidden: bot was blocked by the user", MessageChatUnavailableError),
        (403, "Forbidden: bot can't initiate conversation with a user", MessageChatUnavailableError),
        (400, "Bad Request: chat not found", MessageChatUnavailableError),
        (400, "Bad Request: BUTTON_URL_INVALID", MessageRejectedError),
        (401, "Unauthorized", MessageRejectedError),
        (404, "Not Found", MessageRejectedError),
        (429, "Too Many Requests: retry after 5", MessageUnavailableError),
        (500, "Internal Server Error", MessageUnavailableError),
        (502, "Bad Gateway", MessageUnavailableError),
    ],
)
async def test_telegram_answers_become_stable_errors(status, description, error):
    with pytest.raises(error) as caught:
        await sender(lambda request: reply(status, description)).send_message(1, "x")
    assert type(caught.value) is error


async def test_a_slow_down_answer_carries_the_wait():
    with pytest.raises(MessageUnavailableError) as caught:
        await sender(lambda request: reply(429, "Too Many Requests", parameters={"retry_after": 7})).send_message(1, "x")
    assert caught.value.retry_after == 7
    with pytest.raises(MessageUnavailableError) as other:
        await sender(lambda request: httpx.Response(429, text="slow down")).send_message(1, "x")
    assert other.value.retry_after is None


async def test_an_answer_that_is_not_json_is_still_an_error_not_a_crash():
    with pytest.raises(MessageUnavailableError):
        await sender(lambda request: httpx.Response(502, text="<html>bad gateway</html>")).send_message(1, "x")
    with pytest.raises(MessageRejectedError):
        await sender(lambda request: httpx.Response(400, text="not json")).send_message(1, "x")


@pytest.mark.parametrize("failure", [httpx.ConnectError("boom"), httpx.ReadTimeout("slow"), httpx.WriteError("broken pipe")])
async def test_a_network_failure_is_unavailable(failure):
    def handler(request):
        raise failure

    with pytest.raises(MessageUnavailableError):
        await sender(handler).send_message(1, "x")


async def test_the_error_codes_are_stable_names():
    assert (MessageChatUnavailableError.code, MessageRejectedError.code, MessageUnavailableError.code, MessageDeliveryDisabledError.code) == (
        "BOT_BLOCKED", "REJECTED", "UNAVAILABLE", "DELIVERY_DISABLED",
    )


async def test_the_token_is_nowhere_in_an_error_a_repr_or_a_chained_exception():
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")  # a transport error that names the URL

    client = sender(handler)
    with pytest.raises(MessageUnavailableError) as caught:
        await client.send_message(1, "x")
    error = caught.value
    assert TOKEN not in str(error) and TOKEN not in repr(error) and TOKEN not in repr(client) and TOKEN not in str(client)
    assert error.__cause__ is None and error.__suppress_context__
    for status in (403, 429, 400, 500):
        with pytest.raises(Exception) as other:
            await sender(lambda request, s=status: reply(s, "x")).send_message(1, "x")
        assert TOKEN not in str(other.value) and TOKEN not in repr(other.value)


async def test_the_http_client_loggers_do_not_write_the_url_with_the_token(caplog):
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    caplog.set_level(logging.INFO)
    await sender(lambda request: reply(200)).send_message(1, "x")
    assert TOKEN not in caplog.text and "api.telegram.org" not in caplog.text


async def test_the_disabled_sender_refuses():
    with pytest.raises(MessageDeliveryDisabledError):
        await DisabledMessageSender().send_message(1, "x")


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_the_sender_follows_the_settings_and_needs_a_token():
    assert isinstance(message_sender_from_settings(settings(TELEGRAM_BOT_TOKEN=TOKEN)), TelegramMessageSender)
    assert isinstance(message_sender_from_settings(settings(TELEGRAM_BOT_TOKEN="")), DisabledMessageSender)
    with pytest.raises(ValueError):
        TelegramMessageSender("")


def test_the_calendar_settings_are_safe_by_default_and_the_button_address_must_be_https():
    default = settings()
    assert default.CALENDAR_DISPATCHER_ENABLED is False and default.CALENDAR_WEB_APP_URL == ""
    assert settings(CALENDAR_WEB_APP_URL=" https://plan-estimate.pl/ ").CALENDAR_WEB_APP_URL == "https://plan-estimate.pl"
    with pytest.raises(ValueError):
        settings(CALENDAR_WEB_APP_URL="http://plan-estimate.pl")
    with pytest.raises(ValueError):
        settings(CALENDAR_DISPATCH_INTERVAL_SECONDS=0)
