"""The answers of the questionnaire "compose the contract" (Stage 16E.1): what an answer may be and when the questionnaire is complete.

Deterministic and catalogue-driven: the **kind** of a question decides the shape of its answer, the catalogue decides which
questions exist, which are REQUIRED and which defaults exist (only the two the owner accepted). An answer is normalised
(trimmed text, ISO date, integers, `"120.00"` money, a list of person ids without repeats) so the same answer is always stored in
the same form. A stored answer is never a number the code invented: an unanswered OPEN question stays empty and the document prints
an empty line for it.
"""

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.contracts.catalog import ContractCatalog, Question, Requirement
from app.domain.exceptions import ContractAnswerInvalidError

TEXT_LIMIT = 500
_MONEY = re.compile(r"^\d{1,9}([.,]\d{1,2})?$")
_RANGES = {"PERCENT": (0, 100), "DAYS": (0, 365), "MONTHS": (0, 120), "NUMBER": (0, 100)}

# reasons the screen has a sentence for
WRONG_TYPE = "WRONG_TYPE"
OUT_OF_RANGE = "OUT_OF_RANGE"
TOO_LONG = "TOO_LONG"
BAD_DATE = "BAD_DATE"
NOT_AN_OPTION = "NOT_AN_OPTION"
UNKNOWN_QUESTION = "UNKNOWN_QUESTION"
UNKNOWN_PERSON = "UNKNOWN_PERSON"
NOT_AUTHORISED = "NOT_AUTHORISED"  # a person of the object who is not marked "may accept the work and sign the protocols"
UNKNOWN_REQUIREMENT = "UNKNOWN_REQUIREMENT"
DATE_ORDER = "DATE_ORDER"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(key: str, value: Any, low: float, high: float) -> int | float:
    """A JSON number (never a bool or a string) within [low, high], kept as an integer when it is one, else with two places."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractAnswerInvalidError(key, WRONG_TYPE)
    if not low <= value <= high:
        raise ContractAnswerInvalidError(key, OUT_OF_RANGE)
    if isinstance(value, int) or float(value).is_integer():
        return int(value)
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def _requirement_value(key: str, requirement: Requirement, value: Any) -> Any:
    if requirement.value_kind == "YES_NO":
        if not isinstance(value, bool):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        return value
    if requirement.value_kind == "NUMBER":
        return _number(key, value, 0, 100000)
    if not isinstance(value, dict) or set(value) != {"min", "max"}:  # NUMBER_RANGE
        raise ContractAnswerInvalidError(key, WRONG_TYPE)
    low, high = _number(key, value["min"], -50, 100), _number(key, value["max"], -50, 100)
    if low > high:
        raise ContractAnswerInvalidError(key, OUT_OF_RANGE)
    return {"min": low, "max": high}


def normalize_answer(
    question: Question, value: Any, *, person_ids: set[str], authorised_ids: set[str], catalog: ContractCatalog
) -> Any:
    """The stored form of one answer, or `ContractAnswerInvalidError`. `value` is never None here (None clears an answer)."""
    key, kind = question.key, question.kind
    if kind == "TEXT":
        if not isinstance(value, str):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        text = " ".join(value.split())
        if len(text) > TEXT_LIMIT:
            raise ContractAnswerInvalidError(key, TOO_LONG)
        return text or None  # blank text is no answer
    if kind == "DATE":
        if not isinstance(value, str):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            raise ContractAnswerInvalidError(key, BAD_DATE) from None
    if kind == "YES_NO":
        if not isinstance(value, bool):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        return value
    if kind in _RANGES:
        if not _is_int(value):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        low, high = _RANGES[kind]
        if not low <= value <= high:
            raise ContractAnswerInvalidError(key, OUT_OF_RANGE)
        return value
    if kind == "MONEY_PLN":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        raw = str(value).strip()
        if not _MONEY.match(raw):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        try:
            return f"{Decimal(raw.replace(',', '.')):.2f}"
        except InvalidOperation:  # pragma: no cover - the pattern already guarantees a decimal
            raise ContractAnswerInvalidError(key, WRONG_TYPE) from None
    if kind == "CHOICE":
        if not isinstance(value, str):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        if value not in (question.options or []):
            raise ContractAnswerInvalidError(key, NOT_AN_OPTION)
        return value
    if kind == "PERSON_LIST":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        ids = []
        for raw in value:
            try:
                person = str(uuid.UUID(raw))
            except ValueError:
                raise ContractAnswerInvalidError(key, WRONG_TYPE) from None
            if person not in person_ids:
                raise ContractAnswerInvalidError(key, UNKNOWN_PERSON)
            if person not in authorised_ids:
                raise ContractAnswerInvalidError(key, NOT_AUTHORISED)
            if person not in ids:
                ids.append(person)
        return ids or None  # an empty list is no answer
    if kind == "REQUIREMENT_VALUES":
        if not isinstance(value, dict):
            raise ContractAnswerInvalidError(key, WRONG_TYPE)
        known = {r.key: r for r in catalog.requirements.items}
        values = {}
        for requirement_key, entry in value.items():
            if requirement_key not in known:
                raise ContractAnswerInvalidError(key, UNKNOWN_REQUIREMENT)
            if entry is None:
                continue  # a requirement left empty
            values[requirement_key] = _requirement_value(key, known[requirement_key], entry)
        return values or None
    raise ContractAnswerInvalidError(key, WRONG_TYPE)  # pragma: no cover - the catalogue admits no other kind


def merge_answers(
    stored: dict[str, Any], changes: dict[str, Any], *, person_ids: set[str], authorised_ids: set[str], catalog: ContractCatalog
) -> dict[str, Any]:
    """The answers after `changes` (None clears an answer). Every change is checked against its question first; nothing is
    applied when one is refused, and the dates must stay in order."""
    questions = {q.key: q for q in catalog.questionnaire.items}
    merged = dict(stored)
    for key, value in changes.items():
        question = questions.get(key)
        if question is None:
            raise ContractAnswerInvalidError(key, UNKNOWN_QUESTION)
        normalized = None if value is None else normalize_answer(question, value, person_ids=person_ids, authorised_ids=authorised_ids, catalog=catalog)
        if normalized is None:
            merged.pop(key, None)
        else:
            merged[key] = normalized
    start, end = merged.get("work_start_date"), merged.get("work_end_date")
    if start and end and end < start:
        raise ContractAnswerInvalidError("work_end_date", DATE_ORDER)
    return merged


def effective_answers(stored: dict[str, Any], catalog: ContractCatalog) -> dict[str, Any]:
    """The stored answers with the catalogue's defaults under them -- the only defaults are the ones the owner accepted."""
    result = {q.key: q.default for q in catalog.questionnaire.items if q.default is not None}
    result.update(stored)
    return result


def missing_required(stored: dict[str, Any], catalog: ContractCatalog) -> list[str]:
    """The REQUIRED questions that have no answer yet (a default is an answer), in the questionnaire's order."""
    effective = effective_answers(stored, catalog)
    return [q.key for q in catalog.questionnaire.items if q.requirement == "REQUIRED" and effective.get(q.key) in (None, [], {})]
