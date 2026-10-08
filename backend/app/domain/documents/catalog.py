"""Polish names of Price Book items for client documents (Stage 15D).

An estimate line stores its `description` as the owner's display name, or -- for the built-in catalog -- as a translation
key (`pricebook.seed.prep_prot`); the Polish texts of those keys live in the frontend. A client document must never print
a raw key, so the backend keeps its own copy (`catalog/price_names_pl.json`) and a test pins it to the frontend dictionary
and to the seed, so the two cannot drift apart.
"""

import json
import re
from functools import cache
from pathlib import Path

from app.domain.exceptions import DocumentDataError

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
CATALOG_FILE = CATALOG_DIR / "price_names_pl.json"
CHECKLIST_FILE = CATALOG_DIR / "checklist_names_pl.json"
RISK_FILE = CATALOG_DIR / "risk_texts_pl.json"
# What a built-in name key looks like. Owner-typed names that merely contain a dot ("Wałek 2.5") do not match.
KEY_PATTERN = re.compile(r"^pricebook\.[a-z0-9_]+(\.[a-z0-9_]+)+$")
CHECKLIST_KEY_PATTERN = re.compile(r"^checklist\.(question|option|section)\.[a-z0-9_]+$")
# The built-in risk texts: risk.<rule code>.<title | explanation | consequence | communication>.
RISK_KEY_PATTERN = re.compile(r"^risk\.[a-z0-9_]+\.(title|explanation|consequence|communication)$")


def _load(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in data.items()):
        raise DocumentDataError("CATALOG_INVALID", f"{path.name} must be a flat dictionary of non-empty strings")
    return data


@cache
def price_names() -> dict[str, str]:
    return _load(CATALOG_FILE)


@cache
def checklist_names() -> dict[str, str]:
    """Polish texts of the built-in inspection sections, questions and answer options (Stage 15E)."""
    return _load(CHECKLIST_FILE)


def localize_description(description: str) -> str:
    """The Polish text for a built-in key, the text itself for an owner's name; an unknown built-in key is an error."""
    if not KEY_PATTERN.match(description):
        return description
    try:
        return price_names()[description]
    except KeyError:
        raise DocumentDataError("CATALOG_NAME_UNKNOWN", f"no Polish name for the price item key {description!r}") from None


@cache
def risk_texts() -> dict[str, str]:
    """Polish client-facing texts of the built-in risk rules (Stage 15E). The `mitigation` texts are instructions to the
    contractor ("Wzmocnij podłoże ..."), not for the client, so they are not part of this catalog; the `communication`
    text is the contractor's own words to the client."""
    return _load(RISK_FILE)


def localize_risk_text(key: str) -> str:
    """The Polish text of a built-in risk key; any other key is an error (a risk always carries its own keys)."""
    if not RISK_KEY_PATTERN.match(key):
        raise DocumentDataError("CATALOG_NAME_UNKNOWN", f"not a risk text key: {key!r}")
    try:
        return risk_texts()[key]
    except KeyError:
        raise DocumentDataError("CATALOG_NAME_UNKNOWN", f"no Polish text for the risk key {key!r}") from None


def localize_checklist_text(text: str) -> str:
    """The Polish text of a built-in question / option key; an unknown built-in key is an error, anything else is kept."""
    if not CHECKLIST_KEY_PATTERN.match(text):
        return text
    try:
        return checklist_names()[text]
    except KeyError:
        raise DocumentDataError("CATALOG_NAME_UNKNOWN", f"no Polish text for the checklist key {text!r}") from None
