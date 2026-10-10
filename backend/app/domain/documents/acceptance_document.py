"""The protocol of acceptance of the work as a document (Stage 16H.2): final or partial.

What it prints is data, never prose written by the code: who was present -- or that the customer did not come after two notifications --,
the rooms and surfaces in scope with the standard of each and the state of its planned works (the execution of Stage 13), the conditions
of the assessment of each standard and the instruments used (both the catalogue's), the list of remarks with their class and their deadline,
the **derived** result, the amounts and the instructions handed over. The consequences of a result stay in the contract, which the protocol
points at.

Two forms of one builder: **issued** (numbered, frozen from the protocol that the gate has just checked) and the **working version**
(pale watermark, no number, never refuses: whatever is not recorded yet is an empty box or line to fill in by hand on the spot).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.contracts.catalog import ContractCatalog, load_contract_catalog
from app.domain.documents import formatting
from app.domain.documents.contract_document import CheckOption, client_party
from app.domain.documents.estimate_document import object_lines
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.protocols import acceptance as A
from app.domain.protocols.sources import AcceptanceSources

BLANK_REMARK_ROWS = 6
BLANK_SURFACE_ROWS = 4


@dataclass(frozen=True, slots=True)
class Attendee:
    name: str
    role: str | None


@dataclass(frozen=True, slots=True)
class FactRow:
    label: str
    value: str | None  # None = an empty line to write in


@dataclass(frozen=True, slots=True)
class ConditionLine:
    key: str
    text: str


@dataclass(frozen=True, slots=True)
class WorkRow:
    name: str
    status: str  # the printed state of the work


@dataclass(frozen=True, slots=True)
class SurfaceBlock:
    heading: str  # "Salon — Ściana 1"
    standard: str | None
    works: tuple[WorkRow, ...]
    result: str


@dataclass(frozen=True, slots=True)
class RemarkRow:
    number: int
    surface: str
    place: str | None
    description: str | None
    classification: str | None
    deadline: str | None
    photos: str | None  # the first characters of the photos' ids: enough to find them in the application


@dataclass(frozen=True, slots=True)
class ClassLegend:
    name: str
    text: str


@dataclass(frozen=True, slots=True)
class AcceptanceDocument:
    layout: DocumentLayout
    facts: tuple[FactRow, ...]
    absent_text: str | None  # printed instead of the people present when the customer did not come after two notifications
    attendees: tuple[Attendee, ...]
    conditions: tuple[ConditionLine, ...]
    conditions_note: str | None
    instruments: tuple[str, ...]
    surfaces: tuple[SurfaceBlock, ...]
    remarks: tuple[RemarkRow, ...]
    legend: tuple[ClassLegend, ...]
    results: tuple[CheckOption, ...]
    settlement: tuple[FactRow, ...]
    instructions: CheckOption
    notes: str | None
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def _day(value: date | None) -> str | None:
    return formatting.format_date(value) if value else None


def _iso_day(value: str | None) -> str | None:
    return formatting.format_date(date.fromisoformat(value)) if value else None


def _money(value: str | None) -> str | None:
    return formatting.format_money(Decimal(value)) if value else None


def _title(scope: str | None) -> str:
    labels = Labels()
    if scope == "FINAL":
        return labels("acceptance.title.final")
    if scope == "PARTIAL":
        return labels("acceptance.title.partial")
    return labels("acceptance.title.blank")


def title_of(data: dict[str, Any], sources: AcceptanceSources) -> str:
    return _title(A.scope_kind(data, sources.facts))


def build_acceptance_document(
    data: dict[str, Any],
    sources: AcceptanceSources,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> AcceptanceDocument:
    """`data` is the protocol's own entries (an empty dict for a blank form)."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    base = sources.base
    if base.executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a protocol")
    labels, catalog = Labels(), load_contract_catalog()
    state = {**A.empty_state(), **data}
    scope_kind = A.scope_kind(state, sources.facts)
    scope = A.surfaces_in_scope(state, sources.facts)
    rooms = [name for room_id, name, _ in sources.rooms if room_id in set(state["room_ids"])]
    held = None
    if state["held_on"]:
        held = formatting.format_date(state["held_on"]) + (f", {state['held_time']}" if state["held_time"] else "")
    if base.contract is None:
        contract_text = None
    elif base.contract_number:
        contract_text = labels("acceptance.contract_value", n=base.contract.version, number=base.contract_number)
    else:
        contract_text = labels("acceptance.contract_value_short", n=base.contract.version)
    scope_text = None
    if scope_kind == "FINAL":
        scope_text = labels("acceptance.scope.final")
    elif scope_kind == "PARTIAL":
        scope_text = labels("acceptance.scope.partial", rooms=", ".join(rooms))
    absent = bool(state["customer_absent"])
    absent_text = (
        labels("acceptance.absent", first=_day(state["notified_on"]) or "……………", second=_day(state["renotified_on"]) or "……………")
        if absent else None
    )
    work_names = {
        "COMPLETED": labels("acceptance.work.completed"),
        "IN_PROGRESS": labels("acceptance.work.in_progress"),
        "NOT_STARTED": labels("acceptance.work.not_started"),
    }
    class_names = {"REMOVABLE": labels("acceptance.class.removable"), "SIGNIFICANT": labels("acceptance.class.significant")}
    result_names = {
        A.ACCEPTED: labels("acceptance.result.accepted"),
        A.WITH_REMARKS: labels("acceptance.result.with_remarks"),
        A.NOT_ACCEPTED: labels("acceptance.result.not_accepted"),
    }
    surface_results = {f.id: A.surface_result(f, state["surfaces"].get(f.id)) for f in scope}
    blocks = tuple(
        SurfaceBlock(
            heading=f"{f.room_name} — {f.name}", standard=f.quality_target,
            works=tuple(WorkRow(w.name, work_names[w.status]) for w in f.works), result=result_names[surface_results[f.id]],
        )
        for f in scope
    )
    remarks: list[RemarkRow] = []
    for f in scope:
        photos = {p.id: p for p in sources.defect_photos.get(f.id, [])}
        for remark in A.ordered_remarks(state["surfaces"].get(f.id)):
            remarks.append(RemarkRow(
                len(remarks) + 1, f"{f.room_name} — {f.name}", remark["place"], remark["description"], class_names[remark["classification"]],
                _iso_day(remark.get("deadline")), ", ".join(pid[:8] for pid in remark.get("photo_ids") or [] if pid in photos) or None,
            ))
    if working and not blocks:
        blocks = tuple(SurfaceBlock("", None, (), "") for _ in range(BLANK_SURFACE_ROWS))
    if working and not remarks:
        remarks = [RemarkRow(n, "", None, None, None, None, None) for n in range(1, BLANK_REMARK_ROWS + 1)]
    overall = A.overall_result(list(surface_results.values()))
    instruments = {i.key: i.text_pl for i in catalog.instruments.items}
    executor = party_from_executor_profile(base.executor) if base.executor is not None else None
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=_title(scope_kind), issued_on=issued_on, number=number,
            place=(base.executor.city if base.executor is not None else None) or None, sequence=sequence,
        ),
        executor=executor,
        client=client_party(base.client),
        signatures=True,
        draft=working,
        light_watermark=working,
    )
    return AcceptanceDocument(
        layout=layout,
        facts=(
            FactRow(labels("acceptance.object"), ", ".join((base.project.name, *object_lines(base.project)))),
            FactRow(labels("acceptance.scope"), scope_text),
            FactRow(labels("acceptance.when"), held),
            FactRow(labels("acceptance.contract"), contract_text),
        ),
        absent_text=absent_text,
        attendees=tuple(Attendee(a["name"], a.get("role")) for a in state["attendees"]),
        conditions=tuple(ConditionLine(c["key"], c["text_pl"]) for c in A.conditions(state, sources.facts, catalog)),
        conditions_note=state["conditions_note"],
        instruments=tuple(instruments[k] for k in state["instrument_keys"] if k in instruments),
        surfaces=blocks,
        remarks=tuple(remarks),
        legend=_legend(catalog, class_names),
        results=tuple(CheckOption(result_names[r], r == overall) for r in (A.ACCEPTED, A.WITH_REMARKS, A.NOT_ACCEPTED)),
        settlement=(
            FactRow(labels("acceptance.amount_due"), _money(state["amount_due"])),
            FactRow(labels("acceptance.amount_retained"), _money(state["amount_retained"])),
            FactRow(labels("acceptance.batches"), state["batches"]),
        ),
        instructions=CheckOption(labels("acceptance.instructions"), bool(state["instructions_given"])),
        notes=state["notes"],
        working=working,
    )


def _legend(catalog: ContractCatalog, class_names: dict[str, str]) -> tuple[ClassLegend, ...]:
    return tuple(ClassLegend(class_names[c.key], c.text_pl) for c in catalog.defects.items)


def render_acceptance_html(document: AcceptanceDocument) -> str:
    return render_html(get_template(DocumentKind.FINAL_PROTOCOL), document.context())


def snapshot_of(data: dict[str, Any], sources: AcceptanceSources, document: AcceptanceDocument) -> dict[str, Any]:
    """The frozen content of an issued protocol (JSON): what a dispute needs without re-reading live data."""
    state = {**A.empty_state(), **data}
    contract, catalog = sources.base.contract, load_contract_catalog()
    scope = A.surfaces_in_scope(state, sources.facts)
    held_on, notified_on, renotified_on = state["held_on"], state["notified_on"], state["renotified_on"]
    surfaces = []
    for f in scope:
        entry = state["surfaces"].get(f.id) or {}
        photos = {p.id: p for p in sources.defect_photos.get(f.id, [])}
        surfaces.append({
            "id": f.id, "name": f.name, "room_id": f.room_id, "room_name": f.room_name, "surface_type": f.surface_type,
            "quality_target": f.quality_target, "works": [{"name": w.name, "status": w.status} for w in f.works],
            "result": A.surface_result(f, entry),
            "remarks": [
                {
                    "id": r["id"], "place": r["place"], "description": r["description"], "classification": r["classification"],
                    "deadline": r.get("deadline"),
                    "photos": [
                        {"id": pid, "caption": photos[pid].caption, "added_at": photos[pid].created_at.isoformat()}
                        for pid in r.get("photo_ids") or [] if pid in photos
                    ],
                }
                for r in A.ordered_remarks(entry)
            ],
        })
    return {
        "template_version": get_template(DocumentKind.FINAL_PROTOCOL).version,
        "scope_kind": A.scope_kind(state, sources.facts),
        "result": A.overall_result([s["result"] for s in surfaces]),
        "held_on": held_on.isoformat() if held_on else None,
        "held_time": state["held_time"],
        "customer_absent": bool(state["customer_absent"]),
        "notified_on": notified_on.isoformat() if notified_on else None,
        "renotified_on": renotified_on.isoformat() if renotified_on else None,
        "attendees": list(state["attendees"]),
        "rooms": [{"id": room_id, "name": name} for room_id, name, _ in sources.rooms if room_id in set(state["room_ids"])],
        "conditions": [c for c in A.conditions(state, sources.facts, catalog)],
        "conditions_note": state["conditions_note"],
        "instrument_keys": list(state["instrument_keys"]),
        "surfaces": surfaces,
        "batches": state["batches"],
        "instructions_given": bool(state["instructions_given"]),
        "amount_due": state["amount_due"],
        "amount_retained": state["amount_retained"],
        "notes": state["notes"],
        "contract": (
            {"id": str(contract.id), "version": contract.version, "status": contract.status, "number": sources.base.contract_number}
            if contract is not None else None
        ),
        "client": document.layout.client.name if document.layout.client else None,
        "executor": document.layout.executor.name if document.layout.executor else None,
    }
