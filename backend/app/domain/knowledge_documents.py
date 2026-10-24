"""The rules of the owner's own documents of the knowledge base (V2-7a; a module of its own, outside the package of the approved catalogue): what a title, a link, a tag and a file may be. Pure functions, no database.

The file is judged by its first bytes, never by the name or the type the browser announced: a PDF (`%PDF-`), a JPEG or a PNG. Anything else
is refused with a code the screen can say in words.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from app.models.knowledge_document import KINDS

MAX_TITLE = 200
MAX_URL = 1000
MAX_WHEN_TO_USE = 1000
MAX_BODY = 100_000
MAX_TAGS = 10
MAX_TAG = 30
MAX_FILE_BYTES = 10_000_000
MAX_DOCUMENTS = 100
MAX_TOTAL_FILE_BYTES = 300_000_000
SNIPPET = 160

# the same rule of comparison as the search of the approved catalogue (letters without their marks and case), kept here on purpose: the guards of
# the knowledge base (Stage 17F) allow nothing outside it to import it, and the own documents are not a part of it
_FOLD = str.maketrans({"ł": "l", "ø": "o", "đ": "d", "ß": "ss", "ё": "е", "й": "и"})
_WORD = re.compile(r"[0-9a-zа-яіїєґ]+")
_TAG_SPLIT = re.compile(r"[,;\n]")
_SPACES = re.compile(r"\s+")
_NAME_SAFE = re.compile(r"[^0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźżА-Яа-яЁёІіЇїЄєҐґ._ ()+-]")
_FILE_TYPES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(_FOLD))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def words(text: str) -> list[str]:
    return _WORD.findall(fold(text))


class OwnDocumentError(Exception):
    """A refused document: `code` is the machine word, `field` the form field it is about (None: the whole document)."""

    def __init__(self, code: str, message: str = "", field: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.field = field


class OwnDocumentNotFoundError(OwnDocumentError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_DOCUMENT_NOT_FOUND", "The document was not found")


@dataclass(frozen=True)
class DocumentFields:
    title: str
    kind: str
    source_url: str | None
    doc_date: date | None
    when_to_use: str | None
    body: str | None
    tags: list[str]


def _text(value: str | None, limit: int, field: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if len(text) > limit:
        raise OwnDocumentError("TOO_LONG", f"{field} is longer than {limit}", field)
    return text


def normalise_tags(raw: str | list[str] | None) -> list[str]:
    parts = _TAG_SPLIT.split(raw) if isinstance(raw, str) else list(raw or [])
    seen: set[str] = set()
    tags: list[str] = []
    for part in parts:
        tag = _SPACES.sub(" ", part).strip().lstrip("#").strip()
        if not tag:
            continue
        if len(tag) > MAX_TAG:
            raise OwnDocumentError("TAG_TOO_LONG", f"a tag is longer than {MAX_TAG}", "tags")
        key = fold(tag)
        if key not in seen:
            seen.add(key)
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise OwnDocumentError("TOO_MANY_TAGS", f"more than {MAX_TAGS} tags", "tags")
    return tags


def check_url(value: str | None) -> str | None:
    url = (value or "").strip()
    if not url:
        return None
    if len(url) > MAX_URL:
        raise OwnDocumentError("TOO_LONG", "the link is too long", "source_url")
    if not re.fullmatch(r"https?://[^\s/$.?#][^\s]*", url, flags=re.IGNORECASE):
        raise OwnDocumentError("URL_INVALID", "the link must start with http:// or https://", "source_url")
    return url


def parse_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise OwnDocumentError("DATE_INVALID", "the date must be YYYY-MM-DD", "doc_date") from None


def build_fields(*, title: str, kind: str, source_url: str | None, doc_date: str | None, when_to_use: str | None, body: str | None,
                 tags: str | list[str] | None) -> DocumentFields:
    clean_title = _SPACES.sub(" ", (title or "")).strip()
    if not clean_title:
        raise OwnDocumentError("TITLE_REQUIRED", "the title is required", "title")
    if len(clean_title) > MAX_TITLE:
        raise OwnDocumentError("TOO_LONG", f"the title is longer than {MAX_TITLE}", "title")
    clean_kind = (kind or "OTHER").strip().upper()
    if clean_kind not in KINDS:
        raise OwnDocumentError("KIND_UNKNOWN", "unknown kind of document", "kind")
    return DocumentFields(
        title=clean_title,
        kind=clean_kind,
        source_url=check_url(source_url),
        doc_date=parse_date(doc_date),
        when_to_use=_text(when_to_use, MAX_WHEN_TO_USE, "when_to_use"),
        body=_text(body, MAX_BODY, "body"),
        tags=normalise_tags(tags),
    )


def sniff_file(content: bytes) -> tuple[str, str]:
    """(mime, extension) from the first bytes, or a refusal."""
    for magic, mime, extension in _FILE_TYPES:
        if content.startswith(magic):
            return mime, extension
    raise OwnDocumentError("FILE_TYPE_UNSUPPORTED", "only a PDF, a JPEG or a PNG can be added", "file")


def safe_filename(announced: str | None, extension: str) -> str:
    """The name shown and offered for download: no path, no odd characters, the extension of the real type."""
    name = (announced or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = _SPACES.sub(" ", _NAME_SAFE.sub("", stem)).strip(" .")[:120]
    return f"{stem or 'document'}{extension}"


def check_file(content: bytes) -> None:
    if not content:
        raise OwnDocumentError("FILE_EMPTY", "the file is empty", "file")
    if len(content) > MAX_FILE_BYTES:
        raise OwnDocumentError("FILE_TOO_LARGE", f"the file is larger than {MAX_FILE_BYTES // 1_000_000} MB", "file")


def snippet(body: str | None) -> str | None:
    if not body:
        return None
    one_line = _SPACES.sub(" ", body).strip()
    return one_line if len(one_line) <= SNIPPET else one_line[: SNIPPET - 1].rstrip() + "…"


# weight of a query word found in each field (as in the catalogue: the title first)
_WEIGHTS = (("title", 100), ("tags", 50), ("when", 30), ("file", 20), ("body", 10))


def score(query: str, *, title: str, tags: list[str], when_to_use: str | None, file_name: str | None, body: str | None) -> int | None:
    """None: some word of the query is found nowhere; otherwise the sum of the best weight of each word. An empty query scores 0."""
    terms = words(query)
    if not terms:
        return 0
    fields = {
        "title": words(title), "tags": words(" ".join(tags)), "when": words(when_to_use or ""), "file": words(file_name or ""),
        "body": words(body or ""),
    }
    total = 0
    for term in terms:
        best = max((weight for name, weight in _WEIGHTS if any(w.startswith(term) for w in fields[name])), default=0)
        if best == 0:
            return None
        total += best
    return total
