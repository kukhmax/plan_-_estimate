"""Polish labels of client-facing documents (Stage 15B).

One flat dictionary (`locales/pl.json`): the only place where document wording lives, so it never leaks into React and a
template cannot silently print an empty label -- an unknown key is a `DocumentTemplateError`.
"""

import json
from functools import cache
from pathlib import Path

from app.domain.exceptions import DocumentTemplateError

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
CLIENT_LANGUAGE = "pl"  # client-facing documents default strictly to Polish


@cache
def load_labels(language: str = CLIENT_LANGUAGE) -> dict[str, str]:
    path = LOCALES_DIR / f"{language}.json"
    if not path.is_file():
        raise DocumentTemplateError(f"no labels for language {language!r}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise DocumentTemplateError(f"labels of {language!r} must be a flat string dictionary")
    return data


class Labels:
    def __init__(self, language: str = CLIENT_LANGUAGE) -> None:
        self.language = language
        self._labels = load_labels(language)

    def __call__(self, key: str, **params: object) -> str:
        try:
            text = self._labels[key]
        except KeyError:
            raise DocumentTemplateError(f"unknown label {key!r}") from None
        try:
            return text.format(**params) if params or "{" in text else text
        except (KeyError, IndexError) as exc:
            raise DocumentTemplateError(f"label {key!r} needs the parameter {exc}") from None
