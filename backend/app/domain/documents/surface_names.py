"""The names of the surfaces in a document (V2-4 correction).

A surface made by the application is stored with a language-neutral name ("Wall 1", "Floor", "Ceiling"); the screens translate it, and the documents of
the client are Polish, so a document translates it too. A name the owner typed is kept as it is.
"""
import re

from app.domain.documents.labels import Labels

_CANONICAL_WALL = re.compile(r"^Wall (\d+)$")


def surface_title(name: str) -> str:
    """The canonical language-neutral names ("Wall 1", "Floor", "Ceiling") in Polish; an owner's own name is kept."""
    labels = Labels()
    match = _CANONICAL_WALL.match(name)
    if match:
        return labels("techcard.canonical.wall", n=match.group(1))
    if name == "Floor":
        return labels("techcard.canonical.floor")
    if name == "Ceiling":
        return labels("techcard.canonical.ceiling")
    return name


def surface_title_or_none(name: str | None) -> str | None:
    return None if name is None else surface_title(name)
