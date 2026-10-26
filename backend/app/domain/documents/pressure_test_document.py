"""The protocol of a pressure test as a document (V2-12b, "Protokół próby ciśnieniowej").

What it prints is data, never prose written by the code: the object, the system and the place tested, the medium, the test pressure, the time held and the drop of the pressure, the day
and who was present -- or that the customer did not come after being notified on a given day --, the photos of the manometer (with the time they were taken and their caption), the
result the owner chose and the remarks, and the signature lines. The words are only the names of things; whether the test is positive is the owner's word, no norm is printed.

Two forms of one builder, like the protocol of concealed works: **issued** (numbered, frozen from the protocol the gate has just checked) and the **working version** (pale watermark,
no number, never refuses: whatever is not recorded yet is an empty line to fill in by hand on the spot).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.domain.documents import formatting
from app.domain.documents.concealed_works_document import Attendee, FactRow, PhotoLine
from app.domain.documents.contract_document import CheckOption, client_party
from app.domain.documents.estimate_document import object_lines
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.protocols.pressure import RESULTS
from app.domain.protocols.sources import PressureSources

BLANK_PHOTO_ROWS = 3
NBSP = " "


@dataclass(frozen=True, slots=True)
class PressureTestDocument:
    layout: DocumentLayout
    facts: tuple[FactRow, ...]
    absent_text: str | None
    attendees: tuple[Attendee, ...]
    photos: tuple[PhotoLine, ...]
    results: tuple[CheckOption, ...]
    remarks: str | None
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def _day(value: date | None) -> str | None:
    return formatting.format_date(value) if value else None


def _taken(captured_at: datetime | None, created_at: datetime) -> str:
    if captured_at is not None:  # the camera's own clock: printed as it is, it carries no zone
        return captured_at.strftime("%d.%m.%Y %H:%M")
    return formatting.format_datetime(created_at)


def bar_text(value: Decimal | None) -> str | None:
    """A pressure as printed: "6" or "2,5" bar, no needless zeros, a comma."""
    if value is None:
        return None
    text = format(Decimal(value).normalize(), "f").replace(".", ",")
    return f"{text}{NBSP}bar"


def build_pressure_document(
    data: dict[str, Any],
    sources: PressureSources,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> PressureTestDocument:
    """`data` is the protocol's own entries (an empty dict for a blank form)."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    base = sources.base
    if base.executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a protocol")
    labels = Labels()
    system_names = {
        "COLD_WATER": labels("pressure.system.cold_water"), "HOT_WATER": labels("pressure.system.hot_water"), "HEATING": labels("pressure.system.heating"),
        "GAS": labels("pressure.system.gas"), "SEWER": labels("pressure.system.sewer"),
    }
    medium_names = {"WATER": labels("pressure.medium.water"), "AIR": labels("pressure.medium.air")}
    result_names = {"POSITIVE": labels("pressure.result.positive"), "NEGATIVE": labels("pressure.result.negative")}
    system = system_names.get(data.get("system") or "")
    installation = " — ".join(part for part in (system, data.get("section")) if part) or None
    held_on = data.get("held_on")
    held = None
    if held_on:
        held = formatting.format_date(held_on) + (f", {data['held_time']}" if data.get("held_time") else "")
    duration = data.get("duration_min")
    absent = bool(data.get("customer_absent"))
    absent_text = labels("pressure.absent", day=_day(data.get("notified_on")) or "……………") if absent else None
    chosen = list(data.get("photo_ids") or [])
    photos = tuple(
        PhotoLine(n, _taken(sources.photos[p].captured_at, sources.photos[p].created_at), " · ".join(x for x in (sources.photos[p].caption, sources.photos[p].place) if x) or None, None)
        for n, p in enumerate((p for p in chosen if p in sources.photos), start=1)
    )
    if working and not photos:
        photos = tuple(PhotoLine(n, None, None, None) for n in range(1, BLANK_PHOTO_ROWS + 1))
    executor = party_from_executor_profile(base.executor) if base.executor is not None else None
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("pressure.title"), issued_on=issued_on, number=number,
            place=(base.executor.city if base.executor is not None else None) or None, sequence=sequence,
        ),
        executor=executor,
        client=client_party(base.client),
        signatures=True,
        draft=working,
        light_watermark=working,
    )
    return PressureTestDocument(
        layout=layout,
        facts=(
            FactRow(labels("pressure.object"), ", ".join((base.project.name, *object_lines(base.project)))),
            FactRow(labels("pressure.installation"), installation),
            FactRow(labels("pressure.medium"), medium_names.get(data.get("medium") or "")),
            FactRow(labels("pressure.test_pressure"), bar_text(data.get("test_pressure_bar"))),
            FactRow(labels("pressure.duration"), f"{duration}{NBSP}min" if duration is not None else None),
            FactRow(labels("pressure.drop"), bar_text(data.get("pressure_drop_bar"))),
            FactRow(labels("pressure.when"), held),
        ),
        absent_text=absent_text,
        attendees=tuple(Attendee(a["name"], a.get("role")) for a in data.get("attendees") or []),
        photos=photos,
        results=tuple(CheckOption(result_names[r], r == data.get("result")) for r in RESULTS),
        remarks=data.get("remarks"),
        working=working,
    )


def render_pressure_html(document: PressureTestDocument) -> str:
    return render_html(get_template(DocumentKind.PRESSURE_TEST_PROTOCOL), document.context())


def snapshot_of(data: dict[str, Any], sources: PressureSources, document: PressureTestDocument) -> dict[str, Any]:
    """The frozen content of an issued protocol (JSON): what a dispute needs without re-reading live data."""
    held_on, notified_on = data.get("held_on"), data.get("notified_on")
    pressure, drop = data.get("test_pressure_bar"), data.get("pressure_drop_bar")
    return {
        "template_version": get_template(DocumentKind.PRESSURE_TEST_PROTOCOL).version,
        "held_on": held_on.isoformat() if held_on else None,
        "held_time": data.get("held_time"),
        "customer_absent": bool(data.get("customer_absent")),
        "notified_on": notified_on.isoformat() if notified_on else None,
        "attendees": list(data.get("attendees") or []),
        "system": data.get("system"),
        "section": data.get("section"),
        "medium": data.get("medium"),
        "test_pressure_bar": str(pressure) if pressure is not None else None,
        "duration_min": data.get("duration_min"),
        "pressure_drop_bar": str(drop) if drop is not None else None,
        "photos": [
            {
                "id": p, "caption": sources.photos[p].caption, "place": sources.photos[p].place,
                "captured_at": sources.photos[p].captured_at.isoformat() if sources.photos[p].captured_at else None,
                "added_at": sources.photos[p].created_at.isoformat(),
            }
            for p in data.get("photo_ids") or [] if p in sources.photos
        ],
        "result": data.get("result"),
        "remarks": data.get("remarks"),
        "client": document.layout.client.name if document.layout.client else None,
        "executor": document.layout.executor.name if document.layout.executor else None,
    }
