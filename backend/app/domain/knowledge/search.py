"""Search in the knowledge base (Stage 17): deterministic, in memory, no external service.

A query is cut into words; every word must be found (AND) at the beginning of a word of the entry -- "rekoj" finds
"rękojmia", "лод" finds "лодка". Letters are compared without their marks and case: ą = a, ł = l, ё = е, й = и. The order of
the result is explainable and stable: the exact code first, then the words of the title, the tags, the place in the source,
the text; equal scores keep the order of the codes.
"""

import re
import unicodedata
from dataclasses import dataclass

from app.domain.knowledge.catalog import Entry, KnowledgeCatalog

# letters that a canonical decomposition does not split into a base letter and a mark
_FOLD = str.maketrans({"ł": "l", "ø": "o", "đ": "d", "ß": "ss", "ё": "е", "й": "и"})
_WORD = re.compile(r"[0-9a-zа-я]+")

# weight of a query word found in each field
_WEIGHTS = (("title", 100), ("tags", 50), ("locator", 30), ("text", 10))
_EXACT_CODE = 1000


def fold(text: str) -> str:
    lowered = text.lower().translate(_FOLD)
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def words(text: str) -> list[str]:
    return _WORD.findall(fold(text))


@dataclass(frozen=True, slots=True)
class _Indexed:
    entry: Entry
    fields: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Filters:
    kind: str | None = None
    source: str | None = None
    tag: str | None = None
    work: str | None = None
    substrate: str | None = None
    quality: str | None = None
    status: str | None = None


def _index(catalog: KnowledgeCatalog) -> list[_Indexed]:
    sources = {s.code: s for s in catalog.sources}
    indexed = []
    for entry in catalog.entries:
        source = sources[entry.source]
        indexed.append(_Indexed(entry, {
            "title": tuple(words(f"{entry.title_pl} {entry.title_ru}")),
            "tags": tuple(words(" ".join(entry.tags))),
            "locator": tuple(words(f"{entry.locator or ''} {source.designation} {source.title_pl}")),
            "text": tuple(words(f"{entry.summary_pl or ''} {entry.explanation_ru or ''}")),
        }))
    return indexed


def _passes(entry: Entry, kind: str, filters: Filters) -> bool:
    return (
        (filters.kind is None or kind == filters.kind)
        and (filters.source is None or entry.source == filters.source)
        and (filters.tag is None or filters.tag in entry.tags)
        and (filters.work is None or filters.work in entry.works)
        and (filters.substrate is None or filters.substrate in entry.substrates)
        and (filters.quality is None or filters.quality in entry.qualities)
        and (filters.status is None or entry.status == filters.status)
    )


def search(catalog: KnowledgeCatalog, query: str = "", filters: Filters | None = None) -> list[Entry]:
    """The entries that match every word of the query and every filter, best first. An empty query lists by title."""
    filters = filters or Filters()
    kinds = {s.code: s.kind for s in catalog.sources}
    terms = words(query)
    exact = query.strip().upper()
    scored: list[tuple[int, str, Entry]] = []
    for item in _index(catalog):
        entry = item.entry
        if not _passes(entry, kinds[entry.source], filters):
            continue
        if not terms:
            scored.append((0, fold(entry.title_pl), entry))
            continue
        score = _EXACT_CODE if entry.code == exact else 0
        for term in terms:
            best = max((weight for field, weight in _WEIGHTS if any(w.startswith(term) for w in item.fields[field])), default=0)
            if best == 0 and entry.code != exact:
                break
            score += best
        else:
            scored.append((-score, entry.code, entry))
    scored.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in scored]
