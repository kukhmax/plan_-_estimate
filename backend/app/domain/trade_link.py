"""The link for the electrician and the plumber (V2-14): the texts of the message to the owner. The secret, the term and the hashes are those of the link of the client
(`app.domain.client_link`); the checklist and the cleaning of what a craftsman writes are in `app.domain.rules.trade_checklist`.
"""
import json
import re
from pathlib import Path

from app.domain.client_link import LANGUAGES, clean_language

TEXTS_FILE = Path(__file__).with_name("trade_link_texts.json")

_texts: dict[str, dict[str, str]] | None = None


def texts() -> dict[str, dict[str, str]]:
    global _texts
    if _texts is None:
        loaded = json.loads(TEXTS_FILE.read_text(encoding="utf-8"))
        for key, entry in loaded.items():
            if set(entry) != set(LANGUAGES) or not all(str(v).strip() for v in entry.values()):
                raise ValueError(f"trade link text {key} must have all four languages")
        _texts = loaded
    return _texts


def trade_name(trade: str, lang: str) -> str:
    return texts()[f"trade_{trade}"][clean_language(lang)]


def notice_text(lang: str, **values: object) -> str:
    """The message to the owner after a craftsman sent his answer; the words of the craftsman are cut and stripped of line breaks (one line in a chat)."""
    safe = {name: re.sub(r"\s+", " ", str(value)).strip()[:200] for name, value in values.items()}
    return texts()["notice_submit"][clean_language(lang)].format(**safe)
