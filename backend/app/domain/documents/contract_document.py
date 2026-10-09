"""The contract (Umowa) as a document (Stage 16E.2).

What the contract says is data, never prose written by the code: the **answers** of the owner's questionnaire (16E.1), the persons
who may accept the work, the price of the current estimate (without VAT), and -- as annexes of the same issue -- the technological
card, the production plan, the requirements for the premises and the regulation of acceptance. The **wording** of the clauses
(§ 1 ... § 23 and the annexes 6-12) comes from the clause catalogue (`contracts/catalog/clauses.json`, 16E.3): the values of the
contract are put into its placeholders, a clause whose deciding answer is not given is printed as choices to tick, and while the
catalogue is not approved by the owner and a lawyer every contract carries the "WERSJA ROBOCZA" watermark.

Two forms of one builder, like the card and the plan: **issued** (numbered, journalled, built from data that the gate has just
checked) and the **working version** (pale watermark, no number, never refuses: whatever is not answered yet is an empty line to
write in by hand, so the owner can print the whole packet and talk it through with the customer).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.domain.contracts.catalog import ContractCatalog, load_contract_catalog
from app.domain.contracts.clause_render import (
    RenderedAnnex, RenderedSection, build_flags, build_values, render_annexes, render_sections,
)
from app.domain.contracts.clauses import load_clause_catalog
from app.domain.contracts.gate import GateData
from app.domain.documents import formatting
from app.domain.documents.estimate_document import object_lines
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta, Party
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.production_plan_document import ProductionPlanDocument, build_production_plan_document
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.tech_card_document import TechCardDocument, build_tech_card_document
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.rules.polish_identifiers import format_nip, normalize_nip
from app.models.client import Client
from app.models.contract import Contract


@dataclass(frozen=True, slots=True)
class FactRow:
    label: str
    value: str | None  # None = an empty line to write in


@dataclass(frozen=True, slots=True)
class CheckOption:
    label: str
    checked: bool


@dataclass(frozen=True, slots=True)
class PersonRow:
    name: str
    side: str
    role: str | None
    phone: str | None
    paid_orders: str  # "tak" / "nie": may accept orders that raise the price (§ 21 ust. 3)


@dataclass(frozen=True, slots=True)
class RequirementRow:
    text: str
    value: str | None


@dataclass(frozen=True, slots=True)
class ClassRow:
    code: str
    text: str
    lighting: str
    needs_agreement: bool


@dataclass(frozen=True, slots=True)
class DefectRow:
    text: str
    outcome: str
    criteria: str | None


@dataclass(frozen=True, slots=True)
class Regulation:
    classes: tuple[ClassRow, ...]
    defects: tuple[DefectRow, ...]
    instruments: tuple[str, ...]
    tolerances: tuple[str, ...]  # empty until the owner approves values with their source


@dataclass(frozen=True, slots=True)
class ContractDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    intro: tuple[FactRow, ...]  # date and place of the contract
    client_status: tuple[CheckOption, ...]  # the boxes under the parties: who the customer is ...
    conclusion_mode: tuple[CheckOption, ...]  # ... and where the contract is concluded
    sections: tuple[RenderedSection, ...]
    annexes: tuple[RenderedAnnex, ...]  # the annexes 6-12 of the catalogue (forms and fixed texts)
    persons: tuple[PersonRow, ...]
    requirements: tuple[RequirementRow, ...]
    regulation: Regulation
    tech_card: TechCardDocument
    plan: ProductionPlanDocument
    estimate_version: int | None  # the estimate whose price is the price of the contract
    estimate_total: str | None  # as printed, without VAT
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def client_party(client: Client | None) -> Party | None:
    """The customer block of a contract: name, address (16B.1), tax id of a company, phone and e-mail."""
    if client is None:
        return None
    person = " ".join(part for part in (client.first_name, client.last_name) if part)
    city_line = " ".join(part for part in (client.postal_code, client.city) if part)
    address = tuple(line for line in (client.street, city_line) if line)
    tax_id = None
    if client.nip:
        try:
            tax_id = format_nip(normalize_nip(client.nip))
        except ValueError:
            tax_id = client.nip  # stored as the owner typed it; print it, do not hide it
    return Party(name=client.company_name or person or "—", tax_id=tax_id, address_lines=address, phone=client.phone, email=client.email)


# --- values as printed -------------------------------------------------------------------------------------------------------------


def _date(value: Any) -> str | None:
    return formatting.format_date(date.fromisoformat(value)) if isinstance(value, str) and value else None


def _number(value: Any) -> str:
    """`300` stays `300`, `25.5` becomes `25,5`, `3.456` becomes `3,46` (a threshold is not an amount: no forced decimals)."""
    number = Decimal(str(value))
    if number == number.to_integral_value():
        return formatting.format_decimal(number, 0)
    text = formatting.format_decimal(number, 2)
    return text[:-1] if text.endswith("0") else text


def _requirement_value(kind: str, unit: str | None, value: Any) -> str | None:
    labels = Labels()
    suffix = f"{formatting.NBSP}{unit}" if unit else ""
    if value is None:
        return None
    if kind == "YES_NO":
        return labels("contract.yes") if value else labels("contract.no")
    if kind == "NUMBER_RANGE":
        return labels("contract.range", low=_number(value["min"]), high=_number(value["max"])) + suffix
    return _number(value) + suffix


def _unit_text(unit: str | None) -> str | None:
    labels = Labels()
    names = {
        "lx": "lx", "°C": "°C", "%": "%", "mm": "mm", "mm/m": "mm/m",
        "days": labels("contract.unit.days"), "months": labels("contract.unit.months"),
        "working_days": labels("contract.unit.working_days"), "PLN": "zł",
    }
    return names[unit] if unit else None


# --- the builder ------------------------------------------------------------------------------------------------------------------


def _persons(data: GateData, answers: dict[str, Any]) -> tuple[PersonRow, ...]:
    labels = Labels()
    sides = {
        "CUSTOMER": labels("contract.side.customer"),
        "CUSTOMER_REPRESENTATIVE": labels("contract.side.customer_representative"),
        "SUPERVISION": labels("contract.side.supervision"),
        "CONTRACTOR": labels("contract.side.contractor"),
    }
    chosen = answers.get("who_accepts") or []
    paid = set(answers.get("paid_orders_persons") or [])
    by_id = {str(p.id): p for p in data.people}
    return tuple(
        PersonRow(by_id[pid].name, sides[by_id[pid].side], by_id[pid].role_title, by_id[pid].phone,
                  labels("contract.yes") if pid in paid else labels("contract.no"))
        for pid in chosen if pid in by_id
    )


def _regulation(data: GateData, catalog: ContractCatalog) -> Regulation:
    labels = Labels()
    in_scope = {s.quality_target for room in data.rooms for s in room.surfaces if s.works and s.quality_target}
    lighting = {
        "NONE_SPECIFIED": labels("contract.lighting.none_specified"),
        "DIFFUSE": labels("contract.lighting.diffuse"),
        "DEMANDING": labels("contract.lighting.demanding"),
        "AGREED_BEFORE_WORK": labels("contract.lighting.agreed_before_work"),
        "RAKING_LIGHT": labels("contract.lighting.raking_light"),
    }
    outcome = {"ACCEPTED_WITH_REMARKS": labels("contract.outcome.with_remarks"), "NOT_ACCEPTED": labels("contract.outcome.not_accepted")}
    conditions = [c for c in catalog.evaluation.items if c.key in in_scope] or list(catalog.evaluation.items)
    return Regulation(
        classes=tuple(ClassRow(c.key, c.text_pl, lighting[c.lighting], c.requires_agreement) for c in conditions),
        defects=tuple(DefectRow(d.text_pl, outcome[d.outcome], d.criteria_pl) for d in catalog.defects.items),
        instruments=tuple(i.text_pl for i in catalog.instruments.items),
        tolerances=tuple(
            f"{t.text_pl}: {_number(t.limit_value)}{formatting.NBSP}{t.unit} ({t.norm_ref})" for t in catalog.tolerances.items
        ),
    )


def _requirements(answers: dict[str, Any], catalog: ContractCatalog) -> tuple[RequirementRow, ...]:
    values = answers.get("premises_requirement_values") or {}
    return tuple(
        RequirementRow(r.text_pl, _requirement_value(r.value_kind, _unit_text(r.unit), values.get(r.key))) for r in catalog.requirements.items
    )


def _price(data: GateData) -> str | None:
    estimate = data.estimate
    if estimate is None or estimate.total is None:
        return None
    return formatting.format_money(estimate.total, estimate.currency)


def _options(answer: Any, options: tuple[tuple[str, str], ...]) -> tuple[CheckOption, ...]:
    return tuple(CheckOption(label, answer == key) for key, label in options)


def _status_options(answers: dict[str, Any]) -> tuple[CheckOption, ...]:
    labels = Labels()
    return _options(answers.get("client_status"), (
        ("CONSUMER", labels("contract.status.consumer")),
        ("CONSUMER_RIGHTS_ENTREPRENEUR", labels("contract.status.consumer_rights_entrepreneur")),
        ("ENTREPRENEUR", labels("contract.status.entrepreneur")),
    ))


def _mode_options(answers: dict[str, Any]) -> tuple[CheckOption, ...]:
    labels = Labels()
    return _options(answers.get("conclusion_mode"), (
        ("PREMISES_OF_EXECUTOR", labels("contract.mode.premises_of_executor")),
        ("OFF_PREMISES", labels("contract.mode.off_premises")),
        ("DISTANCE", labels("contract.mode.distance")),
    ))


def build_contract_document(
    contract: Contract | None,
    effective: dict[str, Any],
    data: GateData,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> ContractDocument:
    """`effective` are the answers with the accepted defaults (an empty dict for a contract nobody has started)."""
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if data.executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a contract")
    catalog, clauses = load_contract_catalog(), load_clause_catalog()
    labels = Labels()
    persons = _persons(data, effective)
    card = build_tech_card_document(data.project, data.client, data.executor, data.rooms, working=working, issued_on=issued_on)
    plan = build_production_plan_document(
        data.project, data.client, data.executor, data.rooms, data.adjacent, working=working, issued_on=issued_on
    )
    place = effective.get("contract_place")
    executor_party = party_from_executor_profile(data.executor) if data.executor is not None else None
    client = client_party(data.client)
    estimate = data.estimate
    flags = build_flags(effective)
    values = build_values(
        effective,
        object_address=", ".join(object_lines(data.project)) or None,
        estimate_version=estimate.version if estimate is not None else None,
        net=estimate.total if estimate is not None else None,
        currency=estimate.currency if estimate is not None else "PLN",
        executor=(
            executor_party.name if executor_party else None,
            ", ".join(executor_party.address_lines) if executor_party and executor_party.address_lines else None,
            executor_party.email if executor_party else None,
            executor_party.phone if executor_party else None,
        ),
        client=(client.email if client else None, client.phone if client else None),
    )
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("contract.title"),
            issued_on=issued_on,
            number=number,
            place=place or (data.executor.city if data.executor is not None else None) or None,
            sequence=sequence,
        ),
        executor=executor_party,
        client=client,
        signatures=False,  # the template prints them right after § 23, before the annexes
        draft=working or not clauses.approved,  # unapproved wording is always a draft
        light_watermark=working,
    )
    return ContractDocument(
        layout=layout,
        object_name=data.project.name,
        object_lines=object_lines(data.project),
        intro=(
            FactRow(labels("contract.f.contract_date"), _date(effective.get("contract_date"))),
            FactRow(labels("contract.f.contract_place"), place),
            FactRow(labels("contract.f.object"), data.project.name),
        ),
        client_status=_status_options(effective),
        conclusion_mode=_mode_options(effective),
        sections=render_sections(clauses, flags, values),
        annexes=render_annexes(clauses, flags, values),
        persons=persons,
        requirements=_requirements(effective, catalog),
        regulation=_regulation(data, catalog),
        tech_card=card,
        plan=plan,
        estimate_version=data.estimate.version if data.estimate is not None else None,
        estimate_total=_price(data),
        working=working,
    )


def render_contract_html(document: ContractDocument) -> str:
    return render_html(get_template(DocumentKind.CONTRACT), document.context())


def snapshot_of(
    contract: Contract, effective: dict[str, Any], data: GateData, document: ContractDocument
) -> dict[str, Any]:
    """The frozen conditions of an issued contract (JSON): what a dispute needs to know without re-reading live data."""
    clauses = load_clause_catalog()
    estimate = data.estimate
    return {
        "template_version": get_template(DocumentKind.CONTRACT).version,
        "questionnaire_version": contract.questionnaire_version,
        "clauses": {"version": clauses.version, "approved": clauses.approved, "approved_by": clauses.approved_by},
        "answers": effective,
        "persons": [
            {"id": str(p.id), "name": p.name, "side": p.side, "role_title": p.role_title, "phone": p.phone, "email": p.email}
            for p in data.people
            if str(p.id) in (effective.get("who_accepts") or [])
        ],
        "client": {
            "id": str(data.client.id) if data.client else None,
            "name": document.layout.client.name if document.layout.client else None,
            "address": list(document.layout.client.address_lines) if document.layout.client else [],
        },
        "executor": {"name": document.layout.executor.name if document.layout.executor else None},
        "estimate": (
            {"id": str(estimate.id), "version": estimate.version, "status": estimate.status.value,
             "total": str(estimate.total) if estimate.total is not None else None, "currency": estimate.currency}
            if estimate is not None else None
        ),
        "scope": {
            "rooms": len(document.tech_card.rooms),
            "surfaces": sum(len(r.surfaces) for r in document.tech_card.rooms),
            "works": sum(len(r.works) for r in document.plan.rooms),
            "adjacent_works": len(document.plan.adjacent),
        },
    }

