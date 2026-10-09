"""The clause catalogue of the contract (Stages 16E.2 / 16E.3): the **wording** of the contract, a server file the owner approves.

The catalogue is the prototype contract of the owner turned into data: 23 numbered sections (§ 1 ... § 23), each a list of numbered
clauses (ust.), and the annexes 6-12 (forms and the fixed texts). Three mechanisms keep the text honest:

* a **placeholder** `{name}` is replaced by a value of the contract (the price, a date, an answer of the questionnaire); a value that
  is not known prints an empty line to write in by hand -- the code never invents a number;
* a clause has one or more **variants**, each with a condition (`consumer`, `!partial_acceptance` ...) computed from the answers;
  the number of a clause never changes with its variant, so a reference such as "§ 10 ust. 5" is always right. When the answer
  that decides is not given, the variants are printed as boxes to tick by hand;
* a **review note** is the question to the lawyer that belongs to a clause. It is never printed in a client document, and the
  catalogue cannot be `approved` while a note is open.

Until the catalogue is `approved` (with who and when) every contract is printed with the "WERSJA ROBOCZA" watermark. The version of the
catalogue and its approval state are written into the snapshot of an issued contract, so a dispute can always say which wording the
customer had. Nothing here is legal advice and nothing is generated.
"""

import json
import re
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.documents.registry import DocumentKind, get_template
from app.domain.exceptions import DocumentDataError

CLAUSES_FILE = Path(__file__).resolve().parent / "catalog" / "clauses.json"
ANNEX_NUMBERS = (6, 7, 8, 9, 10, 11, 12)  # annexes 1-5 are built from the data of the object and the catalogues

# the facts a variant or a section may depend on (three-valued: true / false / not answered yet)
FLAGS = frozenset({
    "consumer", "offsite_consumer", "partial_acceptance", "payment_by_stages", "materials_executor", "materials_customer",
    "penalty_per_day", "has_insurance", "reinspection_limit",
})
# the values a text may print
PLACEHOLDERS = frozenset({
    "object_address", "estimate_version", "net_price", "vat_rate", "gross_price", "price_validity_days", "advance_percent",
    "advance_amount", "work_start_date", "work_end_date", "work_hours", "payment_due_days", "payment_account", "premises_notice_days",
    "downtime_rate", "downtime_cap_percent", "downtime_days_limit", "insurance_sum", "insurance_policy", "appearance_days",
    "reinspection_limit", "warranty_months", "penalty_rate", "penalty_cap_percent", "executor_name", "executor_address",
    "executor_email", "executor_phone", "client_email", "client_phone", "contractor_representative",
})
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_REFERENCE = re.compile(r"§\s*(\d+)(?:\s+ust\.\s*(\d+))?")
_ARTICLE_BEFORE = re.compile(r"art\.\s*\d+\w*\s*$")  # "art. 355 § 2 KC" is the Civil Code, not a section of the contract


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def parse_condition(condition: str) -> tuple[bool, str]:
    """`"consumer"` -> (False, "consumer"), `"!consumer"` -> (True, "consumer")."""
    negated = condition.startswith("!")
    flag = condition[1:] if negated else condition
    if flag not in FLAGS:
        raise ValueError(f"unknown condition {condition!r}")
    return negated, flag


def _check_text(text: str) -> None:
    if not text.strip():
        raise ValueError("a text of the catalogue is not empty")
    unknown = sorted(set(PLACEHOLDER.findall(text)) - PLACEHOLDERS)
    if unknown:
        raise ValueError(f"unknown placeholders {unknown}")
    if re.search(r"[{}]", PLACEHOLDER.sub("", text)):
        raise ValueError(f"a stray brace in {text[:60]!r}")


class ReviewNote(_Model):
    ref: str = Field(pattern=r"^L\d+$")
    text: str = Field(min_length=3)
    status: Literal["OPEN", "RESOLVED"]


class Variant(_Model):
    when: str | None
    text_pl: str

    @model_validator(mode="after")
    def _valid(self) -> "Variant":
        _check_text(self.text_pl)
        if self.when is not None:
            parse_condition(self.when)
        return self


class Clause(_Model):
    n: int = Field(ge=1)
    variants: list[Variant] = Field(min_length=1)
    block: Literal["persons_table"] | None = None  # a block of the document printed right after this clause
    review_notes: list[ReviewNote] = []

    @property
    def always_printed(self) -> bool:
        return self.variants[-1].when is None


class ClauseSection(_Model):
    key: str = Field(pattern=r"^[a-z]+(_[a-z]+)*$")
    title_pl: str = Field(min_length=3)
    numbered: bool = True  # a section with one paragraph prints it without "1."
    when: str | None = None  # the section applies only when this is not false ...
    else_pl: str | None = None  # ... otherwise this line stands in its place (the number of the section stays)
    clauses: list[Clause] = Field(min_length=1)

    @model_validator(mode="after")
    def _valid(self) -> "ClauseSection":
        if (self.when is None) != (self.else_pl is None):
            raise ValueError(f"{self.key}: `when` and `else_pl` go together")
        if self.when is not None:
            parse_condition(self.when)
        if self.else_pl is not None:
            _check_text(self.else_pl)
        if [c.n for c in self.clauses] != list(range(1, len(self.clauses) + 1)):
            raise ValueError(f"{self.key}: clauses are numbered 1, 2, 3 ... in order")
        if not self.numbered and len(self.clauses) != 1:
            raise ValueError(f"{self.key}: only a one-paragraph section is printed without numbers")
        # a clause that may print nothing would leave a gap in the numbers: only the last one may
        for clause in self.clauses[:-1]:
            if not clause.always_printed:
                raise ValueError(f"{self.key} ust. {clause.n}: every variant is conditional, so it may print nothing; only the last clause may")
        return self


class AnnexForm(_Model):
    number: int
    title_pl: str = Field(min_length=3)
    when: str | None
    paragraphs_pl: list[str]
    fields_pl: list[str]  # the lines of a form to complete by hand
    review_notes: list[ReviewNote]

    @model_validator(mode="after")
    def _valid(self) -> "AnnexForm":
        if self.when is not None:
            parse_condition(self.when)
        for text in (*self.paragraphs_pl, *self.fields_pl):
            _check_text(text)
        if not self.paragraphs_pl and not self.fields_pl:
            raise ValueError(f"annex {self.number} has neither text nor fields")
        return self


class ClauseCatalog(_Model):
    version: int = Field(ge=1)
    approved: bool
    approved_by: str | None
    approved_on: date | None
    sections: list[ClauseSection]
    annexes: list[AnnexForm]

    @property
    def open_notes(self) -> list[str]:
        notes = [n for s in self.sections for c in s.clauses for n in c.review_notes] + [n for a in self.annexes for n in a.review_notes]
        return [n.ref for n in notes if n.status == "OPEN"]

    @model_validator(mode="after")
    def _approval_is_complete_and_the_text_is_consistent(self) -> "ClauseCatalog":
        if self.approved and not (self.approved_by and self.approved_on):
            raise ValueError("an approved catalogue names who approved it and when")
        if not self.approved and (self.approved_by or self.approved_on):
            raise ValueError("an unapproved catalogue carries no approval")
        if self.approved and self.open_notes:
            raise ValueError(f"an approved catalogue has no open question to the lawyer, still open: {self.open_notes}")
        expected = list(get_template(DocumentKind.CONTRACT).sections)
        if [s.key for s in self.sections] != expected:
            raise ValueError(f"the sections of the catalogue must be exactly {expected} in this order")
        if [a.number for a in self.annexes] != list(ANNEX_NUMBERS):
            raise ValueError(f"the annexes of the catalogue must be exactly {list(ANNEX_NUMBERS)}")
        refs = [n.ref for s in self.sections for c in s.clauses for n in c.review_notes] + [n.ref for a in self.annexes for n in a.review_notes]
        if len(refs) != len(set(refs)):
            raise ValueError("a review note appears twice")
        sizes = {number: len(section.clauses) for number, section in enumerate(self.sections, start=1)}
        texts = [v.text_pl for s in self.sections for c in s.clauses for v in c.variants] + [t for a in self.annexes for t in a.paragraphs_pl]
        for text in texts:
            for match in _REFERENCE.finditer(text):
                if _ARTICLE_BEFORE.search(text[: match.start()]):
                    continue
                number, clause = int(match.group(1)), match.group(2)
                if number not in sizes or (clause is not None and not 1 <= int(clause) <= sizes[number]):
                    raise ValueError(f"the reference {match.group(0)!r} points to nothing")
        return self


@cache
def load_clause_catalog() -> ClauseCatalog:
    try:
        return ClauseCatalog.model_validate(json.loads(CLAUSES_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise DocumentDataError("CATALOG_INVALID", f"clauses.json: {exc}") from exc
