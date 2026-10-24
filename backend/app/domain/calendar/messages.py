"""The text of the messages to the owner (Stage 18D): what goes into one message, and in which words.

Pure functions. The words are in `texts.json` (Polish, Russian, Ukrainian and English, like every text of the application, never in code); the owner's own
reminders carry the owner's own words. What is due at one moment is put together so that the owner is not flooded: everything announced
by a day (a term, a start) goes into **one digest**, the ends of breaks of one room into **one message**, the rest one message each.
"""
import json
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from functools import lru_cache
from pathlib import Path

from app.domain.calendar import DEFAULT_TIMEZONE
from app.domain.calendar.policy import LATE, lateness

LANGUAGES = ("pl", "ru", "uk", "en")
TEXTS_FILE = Path(__file__).parent / "texts.json"
FRAME_KEYS = ("late", "digest_title", "today", "in_days", "more", "button", "break_hours", "surfaces", "own_prefix")
BREAK_KINDS = ("BREAK_START", "BREAK_END")
DIGEST_LIMIT = 25  # lines of one digest; the rest is counted


def language_of_telegram(code: str | None) -> str:
    """The language of the messages for an owner who did not choose one: that of Telegram (uk-UA, en, ru ...), anything else is Polish."""
    base = (code or "").lower().replace("_", "-").split("-")[0]
    return base if base in LANGUAGES else "pl"


class CalendarTextsError(Exception):
    """The file of the texts is wrong: a missing key or a missing language (the application refuses to start on it)."""


@dataclass(frozen=True)
class Texts:
    titles: Mapping[str, Mapping[str, str]]
    frame: Mapping[str, Mapping[str, str]]


@lru_cache(maxsize=1)
def load_texts() -> Texts:
    raw = json.loads(TEXTS_FILE.read_text(encoding="utf-8"))
    titles, frame = raw["titles"], raw["frame"]
    for group, keys in ((titles, titles), (frame, FRAME_KEYS)):
        for key in keys:
            entry = group.get(key)
            if not isinstance(entry, dict) or any(not isinstance(entry.get(lang), str) or not entry[lang].strip() for lang in LANGUAGES):
                raise CalendarTextsError(f"texts.json: {key!r} needs a text in {LANGUAGES}")
    return Texts(titles, frame)


@dataclass(frozen=True)
class ReminderView:
    """A reminder with the names it needs for its message."""

    id: uuid.UUID
    origin: str
    kind: str
    ref: str
    title: str | None
    title_key: str | None
    params: Mapping[str, object]
    event_on: date | None
    lead_days: int
    send_at: datetime
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    room_id: uuid.UUID | None = None
    room_name: str | None = None
    surface_name: str | None = None


@dataclass(frozen=True)
class Message:
    reminder_ids: tuple[uuid.UUID, ...]
    text: str
    open_url: str | None
    button: str


def _date(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _open_url(base_url: str, project_id: uuid.UUID | None) -> str | None:
    if not base_url:
        return None
    return f"{base_url}?open={'project:' + str(project_id) if project_id else 'calendar'}"


def _context(view: ReminderView) -> str:
    return " · ".join(part for part in (view.project_name, view.room_name, view.surface_name) if part)


def _title(view: ReminderView, lang: str, texts: Texts) -> str:
    if view.origin == "USER":
        return f"{texts.frame['own_prefix'][lang]} {view.title}"
    if view.title_key not in texts.titles:
        return view.title_key or view.kind
    text = texts.titles[view.title_key or ""][lang]
    # a title may carry what the fact is about (IA-5: the invoice); a missing word leaves the place empty, never a stray brace
    return text.format_map(defaultdict(str, {name: str(value) for name, value in view.params.items()})) if "{" in text else text


def _when(view: ReminderView, lang: str, texts: Texts) -> str:
    if view.lead_days <= 0 or view.event_on is None:
        return texts.frame["today"][lang]
    return f"{texts.frame['in_days'][lang].format(n=view.lead_days)} ({_date(view.event_on)})"


def compose_messages(
    views: Iterable[ReminderView], *, lang: str, now: datetime, base_url: str = "", tz: tzinfo = DEFAULT_TIMEZONE
) -> list[Message]:
    """The messages for the reminders that are due now, in the order they are sent: the digest first, then the rest by time."""
    lang = lang if lang in LANGUAGES else "pl"
    texts = load_texts()
    button = texts.frame["button"][lang]
    late = texts.frame["late"][lang]
    ordered = sorted(views, key=lambda v: (v.send_at, str(v.id)))
    digest = [v for v in ordered if v.origin == "AUTO" and v.event_on is not None]
    in_digest = {v.id for v in digest}
    breaks: dict[tuple[uuid.UUID | None, uuid.UUID | None, str], list[ReminderView]] = {}
    singles: list[ReminderView] = []
    for view in ordered:
        if view.id in in_digest:
            continue
        if view.origin == "AUTO" and view.kind in BREAK_KINDS:
            breaks.setdefault((view.project_id, view.room_id, view.kind), []).append(view)
        else:
            singles.append(view)

    messages: list[Message] = []
    if digest:
        messages.append(_digest(digest, lang=lang, now=now, tz=tz, texts=texts, base_url=base_url, button=button))
    for group in breaks.values():
        messages.append(_break_group(group, lang=lang, now=now, texts=texts, base_url=base_url, button=button, late=late))
    for view in singles:
        lines = [_title(view, lang, texts) + (f" {late}" if lateness(view.send_at, now) == LATE else "")]
        if _context(view):
            lines.append(_context(view))
        messages.append(Message((view.id,), "\n".join(lines), _open_url(base_url, view.project_id), button))
    return messages


def _digest(items: list[ReminderView], *, lang: str, now: datetime, tz: tzinfo, texts: Texts, base_url: str, button: str) -> Message:
    items = sorted(items, key=lambda v: (v.lead_days, v.project_name or "", v.kind, v.ref, str(v.id)))
    shown, hidden = items[:DIGEST_LIMIT], len(items) - DIGEST_LIMIT
    lines = [texts.frame["digest_title"][lang], _date(now.astimezone(tz).date()), ""]
    for view in shown:
        owner = f"{view.project_name} — " if view.project_name else ""
        lines.append(f"• {owner}{_title(view, lang, texts)}, {_when(view, lang, texts)}")
    if hidden > 0:
        lines.append(texts.frame["more"][lang].format(n=hidden))
    projects = {v.project_id for v in items}
    return Message(tuple(v.id for v in items), "\n".join(lines), _open_url(base_url, projects.pop() if len(projects) == 1 else None), button)


def _break_group(group: list[ReminderView], *, lang: str, now: datetime, texts: Texts, base_url: str, button: str, late: str) -> Message:
    first = group[0]
    suffix = f" {late}" if any(lateness(v.send_at, now) == LATE for v in group) else ""
    lines = [_title(first, lang, texts) + suffix]
    if len(group) == 1:
        if _context(first):
            lines.append(_context(first))
        if isinstance(first.params.get("hours"), int):
            lines.append(texts.frame["break_hours"][lang].format(n=first.params["hours"]))
    else:  # the breaks of several surfaces of one room that end together
        lines.append(" · ".join(part for part in (first.project_name, first.room_name) if part))
        lines.append(texts.frame["surfaces"][lang].format(n=len(group)) + ": " + ", ".join(sorted(v.surface_name for v in group if v.surface_name)))  # sorted: the same text whatever the order they were taken in
    return Message(tuple(v.id for v in group), "\n".join(line for line in lines if line), _open_url(base_url, first.project_id), button)
