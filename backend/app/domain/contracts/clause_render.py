"""Rendering of the clause catalogue into the printed contract (Stage 16E.3): placeholders, variants and conditions.

Pure functions over plain data. The wording is the catalogue's; what this module adds are the **values** (the price, the dates and
the answers of the questionnaire as printed, with the right Polish form of "dni" / "miesięcy") and the **choice** of the variant of a
clause. Three states of a fact exist: true, false, and *not answered yet*. When the fact that decides a clause is not answered the
variants are all printed, each with a box to tick by hand -- so the working version can be discussed with the customer and an
issued contract never silently picks a side the owner did not choose. A value that is not known is a blank to write in.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.domain.contracts.clauses import PLACEHOLDER, PLACEHOLDERS, AnnexForm, ClauseCatalog, ClauseSection, parse_condition
from app.domain.documents import formatting

Flags = dict[str, bool | None]
Values = dict[str, str | None]  # None = unknown: printed as a blank line


@dataclass(frozen=True, slots=True)
class Segment:
    kind: Literal["text", "value", "blank"]
    text: str = ""


Text = tuple[Segment, ...]


@dataclass(frozen=True, slots=True)
class RenderedClause:
    number: int
    alternatives: tuple[Text, ...]  # one text; several = a choice to tick by hand
    block: str | None

    @property
    def is_choice(self) -> bool:
        return len(self.alternatives) > 1


@dataclass(frozen=True, slots=True)
class RenderedSection:
    key: str
    number: int
    title: str
    numbered: bool
    clauses: tuple[RenderedClause, ...]
    instead: Text | None  # the line that stands in the place of a section that does not apply


@dataclass(frozen=True, slots=True)
class RenderedAnnex:
    number: int
    title: str
    paragraphs: tuple[Text, ...]
    fields: tuple[Text, ...]


# --- facts and values ------------------------------------------------------------------------------------------------------------


def _and(left: bool | None, right: bool | None) -> bool | None:
    if left is False or right is False:
        return False
    return None if left is None or right is None else True


def build_flags(answers: dict[str, Any]) -> Flags:
    """The facts the variants depend on, from the (effective) answers. An unanswered question gives None, never a guess."""
    status, mode = answers.get("client_status"), answers.get("conclusion_mode")
    consumer = None if status is None else status in ("CONSUMER", "CONSUMER_RIGHTS_ENTREPRENEUR")
    offsite = None if mode is None else mode in ("OFF_PREMISES", "DISTANCE")
    supplier, penalty, payment = answers.get("materials_supplier"), answers.get("penalty_mode"), answers.get("payment_mode")
    return {
        "consumer": consumer,
        "offsite_consumer": _and(consumer, offsite),
        "partial_acceptance": answers.get("partial_acceptance"),
        "payment_by_stages": None if payment is None else payment == "BY_STAGES",
        "materials_executor": None if supplier is None else supplier == "EXECUTOR",
        "materials_customer": None if supplier is None else supplier == "CUSTOMER",
        "penalty_per_day": None if penalty is None else penalty == "PER_DAY_DELAY",
        "has_insurance": bool(answers.get("insurance_sum")),
        "reinspection_limit": answers.get("reinspection_limit") is not None,
    }


def _plural(n: int, one: str, many: str) -> str:
    return f"{n}{formatting.NBSP}{one if n == 1 else many}"


def days(n: Any) -> str | None:  # genitive, after "w terminie" / "przez" / "co najmniej"
    return _plural(n, "dnia", "dni") if isinstance(n, int) and not isinstance(n, bool) else None


def working_days(n: Any) -> str | None:
    return _plural(n, "Dnia roboczego", "Dni roboczych") if isinstance(n, int) and not isinstance(n, bool) else None


def months(n: Any) -> str | None:
    return _plural(n, "miesiąca", "miesięcy") if isinstance(n, int) and not isinstance(n, bool) else None


def percent(n: Any) -> str | None:
    return f"{n}{formatting.NBSP}%" if isinstance(n, int) and not isinstance(n, bool) else None


def money(value: Any) -> str | None:
    return formatting.format_money(Decimal(value)) if value else None


def date_text(value: Any) -> str | None:
    return formatting.format_date(date.fromisoformat(value)) if isinstance(value, str) and value else None


def gross_of(net: Decimal | None, vat_percent: Any, *, currency: str = "PLN") -> Decimal | None:
    if net is None or not isinstance(vat_percent, int) or isinstance(vat_percent, bool):
        return None
    return (net * (Decimal(100) + vat_percent) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_values(
    answers: dict[str, Any],
    *,
    object_address: str | None,
    estimate_version: int | None,
    net: Decimal | None,
    currency: str,
    executor: tuple[str | None, str | None, str | None, str | None],  # name, address line, e-mail, phone
    client: tuple[str | None, str | None],  # e-mail, phone
) -> Values:
    """Every placeholder the catalogue may use, as printed (None = unknown)."""
    vat = answers.get("vat_rate_percent")
    gross = gross_of(net, vat)
    advance = answers.get("advance_percent")
    advance_amount = gross * Decimal(advance) / Decimal(100) if gross is not None and isinstance(advance, int) else None
    e_name, e_address, e_email, e_phone = executor
    reinspection = answers.get("reinspection_limit")
    values: Values = {
        "object_address": object_address,
        "estimate_version": str(estimate_version) if estimate_version is not None else None,
        "net_price": formatting.format_money(net, currency) if net is not None else None,
        "vat_rate": percent(vat),
        "gross_price": formatting.format_money(gross, currency) if gross is not None else None,
        "price_validity_days": days(answers.get("price_validity_days")),
        "advance_percent": percent(advance),
        "advance_amount": formatting.format_money(advance_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), currency) if advance_amount is not None else None,
        "work_start_date": date_text(answers.get("work_start_date")),
        "work_end_date": date_text(answers.get("work_end_date")),
        "work_hours": answers.get("work_hours"),
        "payment_due_days": days(answers.get("payment_due_days")),
        "payment_account": answers.get("payment_account"),
        "premises_notice_days": days(answers.get("premises_acceptance_notice_days")),
        "downtime_rate": money(answers.get("downtime_rate_per_day")),
        "downtime_cap_percent": percent(answers.get("downtime_cap_percent")),
        "downtime_days_limit": working_days(answers.get("downtime_days_limit")),
        "insurance_sum": money(answers.get("insurance_sum")),
        "insurance_policy": answers.get("insurance_policy"),
        "appearance_days": working_days(answers.get("customer_appearance_days")),
        "reinspection_limit": str(reinspection) if reinspection is not None else None,
        "warranty_months": months(answers.get("warranty_months")),
        "penalty_rate": money(answers.get("penalty_rate_per_day")),
        "penalty_cap_percent": percent(answers.get("penalty_cap_percent")),
        "executor_name": e_name,
        "executor_address": e_address,
        "executor_email": e_email,
        "executor_phone": e_phone,
        "client_email": client[0],
        "client_phone": client[1],
        "contractor_representative": answers.get("contractor_representative"),
    }
    missing = PLACEHOLDERS - set(values)
    if missing:  # a placeholder the catalogue may use but nobody computes: a bug, not a blank
        raise KeyError(f"no value computed for {sorted(missing)}")
    return values


# --- the choice of a variant -------------------------------------------------------------------------------------------------------


def _holds(condition: str | None, flags: Flags) -> bool | None:
    if condition is None:
        return True
    negated, flag = parse_condition(condition)
    value = flags.get(flag)
    return None if value is None else (not value if negated else value)


def text_segments(text: str, values: Values) -> Text:
    segments: list[Segment] = []
    position = 0
    for match in PLACEHOLDER.finditer(text):
        if match.start() > position:
            segments.append(Segment("text", text[position : match.start()]))
        value = values.get(match.group(1))
        segments.append(Segment("blank") if value is None else Segment("value", value))
        position = match.end()
    if position < len(text):
        segments.append(Segment("text", text[position:]))
    return tuple(segments)


def _choose(variants: list[tuple[str | None, str]], flags: Flags) -> list[str]:
    """The text to print: one variant, or -- when the deciding fact is not answered -- every variant still possible."""
    for index, (condition, text) in enumerate(variants):
        verdict = _holds(condition, flags)
        if verdict is True:
            return [text]
        if verdict is None:
            return [text] + [t for c, t in variants[index + 1 :] if _holds(c, flags) is not False]
    return []


def render_sections(catalog: ClauseCatalog, flags: Flags, values: Values) -> tuple[RenderedSection, ...]:
    return tuple(_render_section(number, section, flags, values) for number, section in enumerate(catalog.sections, start=1))


def _render_section(number: int, section: ClauseSection, flags: Flags, values: Values) -> RenderedSection:
    if section.when is not None and _holds(section.when, flags) is False:
        assert section.else_pl is not None  # guaranteed by the catalogue
        return RenderedSection(section.key, number, section.title_pl, section.numbered, (), text_segments(section.else_pl, values))
    clauses = []
    for clause in section.clauses:
        chosen = _choose([(v.when, v.text_pl) for v in clause.variants], flags)
        if chosen:
            clauses.append(RenderedClause(clause.n, tuple(text_segments(t, values) for t in chosen), clause.block))
    return RenderedSection(section.key, number, section.title_pl, section.numbered, tuple(clauses), None)


def render_annexes(catalog: ClauseCatalog, flags: Flags, values: Values) -> tuple[RenderedAnnex, ...]:
    def one(annex: AnnexForm) -> RenderedAnnex:
        return RenderedAnnex(
            annex.number, annex.title_pl, tuple(text_segments(p, values) for p in annex.paragraphs_pl),
            tuple(text_segments(f, values) for f in annex.fields_pl),
        )

    return tuple(one(a) for a in catalog.annexes if _holds(a.when, flags) is not False)
