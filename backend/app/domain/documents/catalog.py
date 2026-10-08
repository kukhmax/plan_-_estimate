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

CATALOG_FILE = Path(__file__).resolve().parent / "catalog" / "price_names_pl.json"
# What a built-in name key looks like. Owner-typed names that merely contain a dot ("Wałek 2.5") do not match.
KEY_PATTERN = re.compile(r"^pricebook\.[a-z0-9_]+(\.[a-z0-9_]+)+$")


@cache
def price_names() -> dict[str, str]:
    data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in data.items()):
        raise DocumentDataError("CATALOG_INVALID", "the price name catalog must be a flat dictionary of non-empty strings")
    return data


def localize_description(description: str) -> str:
    """The Polish text for a built-in key, the text itself for an owner's name; an unknown built-in key is an error."""
    if not KEY_PATTERN.match(description):
        return description
    try:
        return price_names()[description]
    except KeyError:
        raise DocumentDataError("CATALOG_NAME_UNKNOWN", f"no Polish name for the price item key {description!r}") from None
