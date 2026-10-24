"""The link for the client (V2-8): the secret, the hashes of what the client was shown, the texts of the consent, the checks of the words.

Pure rules, no database and no web framework. The Polish text of a consent is the one written to the journal; the other languages are a
help for the client who reads the page in another language.
"""
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

LANGUAGES = ("pl", "ru", "uk", "en")
LINK_DAYS = 30
TOKEN_BYTES = 32
MAX_TITLE = 120
MAX_DESCRIPTION = 2000
MAX_PROPOSALS = 20
MAX_AMOUNT = Decimal(10000000)
MAX_EXTRA_DAYS = 365
MIN_NAME = 2
MAX_NAME = 80
TEXTS_FILE = Path(__file__).with_name("client_link_texts.json")

LINK_TERM = timedelta(days=LINK_DAYS)


class ClientLinkError(Exception):
    """A rule of the link is broken; `code` is the machine word the screens translate."""

    def __init__(self, code: str, message: str = "", field: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.field = field


class ClientLinkNotFoundError(Exception):
    """No such link, proposal or journal row for this owner / this link."""


class LinkInactiveError(Exception):
    """The link is expired or revoked."""


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def looks_like_token(value: str | None) -> bool:
    """A cheap check before a query: the length and the alphabet of `token_urlsafe(32)` (43 characters)."""
    return bool(value) and re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is not None


def hash_value(secret: str, value: str) -> str:
    """HMAC of an address or a browser string: the journal keeps a proof that can be compared, never the raw value."""
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _money(value: Decimal | None) -> str:
    return "" if value is None else format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _digest(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_hash(estimate: Any) -> str:
    """What the client sees of an estimate: the version, the totals and every line's words, quantity, price and amount. Any change changes the hash."""
    return _digest(
        {
            "id": str(estimate.id),
            "version": estimate.version,
            "currency": estimate.currency,
            "vat": [estimate.vat_mode, estimate.vat_rate_percent],
            "total": _money(estimate.total),
            "gross": _money(estimate.gross_total),
            "lines": [
                [
                    ln.position,
                    ln.room_name,
                    ln.description,
                    str(ln.unit.value if hasattr(ln.unit, "value") else ln.unit),
                    str(ln.quantity),
                    _money(ln.unit_price),
                    _money(ln.amount),
                ]
                for ln in estimate.lines
            ],
        }
    )


def proposal_hash(title: str, description: str | None, amount: Decimal, currency: str, extra_days: int | None) -> str:
    return _digest([title, description or "", _money(amount), currency, extra_days])


def payable(estimate: Any) -> Decimal:
    """The amount the client pays: gross when a VAT mode is set, otherwise the total."""
    value = estimate.gross_total if estimate.gross_total is not None else estimate.total
    return value if value is not None else Decimal(0)


def clean_name(value: str | None) -> str:
    """The signer's name: collapsed spaces, no control characters, 2 to 80 characters."""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < MIN_NAME:
        raise ClientLinkError("NAME_REQUIRED", "write your name", "signer_name")
    if len(text) > MAX_NAME:
        raise ClientLinkError("NAME_TOO_LONG", f"at most {MAX_NAME} characters", "signer_name")
    return text


def clean_title(value: str | None) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", value or "")).strip()
    if not text:
        raise ClientLinkError("TITLE_REQUIRED", "write the title", "title")
    if len(text) > MAX_TITLE:
        raise ClientLinkError("TITLE_TOO_LONG", f"at most {MAX_TITLE} characters", "title")
    return text


def clean_description(value: str | None) -> str | None:
    text = (value or "").replace("\r\n", "\n").strip()
    if not text:
        return None
    if len(text) > MAX_DESCRIPTION:
        raise ClientLinkError("DESCRIPTION_TOO_LONG", f"at most {MAX_DESCRIPTION} characters", "description")
    return text


def clean_amount(value: Decimal | None) -> Decimal:
    if value is None or value <= 0:
        raise ClientLinkError("AMOUNT_INVALID", "the amount must be above zero", "amount")
    amount = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount > MAX_AMOUNT or amount <= 0:
        raise ClientLinkError("AMOUNT_INVALID", "the amount is out of range", "amount")
    return amount


def clean_days(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 0 or value > MAX_EXTRA_DAYS:
        raise ClientLinkError("DAYS_INVALID", f"0 to {MAX_EXTRA_DAYS} days", "extra_days")
    return value or None


def clean_language(value: str | None) -> str:
    return value if value in LANGUAGES else "pl"


_texts: dict[str, dict[str, str]] | None = None


def texts() -> dict[str, dict[str, str]]:
    global _texts
    if _texts is None:
        loaded = json.loads(TEXTS_FILE.read_text(encoding="utf-8"))
        for key, entry in loaded.items():
            if set(entry) != set(LANGUAGES) or not all(str(v).strip() for v in entry.values()):
                raise ValueError(f"client link text {key} must have all four languages")
        _texts = loaded
    return _texts


def _amount_text(value: Decimal, lang: str) -> str:
    plain = _money(value)
    return plain if lang == "en" else plain.replace(".", ",")


def statement(key: str, lang: str, *, contractor: str, amount: Decimal, currency: str, version: int | None = None,
              title: str | None = None, extra_days: int | None = None) -> str:
    """The sentence the client agrees to, in `lang`. `key`: estimate_accept, proposal_accept or proposal_decline."""
    lang = clean_language(lang)
    all_texts = texts()
    days = all_texts["days"][lang].format(days=extra_days) if extra_days else ""
    return all_texts[key][lang].format(
        version=version if version is not None else "",
        contractor=contractor,
        amount=_amount_text(amount, lang),
        currency=currency,
        title=title or "",
        days=days,
    )
