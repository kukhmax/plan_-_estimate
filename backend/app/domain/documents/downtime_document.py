"""The notice and the protocol of downtime on the customer's side as documents (Stage 16I.3; annex 8 of the contract).

What they print is data, never prose written by the code: the cause (the catalogue's name), the rooms, the photos with the time they were
taken, what the contractor needs and until when; and, in the protocol, the notice it follows, the days with the answer whether other work
could be done, the rate and the sum for readiness derived from the frozen contract, the effect on the deadline in the owner's words, the
people present or the refusal to sign. What the sum or the days mean legally stays in the contract (`§ 10`), which the pages point at.

Two builders, each in two forms: **issued** (numbered, frozen from the episode that the gate has just checked) and the **working version**
(pale watermark, no number, never refuses: whatever is not recorded yet is an empty box or line to fill in by hand on the spot).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.documents import formatting
from app.domain.documents.contract_document import CheckOption, client_party
from app.domain.documents.estimate_document import object_lines
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.protocols import downtime as D
from app.domain.protocols.sources import DowntimeSources

BLANK_PHOTO_ROWS = 4
BLANK_DAY_ROWS = 5


@dataclass(frozen=True, slots=True)
class Attendee:
    name: str
    role: str | None


@dataclass(frozen=True, slots=True)
class FactRow:
    label: str
    value: str | None  # None = an empty line to write in


@dataclass(frozen=True, slots=True)
class PhotoLine:
    number: int
    taken: str | None
    caption: str | None
    place: str | None
    ref: str | None  # the first characters of the photo's id: enough to find it in the application


@dataclass(frozen=True, slots=True)
class DayRow:
    number: int
    day: str | None
    weekday: str | None
    other_work: str | None  # "Tak" / "Nie"
    note: str | None


@dataclass(frozen=True, slots=True)
class DowntimeNoticeDocument:
    layout: DocumentLayout
    facts: tuple[FactRow, ...]
    causes: tuple[CheckOption, ...]
    cause_note: str | None
    photos: tuple[PhotoLine, ...]
    need: tuple[FactRow, ...]
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


@dataclass(frozen=True, slots=True)
class DowntimeProtocolDocument:
    layout: DocumentLayout
    facts: tuple[FactRow, ...]
    attendees: tuple[Attendee, ...]
    days: tuple[DayRow, ...]
    totals: tuple[FactRow, ...]
    cap_note: str | None
    deadline_note: str | None
    refusal: CheckOption
    notes: str | None
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def _day(value: date | None) -> str | None:
    return formatting.format_date(value) if value else None


def _stamp(day: date | None, time: str | None) -> str | None:
    return None if not day else formatting.format_date(day) + (f", {time}" if time else "")


def _money(value: Decimal | None) -> str | None:
    return formatting.format_money(value) if value is not None else None


def _taken(captured_at: datetime | None, created_at: datetime) -> str:
    if captured_at is not None:  # the camera's own clock: printed as it is, it carries no zone
        return captured_at.strftime("%d.%m.%Y %H:%M")
    return formatting.format_datetime(created_at)


def _check(working: bool, sources: DowntimeSources) -> None:
    if sources.base.executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a document")


def _layout(title: str, sources: DowntimeSources, *, working: bool, issued_on: date, number: str | None, sequence: int | None, signatures: bool) -> DocumentLayout:
    base = sources.base
    return DocumentLayout(
        meta=DocumentMeta(
            title=title, issued_on=issued_on, number=number,
            place=(base.executor.city if base.executor is not None else None) or None, sequence=sequence,
        ),
        executor=party_from_executor_profile(base.executor) if base.executor is not None else None,
        client=client_party(base.client),
        signatures=signatures,
        draft=working,
        light_watermark=working,
    )


def _contract_text(sources: DowntimeSources, labels: Labels) -> str | None:
    base = sources.base
    if base.contract is None:
        return None
    if base.contract_number:
        return labels("downtime.contract_value", n=base.contract.version, number=base.contract_number)
    return labels("downtime.contract_value_short", n=base.contract.version)


def _rooms_text(data: dict[str, Any], sources: DowntimeSources, labels: Labels) -> str:
    names = [name for room_id, name in sources.rooms if room_id in set(data["room_ids"])]
    return ", ".join(names) if names else labels("downtime.rooms_all")


def build_notice_document(
    data: dict[str, Any], sources: DowntimeSources, *, working: bool, issued_on: date, number: str | None = None, sequence: int | None = None,
) -> DowntimeNoticeDocument:
    """`data` is the episode's own entries (an empty dict for a blank form)."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    _check(working, sources)
    labels, catalog = Labels(), load_contract_catalog()
    state = {**D.empty_state(), **data}
    chosen = set(state["photo_ids"])
    photos = tuple(
        PhotoLine(n, _taken(p.captured_at, p.created_at), p.caption, p.room_name, p.id[:8])
        for n, p in enumerate((p for p in sources.photos.values() if p.id in chosen), start=1)
    )
    if working and not photos:
        photos = tuple(PhotoLine(n, None, None, None, None) for n in range(1, BLANK_PHOTO_ROWS + 1))
    return DowntimeNoticeDocument(
        layout=_layout(labels("downtime.notice.title"), sources, working=working, issued_on=issued_on, number=number, sequence=sequence, signatures=False),
        facts=(
            FactRow(labels("downtime.object"), ", ".join((sources.base.project.name, *object_lines(sources.base.project)))),
            FactRow(labels("downtime.rooms"), _rooms_text(state, sources, labels)),
            FactRow(labels("downtime.noticed"), _stamp(state["noticed_on"], state["noticed_time"])),
            FactRow(labels("downtime.channel"), state["notice_channel"]),
            FactRow(labels("downtime.contract"), _contract_text(sources, labels)),
        ),
        causes=tuple(CheckOption(c.text_pl, c.key == state["cause_key"]) for c in catalog.downtime_causes.items),
        cause_note=state["cause_note"],
        photos=photos,
        need=(
            FactRow(labels("downtime.need"), state["need_text"]),
            FactRow(labels("downtime.need_by"), _day(state["need_by"])),
        ),
        working=working,
    )


def build_protocol_document(
    data: dict[str, Any], sources: DowntimeSources, contract_snapshot: dict[str, Any] | None, *, working: bool, issued_on: date,
    notice_number: str | None = None, notice_on: date | None = None, number: str | None = None, sequence: int | None = None,
) -> DowntimeProtocolDocument:
    """`data` is the episode's own entries (an empty dict for a blank form); `contract_snapshot` the frozen conditions of the contract the
    notice was written under."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    _check(working, sources)
    labels, catalog = Labels(), load_contract_catalog()
    state = {**D.empty_state(), **data}
    cause = next((c.text_pl for c in catalog.downtime_causes.items if c.key == state["cause_key"]), None)
    cause_text = " — ".join(part for part in (cause, state["cause_note"]) if part) or None
    notice_text = None
    if notice_number:
        notice_text = labels("downtime.notice_ref", number=notice_number, day=_day(notice_on) or "……………")
    weekdays = (
        labels("downtime.weekday.mon"), labels("downtime.weekday.tue"), labels("downtime.weekday.wed"), labels("downtime.weekday.thu"),
        labels("downtime.weekday.fri"), labels("downtime.weekday.sat"), labels("downtime.weekday.sun"),
    )
    yes, no = labels("downtime.yes"), labels("downtime.no")
    rows = tuple(
        DayRow(n, _day(date.fromisoformat(d["date"])), weekdays[date.fromisoformat(d["date"]).weekday()], yes if d.get("other_work") else no, d.get("note"))
        for n, d in enumerate(state["days"], start=1)
    )
    if working and not rows:
        rows = tuple(DayRow(n, None, None, None, None) for n in range(1, BLANK_DAY_ROWS + 1))
    s = D.settlement(state["days"], contract_snapshot)
    cap_note = labels("downtime.capped", cap=_money(s["cap"])) if s["capped"] else None
    return DowntimeProtocolDocument(
        layout=_layout(labels("downtime.protocol.title"), sources, working=working, issued_on=issued_on, number=number, sequence=sequence, signatures=True),
        facts=(
            FactRow(labels("downtime.object"), ", ".join((sources.base.project.name, *object_lines(sources.base.project)))),
            FactRow(labels("downtime.notice_row"), notice_text),
            FactRow(labels("downtime.cause"), cause_text),
            FactRow(labels("downtime.rooms"), _rooms_text(state, sources, labels)),
            FactRow(labels("downtime.held"), _stamp(state["held_on"], state["held_time"])),
            FactRow(labels("downtime.contract"), _contract_text(sources, labels)),
        ),
        attendees=tuple(Attendee(a["name"], a.get("role")) for a in state["attendees"]),
        days=rows,
        totals=(
            FactRow(labels("downtime.total_days"), str(s["listed"]) if state["days"] else None),
            FactRow(labels("downtime.chargeable_days"), str(s["chargeable"]) if state["days"] else None),
            FactRow(labels("downtime.rate"), _money(s["rate"])),
            FactRow(labels("downtime.amount"), _money(s["payable"]) if state["days"] else None),
        ),
        cap_note=cap_note,
        deadline_note=state["deadline_note"],
        refusal=CheckOption(labels("downtime.refusal"), bool(state["signature_refused"])),
        notes=state["notes"],
        working=working,
    )


def render_notice_html(document: DowntimeNoticeDocument) -> str:
    return render_html(get_template(DocumentKind.DOWNTIME_NOTICE), document.context())


def render_protocol_html(document: DowntimeProtocolDocument) -> str:
    return render_html(get_template(DocumentKind.DOWNTIME_PROTOCOL), document.context())


def _contract_of(sources: DowntimeSources) -> dict[str, Any] | None:
    contract = sources.base.contract
    return (
        {"id": str(contract.id), "version": contract.version, "status": contract.status, "number": sources.base.contract_number}
        if contract is not None else None
    )


def notice_snapshot_of(data: dict[str, Any], sources: DowntimeSources, document: DowntimeNoticeDocument) -> dict[str, Any]:
    """The frozen content of an issued notice (JSON): what a dispute needs without re-reading live data."""
    state = {**D.empty_state(), **data}
    catalog = load_contract_catalog()
    chosen = set(state["photo_ids"])
    return {
        "template_version": get_template(DocumentKind.DOWNTIME_NOTICE).version,
        "cause_key": state["cause_key"],
        "cause_text": next((c.text_pl for c in catalog.downtime_causes.items if c.key == state["cause_key"]), None),
        "cause_note": state["cause_note"],
        "rooms": [{"id": room_id, "name": name} for room_id, name in sources.rooms if room_id in set(state["room_ids"])],
        "noticed_on": state["noticed_on"].isoformat() if state["noticed_on"] else None,
        "noticed_time": state["noticed_time"],
        "notice_channel": state["notice_channel"],
        "photos": [
            {"id": p.id, "caption": p.caption, "room_name": p.room_name, "captured_at": p.captured_at.isoformat() if p.captured_at else None,
             "added_at": p.created_at.isoformat()}
            for p in sources.photos.values() if p.id in chosen
        ],
        "need_text": state["need_text"],
        "need_by": state["need_by"].isoformat() if state["need_by"] else None,
        "contract": _contract_of(sources),
        "client": document.layout.client.name if document.layout.client else None,
        "executor": document.layout.executor.name if document.layout.executor else None,
    }


def protocol_snapshot_of(
    data: dict[str, Any], sources: DowntimeSources, contract_snapshot: dict[str, Any] | None, document: DowntimeProtocolDocument,
    notice_number: str | None, notice_on: date | None,
) -> dict[str, Any]:
    state = {**D.empty_state(), **data}
    s = D.settlement(state["days"], contract_snapshot)
    return {
        "template_version": get_template(DocumentKind.DOWNTIME_PROTOCOL).version,
        "notice": {"number": notice_number, "on": notice_on.isoformat() if notice_on else None},
        "cause_key": state["cause_key"],
        "cause_note": state["cause_note"],
        "days": [dict(d) for d in state["days"]],
        "settlement": {
            "listed": s["listed"], "chargeable": s["chargeable"], "rate": _plain(s["rate"]), "amount": _plain(s["amount"]), "cap": _plain(s["cap"]),
            "capped": s["capped"], "payable": _plain(s["payable"]), "limit_days": s["limit_days"], "limit_exceeded": s["limit_exceeded"],
        },
        "held_on": state["held_on"].isoformat() if state["held_on"] else None,
        "held_time": state["held_time"],
        "attendees": list(state["attendees"]),
        "signature_refused": bool(state["signature_refused"]),
        "deadline_note": state["deadline_note"],
        "notes": state["notes"],
        "contract": _contract_of(sources),
        "client": document.layout.client.name if document.layout.client else None,
        "executor": document.layout.executor.name if document.layout.executor else None,
    }


def _plain(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"
