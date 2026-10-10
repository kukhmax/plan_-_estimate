"""The protocol of acceptance of concealed works as a document (Stage 16G).

What it prints is data, never prose written by the code: the day, who was present -- or that the customer did not come after being
notified on a given day --, the room and surface, the kind of work (the catalogue's name), the material and its batch, the photos
that are the evidence (with the time they were taken and their caption), the result, the remarks and the consent to cover. The
words are only the names of things; the consequences (a one-sided protocol, the work going on) stay in the contract, which the
protocol points at.

Two forms of one builder: **issued** (numbered, frozen from the protocol that the gate has just checked) and the **working version**
(pale watermark, no number, never refuses: whatever is not recorded yet is an empty box or line to fill in by hand on the spot).
"""

from dataclasses import dataclass
from datetime import date, datetime
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
from app.domain.protocols.concealed import COVER_CONSENTS, RESULTS
from app.domain.protocols.sources import ConcealedSources

BLANK_PHOTO_ROWS = 5


@dataclass(frozen=True, slots=True)
class Attendee:
    name: str
    role: str | None


@dataclass(frozen=True, slots=True)
class PhotoLine:
    number: int
    taken: str | None
    caption: str | None
    ref: str | None  # the first characters of the photo's id: enough to find it in the application


@dataclass(frozen=True, slots=True)
class FactRow:
    label: str
    value: str | None  # None = an empty line to write in


@dataclass(frozen=True, slots=True)
class ConcealedWorksDocument:
    layout: DocumentLayout
    facts: tuple[FactRow, ...]
    absent_text: str | None  # the sentence printed instead of the people present when the customer did not come
    attendees: tuple[Attendee, ...]
    photos: tuple[PhotoLine, ...]
    results: tuple[CheckOption, ...]
    remarks: str | None
    consents: tuple[CheckOption, ...]
    consent_note: str | None  # printed instead of the boxes of the consent when the protocol is one-sided
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def _day(value: date | None) -> str | None:
    return formatting.format_date(value) if value else None


def _taken(captured_at: datetime | None, created_at: datetime) -> str:
    if captured_at is not None:  # the camera's own clock: printed as it is, it carries no zone
        return captured_at.strftime("%d.%m.%Y %H:%M")
    return formatting.format_datetime(created_at)


def build_concealed_document(
    data: dict[str, Any],
    sources: ConcealedSources,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> ConcealedWorksDocument:
    """`data` is the protocol's own entries (an empty dict for a blank form)."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    base = sources.base
    if base.executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a protocol")
    labels, catalog = Labels(), load_contract_catalog()
    surface = sources.surfaces.get(data.get("surface_id") or "")
    kind = next((k for k in catalog.work_kinds.items if k.key == data.get("work_kind")), None)
    work = " — ".join(part for part in (kind.text_pl if kind else None, data.get("work_note")) if part) or None
    held_on = data.get("held_on")
    held = None
    if held_on:
        held = formatting.format_date(held_on) + (f", {data['held_time']}" if data.get("held_time") else "")
    if base.contract is None:
        contract_text = None
    elif base.contract_number:
        contract_text = labels("concealed.contract_value", n=base.contract.version, number=base.contract_number)
    else:
        contract_text = labels("concealed.contract_value_short", n=base.contract.version)
    absent = bool(data.get("customer_absent"))
    absent_text = labels("concealed.absent", day=_day(data.get("notified_on")) or "……………") if absent else None
    chosen = set(data.get("photo_ids") or [])
    photos = tuple(
        PhotoLine(n, _taken(p.captured_at, p.created_at), p.caption, p.id[:8])
        for n, p in enumerate((p for p in sources.photos.get(data.get("surface_id") or "", []) if p.id in chosen), start=1)
    )
    if working and not photos:
        photos = tuple(PhotoLine(n, None, None, None) for n in range(1, BLANK_PHOTO_ROWS + 1))
    result_names = {"ACCEPTED": labels("concealed.result.accepted"), "WITH_REMARKS": labels("concealed.result.with_remarks")}
    consent_names = {"GIVEN": labels("concealed.consent.given"), "WITHHELD": labels("concealed.consent.withheld")}
    executor = party_from_executor_profile(base.executor) if base.executor is not None else None
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("concealed.title"), issued_on=issued_on, number=number,
            place=(base.executor.city if base.executor is not None else None) or None, sequence=sequence,
        ),
        executor=executor,
        client=client_party(base.client),
        signatures=True,
        draft=working,
        light_watermark=working,
    )
    return ConcealedWorksDocument(
        layout=layout,
        facts=(
            FactRow(labels("concealed.object"), ", ".join((base.project.name, *object_lines(base.project)))),
            FactRow(labels("concealed.room"), surface.room_name if surface else None),
            FactRow(labels("concealed.surface"), surface.name if surface else None),
            FactRow(labels("concealed.work"), work),
            FactRow(labels("concealed.material"), data.get("material")),
            FactRow(labels("concealed.batch"), data.get("batch")),
            FactRow(labels("concealed.when"), held),
            FactRow(labels("concealed.contract"), contract_text),
        ),
        absent_text=absent_text,
        attendees=tuple(Attendee(a["name"], a.get("role")) for a in data.get("attendees") or []),
        photos=photos,
        results=tuple(CheckOption(result_names[r], r == data.get("result")) for r in RESULTS),
        remarks=data.get("remarks"),
        consents=tuple(CheckOption(consent_names[c], c == data.get("cover_consent")) for c in COVER_CONSENTS),
        consent_note=labels("concealed.consent.one_sided") if absent else None,
        working=working,
    )


def render_concealed_html(document: ConcealedWorksDocument) -> str:
    return render_html(get_template(DocumentKind.CONCEALED_WORKS_PROTOCOL), document.context())


def snapshot_of(data: dict[str, Any], sources: ConcealedSources, document: ConcealedWorksDocument) -> dict[str, Any]:
    """The frozen content of an issued protocol (JSON): what a dispute needs without re-reading live data."""
    contract, surface = sources.base.contract, sources.surfaces.get(data.get("surface_id") or "")
    held_on, notified_on = data.get("held_on"), data.get("notified_on")
    return {
        "template_version": get_template(DocumentKind.CONCEALED_WORKS_PROTOCOL).version,
        "held_on": held_on.isoformat() if held_on else None,
        "held_time": data.get("held_time"),
        "customer_absent": bool(data.get("customer_absent")),
        "notified_on": notified_on.isoformat() if notified_on else None,
        "attendees": list(data.get("attendees") or []),
        "surface": {"id": surface.id, "name": surface.name, "room_id": surface.room_id, "room_name": surface.room_name} if surface else None,
        "work_kind": data.get("work_kind"),
        "work_note": data.get("work_note"),
        "material": data.get("material"),
        "batch": data.get("batch"),
        "photos": [
            {"id": p.id, "caption": p.caption, "captured_at": p.captured_at.isoformat() if p.captured_at else None, "added_at": p.created_at.isoformat()}
            for p in sources.photos.get(data.get("surface_id") or "", []) if p.id in set(data.get("photo_ids") or [])
        ],
        "result": data.get("result"),
        "remarks": data.get("remarks"),
        "cover_consent": data.get("cover_consent"),
        "contract": (
            {"id": str(contract.id), "version": contract.version, "status": contract.status, "number": sources.base.contract_number}
            if contract is not None else None
        ),
        "client": document.layout.client.name if document.layout.client else None,
        "executor": document.layout.executor.name if document.layout.executor else None,
    }
