"""Short links to the PDF of a document (owner 2026-10-31: "Udostępnij / Pobierz PDF" in the application).

Telegram downloads a file by its address itself (`WebApp.downloadFile`), without the owner's token, so the address carries a short-lived signed
ticket: what it opens (an issued document of the journal, or the working version of an unfinished estimate), whose it is and until when.
HMAC-SHA256 with the application's secret; five minutes; nothing is stored.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

TTL_SECONDS = 300
DOCUMENT, ESTIMATE_DRAFT = "D", "E"


class FileLinkError(Exception):
    pass


@dataclass(frozen=True)
class FileTicket:
    kind: str
    owner_id: uuid.UUID
    project_id: uuid.UUID
    target_id: uuid.UUID


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(body: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode("utf-8"), b"pe-file:" + body.encode("ascii"), hashlib.sha256).digest())


def make(kind: str, owner_id: uuid.UUID, project_id: uuid.UUID, target_id: uuid.UUID, secret: str, *, now: float | None = None) -> str:
    payload = {"k": kind, "o": str(owner_id), "p": str(project_id), "t": str(target_id), "x": int((now or time.time()) + TTL_SECONDS)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body, secret)}"


def read(token: str, secret: str, *, now: float | None = None) -> FileTicket:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise FileLinkError("malformed") from exc
    if not hmac.compare_digest(signature, _sign(body, secret)):
        raise FileLinkError("signature")
    try:
        payload = json.loads(_unb64(body))
        ticket = FileTicket(payload["k"], uuid.UUID(payload["o"]), uuid.UUID(payload["p"]), uuid.UUID(payload["t"]))
        expires = int(payload["x"])
    except (ValueError, KeyError, TypeError) as exc:
        raise FileLinkError("malformed") from exc
    if ticket.kind not in (DOCUMENT, ESTIMATE_DRAFT):
        raise FileLinkError("kind")
    if (now or time.time()) > expires:
        raise FileLinkError("expired")
    return ticket
