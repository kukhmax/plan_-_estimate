"""The protocol of information and decisions of the customer as a document (Stage 16I.1; annex 9 of the contract).

What it prints is data, never prose written by the code: for every item the room, what was found (the risk catalogue's text), the
recommendation of the contractor and its price, the risk and its possible consequences in plain language (the catalogue's text), the
decision of the customer and -- when he insists on the work against the recommendation -- what the contractor does. What a decision
means for the guarantee is not said here: the page points at the contract (`§ 16 ust. 3 lit. f`, `§ 17`), which holds the words.

Two forms of one builder: **issued** (numbered, frozen from the protocol that the gate has just checked) and the **working version**
(pale watermark, no number, never refuses: whatever is not recorded yet is an empty box or line to fill in by hand on the spot).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.documents import formatting
from app.domain.documents.contract_document import CheckOption, client_party
from app.domain.documents.estimate_document import object_lines
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.protocols import decision as D
from app.domain.protocols.sources import DecisionSources
from app.domain.services.decision_service import item_texts

BLANK_ITEMS = 3


@dataclass(frozen=True, slots=True)
class Attendee:
    name: str
    role: str | None


@dataclass(frozen=True, slots=True)
class FactRow:
    label: str
    value: str | None  # None = an empty line to write in


@dataclass(frozen=True, slots=True)
class ItemBlock:
    number: int
    title: str | None
    room: str | None
    state: str | None
    recommendation: str | None
    price: str | None
    consequence: str | None
    decisions: tuple[CheckOption, ...]
    actions: tuple[CheckOption, ...] | None  # what the contractor does when the customer insists; None when no demand was made
    effect: str | None  # the pointer to the contract printed for a decision that gives the recommendation up or overrules it
    note: str | None


@dataclass(frozen=True, slots=True)
class DecisionDocument:
    layout: DocumentLayout
    facts: tuple[FactRow, ...]
    attendees: tuple[Attendee, ...]
    items: tuple[ItemBlock, ...]
    declaration: CheckOption
    refusal: CheckOption
    notes: str | None
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def _blank_item(number: int, labels: Labels) -> ItemBlock:
    return ItemBlock(
        number, None, None, None, None, None, None, _decision_boxes(None, None, labels), _action_boxes(None, True, labels), None, None
    )


def _decision_boxes(decision: str | None, order_ref: str | None, labels: Labels) -> tuple[CheckOption, ...]:
    return (
        CheckOption(labels("decision.decision.accepted", ref=order_ref or "……………"), decision == "ACCEPTED"),
        CheckOption(labels("decision.decision.declined"), decision == "DECLINED"),
        CheckOption(labels("decision.decision.insists"), decision == "INSISTS"),
    )


def _action_boxes(action: str | None, show: bool, labels: Labels) -> tuple[CheckOption, ...] | None:
    if not show:
        return None
    return (
        CheckOption(labels("decision.action.perform"), action == "PERFORM"),
        CheckOption(labels("decision.action.refuse"), action == "REFUSE"),
    )


def build_item_blocks(items: list[dict[str, Any]], sources: DecisionSources, labels: Labels) -> tuple[ItemBlock, ...]:
    blocks = []
    for number, item in enumerate(items, start=1):
        texts = item_texts(item, sources)
        decision = item.get("decision")
        price = formatting.format_money(Decimal(texts["price"])) if texts["price"] else None
        blocks.append(ItemBlock(
            number=number, title=texts["title"] or None, room=texts["room_name"], state=texts["state"],
            recommendation=texts["recommendation"] or None, price=price, consequence=texts["consequence"] or None,
            decisions=_decision_boxes(decision, item.get("order_ref"), labels),
            actions=_action_boxes(item.get("executor_action"), decision == "INSISTS", labels),
            effect=labels("decision.effect") if decision in ("DECLINED", "INSISTS") else None, note=item.get("note"),
        ))
    return tuple(blocks)


def build_decision_document(
    data: dict[str, Any],
    sources: DecisionSources,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> DecisionDocument:
    """`data` is the protocol's own entries (an empty dict for a blank form)."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    base = sources.base
    if base.executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a protocol")
    labels = Labels()
    state = {**D.empty_state(), **data}
    held = None
    if state["held_on"]:
        held = formatting.format_date(state["held_on"]) + (f", {state['held_time']}" if state["held_time"] else "")
    if base.contract is None:
        contract_text = None
    elif base.contract_number:
        contract_text = labels("decision.contract_value", n=base.contract.version, number=base.contract_number)
    else:
        contract_text = labels("decision.contract_value_short", n=base.contract.version)
    items = build_item_blocks(state["items"], sources, labels)
    if working and not items:
        items = tuple(_blank_item(n, labels) for n in range(1, BLANK_ITEMS + 1))
    executor = party_from_executor_profile(base.executor) if base.executor is not None else None
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("decision.title"), issued_on=issued_on, number=number,
            place=(base.executor.city if base.executor is not None else None) or None, sequence=sequence,
        ),
        executor=executor,
        client=client_party(base.client),
        signatures=True,
        draft=working,
        light_watermark=working,
    )
    return DecisionDocument(
        layout=layout,
        facts=(
            FactRow(labels("decision.object"), ", ".join((base.project.name, *object_lines(base.project)))),
            FactRow(labels("decision.when"), held),
            FactRow(labels("decision.contract"), contract_text),
        ),
        attendees=tuple(Attendee(a["name"], a.get("role")) for a in state["attendees"]),
        items=items,
        declaration=CheckOption(labels("decision.declaration"), bool(state["understood"])),
        refusal=CheckOption(labels("decision.refusal"), bool(state["signature_refused"])),
        notes=state["notes"],
        working=working,
    )


def render_decision_html(document: DecisionDocument) -> str:
    return render_html(get_template(DocumentKind.DECISION_PROTOCOL), document.context())


def snapshot_of(data: dict[str, Any], sources: DecisionSources, document: DecisionDocument) -> dict[str, Any]:
    """The frozen content of an issued protocol (JSON): what a dispute needs without re-reading live data."""
    state = {**D.empty_state(), **data}
    contract = sources.base.contract
    held_on = state["held_on"]
    items = []
    for item in state["items"]:
        texts = item_texts(item, sources)
        items.append({
            "id": item["id"], "source": item["source"], "risk_id": item.get("risk_id"), "room_id": texts["room_id"], "room_name": texts["room_name"],
            "severity": texts["severity"], "title": texts["title"], "state": texts["state"], "recommendation": texts["recommendation"],
            "consequence": texts["consequence"], "price": texts["price"], "decision": item.get("decision"),
            "executor_action": item.get("executor_action"), "order_ref": item.get("order_ref"), "note": item.get("note"),
        })
    return {
        "template_version": get_template(DocumentKind.DECISION_PROTOCOL).version,
        "held_on": held_on.isoformat() if held_on else None,
        "held_time": state["held_time"],
        "attendees": list(state["attendees"]),
        "items": items,
        "understood": bool(state["understood"]),
        "signature_refused": bool(state["signature_refused"]),
        "notes": state["notes"],
        "contract": (
            {"id": str(contract.id), "version": contract.version, "status": contract.status, "number": sources.base.contract_number}
            if contract is not None else None
        ),
        "client": document.layout.client.name if document.layout.client else None,
        "executor": document.layout.executor.name if document.layout.executor else None,
    }
