"""The protocol of handing over the premises as a document (Stage 16F.2).

What it prints is data, never prose written by the code: the day and the people present, and -- room by room -- the requirements of
annex 4 of the contract with the numbers the contract asks for, what was found (a state, a measured value, a note), the existing
damages and the decision. The wording is only the names of things and of the four states; the legal consequences stay in the
contract (the protocol points at its sections, which keep their numbers whatever the answers are).

Two forms of one builder: **issued** (numbered, frozen from the protocol that the gate has just checked) and the **working version**
(pale watermark, no number, never refuses: whatever is not recorded yet is an empty box or line, so the owner can print it, take it
to the premises and fill it in by hand). A working version of an open draft prints what is already recorded.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.contracts.catalog import ContractCatalog, load_contract_catalog
from app.domain.documents import formatting
from app.domain.documents.contract_document import CheckOption, _requirement_value, _unit_text, client_party
from app.domain.documents.estimate_document import object_lines
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.protocols.handover import DECISIONS, STATES
from app.domain.protocols.sources import HandoverSources

BLANK_ROOMS = 3  # a blank form with no rooms yet: room blocks to name by hand


@dataclass(frozen=True, slots=True)
class RequirementLine:
    text: str
    required: str | None  # what the contract asks for; None = "—"
    states: tuple[CheckOption, ...]
    found: str | None  # the measured value as printed
    note: str | None


@dataclass(frozen=True, slots=True)
class RoomBlock:
    name: str | None  # None = a blank block to name by hand
    lines: tuple[RequirementLine, ...]
    damages: str | None
    decisions: tuple[CheckOption, ...]


@dataclass(frozen=True, slots=True)
class Attendee:
    name: str
    role: str | None


@dataclass(frozen=True, slots=True)
class HandoverDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    held: str | None  # the day (and the time) as printed
    contract_text: str | None
    attendees: tuple[Attendee, ...]
    rooms: tuple[RoomBlock, ...]
    summary: tuple[tuple[str, str | None], ...]  # (room, the decision as printed) of the rooms that have one
    meters: str | None
    notes: str | None
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def _state_options(state: str | None) -> tuple[CheckOption, ...]:
    labels = Labels()
    names = {
        "YES": labels("handover.state.yes"), "NO": labels("handover.state.no"),
        "CONDITIONAL": labels("handover.state.conditional"), "NOT_APPLICABLE": labels("handover.state.not_applicable"),
    }
    return tuple(CheckOption(names[s], s == state) for s in STATES)


def _decision_options(decision: str | None) -> tuple[CheckOption, ...]:
    labels = Labels()
    names = {
        "HANDED_OVER": labels("handover.decision.handed_over"), "CONDITIONAL": labels("handover.decision.conditional"),
        "NOT_HANDED_OVER": labels("handover.decision.not_handed_over"),
    }
    return tuple(CheckOption(names[d], d == decision) for d in DECISIONS)


def _lines(entries: dict[str, Any], required: dict[str, Any], catalog: ContractCatalog) -> tuple[RequirementLine, ...]:
    lines = []
    for requirement in catalog.requirements.items:
        entry = entries.get(requirement.key) or {}
        unit = _unit_text(requirement.unit)
        lines.append(RequirementLine(
            text=requirement.text_pl,
            required=_requirement_value(requirement.value_kind, unit, required.get(requirement.key)),
            states=_state_options(entry.get("state")),
            found=None if requirement.value_kind == "YES_NO" else _requirement_value(requirement.value_kind, unit, entry.get("value")),
            note=entry.get("note"),
        ))
    return tuple(lines)


def _contract_text(sources: HandoverSources) -> str | None:
    if sources.contract is None:
        return None
    labels = Labels()
    if sources.contract_number:
        return labels("handover.contract_value", n=sources.contract.version, number=sources.contract_number)
    return labels("handover.contract_value_short", n=sources.contract.version)


def build_handover_document(
    data: dict[str, Any],
    sources: HandoverSources,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> HandoverDocument:
    """`data` is the protocol's own entries (an empty dict for a blank form)."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if sources.executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a protocol")
    catalog, labels = load_contract_catalog(), Labels()
    required = sources.required_values
    recorded = data.get("rooms") or {}
    blocks: list[RoomBlock] = []
    summary: list[tuple[str, str | None]] = []
    for room_id, name, archived in sources.rooms:
        if room_id not in recorded and (not working or archived):  # an archived room is printed only if it was recorded
            continue
        room = recorded.get(room_id) or {}
        decision = room.get("decision")
        blocks.append(RoomBlock(name, _lines(room.get("requirements") or {}, required, catalog), room.get("damages"), _decision_options(decision)))
        if decision:
            summary.append((name, next(o.label for o in _decision_options(decision) if o.checked)))
    if working and not blocks:
        blocks = [RoomBlock(None, _lines({}, required, catalog), None, _decision_options(None))] * BLANK_ROOMS
    held_on = data.get("held_on")
    held = None
    if held_on:
        held = formatting.format_date(held_on) + (f", {data['held_time']}" if data.get("held_time") else "")
    executor = party_from_executor_profile(sources.executor) if sources.executor is not None else None
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("handover.title"), issued_on=issued_on, number=number,
            place=(sources.executor.city if sources.executor is not None else None) or None, sequence=sequence,
        ),
        executor=executor,
        client=client_party(sources.client),
        signatures=True,
        draft=working,
        light_watermark=working,
    )
    return HandoverDocument(
        layout=layout,
        object_name=sources.project.name,
        object_lines=object_lines(sources.project),
        held=held,
        contract_text=_contract_text(sources),
        attendees=tuple(Attendee(a["name"], a.get("role")) for a in data.get("attendees") or []),
        rooms=tuple(blocks),
        summary=tuple(summary),
        meters=data.get("meters"),
        notes=data.get("notes"),
        working=working,
    )


def render_handover_html(document: HandoverDocument) -> str:
    return render_html(get_template(DocumentKind.HANDOVER_PROTOCOL), document.context())


def snapshot_of(data: dict[str, Any], sources: HandoverSources, document: HandoverDocument) -> dict[str, Any]:
    """The frozen findings of an issued protocol (JSON): what a dispute needs without re-reading live data."""
    held_on = data.get("held_on")
    contract = sources.contract
    return {
        "template_version": get_template(DocumentKind.HANDOVER_PROTOCOL).version,
        "held_on": held_on.isoformat() if held_on else None,
        "held_time": data.get("held_time"),
        "attendees": list(data.get("attendees") or []),
        "rooms": {rid: room for rid, room in (data.get("rooms") or {}).items()},
        "room_names": {rid: name for rid, name, _ in sources.rooms if rid in (data.get("rooms") or {})},
        "meters": data.get("meters"),
        "notes": data.get("notes"),
        "contract": (
            {"id": str(contract.id), "version": contract.version, "status": contract.status, "number": sources.contract_number}
            if contract is not None else None
        ),
        "required_values": sources.required_values,
        "client": document.layout.client.name if document.layout.client else None,
        "executor": document.layout.executor.name if document.layout.executor else None,
    }
