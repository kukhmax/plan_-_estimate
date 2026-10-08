"""Handing a finished document to the owner (Stage 15F).

The port is `DocumentDelivery.send_document`. The real one posts the PDF to the Telegram Bot API (`sendDocument`) with the
backend's bot token, to the private chat of the owner (the chat id of a private chat is the user's Telegram id). The
owner must have started the bot at least once, which they have done to open the Mini App.

The token lives in the URL path that Telegram requires, so it must never escape:
- the HTTP client libraries log the request URL at INFO: their loggers are raised to WARNING here, once, on import;
- no exception raised from here carries the URL (nothing calls `raise_for_status`, errors are mapped by hand) and the
  original exception is not chained (`from None`), so a traceback cannot print it either.
"""

import logging
from typing import Protocol

import httpx

from app.core.config import Settings
from app.domain.exceptions import (
    DocumentChatUnavailableError,
    DocumentDeliveryDisabledError,
    DocumentDeliveryRejectedError,
    DocumentDeliveryUnavailableError,
)

for _name in ("httpx", "httpcore"):  # they log `POST https://api.telegram.org/bot<TOKEN>/sendDocument` at INFO
    logging.getLogger(_name).setLevel(logging.WARNING)

TELEGRAM_API = "https://api.telegram.org"
MAX_CAPTION = 1024  # Telegram's limit for a document caption


class DocumentDelivery(Protocol):
    async def send_document(self, chat_id: int, filename: str, pdf: bytes, caption: str) -> None:
        """Send `pdf` to the chat. Raises a `DocumentDeliveryError` subclass; returns only when Telegram accepted it."""
        ...


class DisabledDelivery:
    async def send_document(self, chat_id: int, filename: str, pdf: bytes, caption: str) -> None:
        raise DocumentDeliveryDisabledError("document delivery is switched off")


class TelegramBotApiDelivery:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = TELEGRAM_API,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("a bot token is required")
        self._url = f"{base_url.rstrip('/')}/bot{token}/sendDocument"
        self._timeout = httpx.Timeout(timeout, connect=10.0)
        self._transport = transport

    def __repr__(self) -> str:  # never print the URL (it holds the token)
        return "TelegramBotApiDelivery()"

    async def send_document(self, chat_id: int, filename: str, pdf: bytes, caption: str) -> None:
        data = {"chat_id": str(chat_id), "caption": caption[:MAX_CAPTION]}
        files = {"document": (filename, pdf, "application/pdf")}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(self._url, data=data, files=files)
        except httpx.HTTPError:
            raise DocumentDeliveryUnavailableError("Telegram could not be reached") from None
        status = response.status_code
        if status == 200:
            return
        description = _description(response)
        if status == 403 or (status == 400 and "chat not found" in description.lower()):
            raise DocumentChatUnavailableError("Telegram does not allow the bot to write to this chat") from None
        if status == 429 or status >= 500:
            raise DocumentDeliveryUnavailableError(f"Telegram answered {status}") from None
        raise DocumentDeliveryRejectedError(f"Telegram refused the document ({status})") from None


def _description(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    value = payload.get("description") if isinstance(payload, dict) else None
    return value if isinstance(value, str) else ""


def delivery_from_settings(settings: Settings) -> DocumentDelivery:
    token = settings.TELEGRAM_BOT_TOKEN
    if settings.DOCUMENT_DELIVERY != "telegram" or not token:
        return DisabledDelivery()
    return TelegramBotApiDelivery(token, timeout=settings.DOCUMENT_DELIVERY_TIMEOUT_SECONDS)
