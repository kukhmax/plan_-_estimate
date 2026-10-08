"""Stage 15F.3 — every code the document backend can answer or record has words in both languages of the interface.

The backend sends stable codes (never text for the screen); the screen keeps one sentence per code in `documents.errors` of
`pl.json` and `ru.json`. A new code added to the backend without its sentences would show the owner a generic message, so this
scan makes that a test failure instead.
"""

import json
import re
from pathlib import Path

from app.domain import exceptions

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND_LOCALES = BACKEND.parent / "frontend" / "src" / "locales"
SCANNED = [*(BACKEND / "app" / "domain" / "documents").glob("*.py"), BACKEND / "app" / "api" / "v1" / "endpoints" / "documents.py",
           BACKEND / "app" / "domain" / "services" / "issued_document_service.py"]
# codes a screen never shows as a document problem: they belong to the executor profile screen or to the journal internals
NOT_FOR_THE_DOCUMENT_SCREEN = {"CATALOG_INVALID", "DOCUMENT_DATA_INVALID"}  # the second is the class code: the answer carries the reason


def backend_codes() -> set[str]:
    codes: set[str] = set()
    for path in SCANNED:
        source = path.read_text(encoding="utf-8")
        codes |= set(re.findall(r"""DocumentDataError\(\s*["']([A-Z_]+)["']""", source))
        codes |= set(re.findall(r"""_error\(\s*["']([A-Z_]+)["']""", source))
        codes |= set(re.findall(r"""error_code="([A-Z_]+)\"""", source))
        codes |= set(re.findall(r"""code = "([A-Z_]+)\"""", source))
    for name in dir(exceptions):
        cls = getattr(exceptions, name)
        if isinstance(cls, type) and name.startswith("Document") and hasattr(cls, "code"):
            codes.add(cls.code)
    codes |= {"INTERRUPTED", "INTERNAL_ERROR"}  # recorded by the issuer / the journal for a run that did not end by itself
    return codes - NOT_FOR_THE_DOCUMENT_SCREEN


def screen_codes(language: str) -> set[str]:
    data = json.loads((FRONTEND_LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    return set(data["documents"]["errors"])


def test_the_scan_finds_the_codes_it_is_meant_to():
    codes = backend_codes()
    assert {"EXECUTOR_PROFILE_REQUIRED", "PHOTO_LIMIT_EXCEEDED", "TELEGRAM_CHAT_UNAVAILABLE", "DOCUMENT_QUEUE_FULL",
            "DOCUMENT_RENDER_TIMEOUT", "ESTIMATE_NOT_FINAL", "PROJECT_NOT_FOUND", "INTERRUPTED"} <= codes
    assert len(codes) >= 25


def test_every_backend_code_has_a_sentence_in_polish_and_in_russian():
    codes = backend_codes()
    for language in ("pl", "ru"):
        assert codes - screen_codes(language) == set(), f"{language}: codes without a sentence"


def test_the_screens_do_not_keep_sentences_for_codes_that_no_longer_exist():
    extra = (screen_codes("pl") - backend_codes()) - {"UNKNOWN"}
    assert extra == set()
