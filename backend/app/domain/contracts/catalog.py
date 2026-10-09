"""Catalogues of the contract and the protocols (Stage 16B.3) -- structure and starter wording, never a clause.

What lives here: the requirements for the premises (a starter list WITHOUT numbers), the instruments of assessment, the
conditions of the visual assessment by quality class (S1-S4 / Q1-Q4), the classes of defects, the tolerances (the format only: the
file stays empty until the owner approves values with their source) and the questionnaire that opens when the contractor presses
"compose the contract". All of it is server data: the screens only draw it. A number (a threshold, a rate, a date) is never a
part of a catalogue; it is an answer the owner gives in the questionnaire. Legal wording (clauses, norms quoted) is not here
either -- it belongs to the clause catalogue of the contract (16E) and the knowledge base (Stage 17).

Every item has a `label_key` of the form `contractCatalog.<section>.<key>`; the interface texts (PL / RU) are in the frontend
dictionaries and a test pins the two together. `text_pl` is the Polish wording a client document may print.
"""

import json
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
KEY = r"^[a-z][a-z0-9_]*$"
CLASS_KEY = r"^[SQ][1-4]$"
QUALITY_CLASSES = ("S1", "S2", "S3", "S4", "Q1", "Q2", "Q3", "Q4")

RequirementGroup = Literal["LIGHTING", "GLAZING", "CLIMATE", "UTILITIES", "ACCESS", "CLEANLINESS", "SUBSTRATE"]
ValueKind = Literal["YES_NO", "NUMBER", "NUMBER_RANGE"]
Measure = Literal["FLATNESS", "VERTICALITY", "HORIZONTALITY", "DIMENSIONS", "MOISTURE", "SURFACE_APPEARANCE", "ADHESION"]
Lighting = Literal["NONE_SPECIFIED", "DIFFUSE", "DEMANDING", "AGREED_BEFORE_WORK", "RAKING_LIGHT"]
Outcome = Literal["ACCEPTED_WITH_REMARKS", "NOT_ACCEPTED"]
QuestionGroup = Literal["PARTIES", "DATES", "PAYMENT", "WARRANTY", "PENALTY", "DOWNTIME", "ACCEPTANCE", "PREMISES"]
QuestionKind = Literal[
    "TEXT", "DATE", "NUMBER", "MONEY_PLN", "PERCENT", "DAYS", "MONTHS", "YES_NO", "CHOICE", "PERSON_LIST", "REQUIREMENT_VALUES"
]
Unit = Literal["lx", "°C", "%", "days", "months", "working_days", "PLN", "mm", "mm/m"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Requirement(_Model):
    key: str = Field(pattern=KEY)
    group: RequirementGroup
    value_kind: ValueKind
    unit: Unit | None
    label_key: str
    text_pl: str = Field(min_length=3)

    @model_validator(mode="after")
    def _unit_follows_the_kind(self) -> "Requirement":
        if (self.value_kind == "YES_NO") != (self.unit is None):
            raise ValueError(f"{self.key}: a yes/no requirement has no unit, a number has one")
        return self


class Instrument(_Model):
    key: str = Field(pattern=KEY)
    measures: list[Measure] = Field(min_length=1)
    label_key: str
    text_pl: str = Field(min_length=3)


class EvaluationCondition(_Model):
    """The conditions of the visual assessment of one quality class. No millimetre belongs here: S1-S4 / Q1-Q4 are finish
    standards, the geometry is measured separately (Stage 12, 27.1) and its limits are the tolerance catalogue's."""

    key: str = Field(pattern=CLASS_KEY)
    lighting: Lighting
    requires_agreement: bool
    label_key: str
    text_pl: str = Field(min_length=3)


class DefectClass(_Model):
    key: Literal["REMOVABLE", "SIGNIFICANT"]
    outcome: Outcome
    label_key: str
    text_pl: str = Field(min_length=3)
    criteria_pl: str | None  # the criteria of classification: the owner's and the lawyer's to approve, null until then


class Tolerance(_Model):
    """A geometric limit measured with named instruments. Refused without its source (`norm_ref`): no guessed numbers."""

    key: str = Field(pattern=KEY)
    parameter: Measure
    instrument_keys: list[str] = Field(min_length=1)
    limit_value: Decimal = Field(gt=0)
    unit: Literal["mm", "mm/m"]
    norm_ref: str = Field(min_length=3)
    applies_to: list[str] = Field(min_length=1)
    label_key: str
    text_pl: str = Field(min_length=3)

    @model_validator(mode="after")
    def _classes_exist(self) -> "Tolerance":
        unknown = [c for c in self.applies_to if c not in QUALITY_CLASSES]
        if unknown:
            raise ValueError(f"{self.key}: unknown quality classes {unknown}")
        return self


class Question(_Model):
    key: str = Field(pattern=KEY)
    group: QuestionGroup
    kind: QuestionKind
    requirement: Literal["REQUIRED", "OPEN"]  # OPEN: may stay empty, the document prints a field to fill in by hand ("......")
    default: int | bool | None
    options: list[str] | None
    unit: Unit | None
    label_key: str
    hint_key: str | None

    @model_validator(mode="after")
    def _shape_follows_the_kind(self) -> "Question":
        if (self.kind == "CHOICE") != bool(self.options):
            raise ValueError(f"{self.key}: only a choice has options, and a choice needs them")
        if self.default is not None:
            ok = (
                isinstance(self.default, bool)
                if self.kind == "YES_NO"
                else self.kind in ("NUMBER", "PERCENT", "DAYS", "MONTHS") and isinstance(self.default, int) and not isinstance(self.default, bool)
            )
            if not ok:
                raise ValueError(f"{self.key}: a default does not fit the kind {self.kind}")
        return self


class _Catalog(_Model):
    version: int = Field(ge=1)


class RequirementCatalog(_Catalog):
    items: list[Requirement]


class InstrumentCatalog(_Catalog):
    items: list[Instrument]


class EvaluationCatalog(_Catalog):
    items: list[EvaluationCondition]


class DefectCatalog(_Catalog):
    items: list[DefectClass]


class ToleranceCatalog(_Catalog):
    items: list[Tolerance]


class QuestionnaireCatalog(_Catalog):
    items: list[Question]


class ContractCatalog(_Model):
    requirements: RequirementCatalog
    instruments: InstrumentCatalog
    evaluation: EvaluationCatalog
    defects: DefectCatalog
    tolerances: ToleranceCatalog
    questionnaire: QuestionnaireCatalog


SECTIONS: dict[str, tuple[str, type[_Catalog]]] = {
    "requirements": ("premises_requirements.json", RequirementCatalog),
    "instruments": ("assessment_instruments.json", InstrumentCatalog),
    "evaluation": ("evaluation_conditions.json", EvaluationCatalog),
    "defects": ("defect_classes.json", DefectCatalog),
    "tolerances": ("tolerances.json", ToleranceCatalog),
    "questionnaire": ("questionnaire.json", QuestionnaireCatalog),
}
# the section of the interface dictionary where the label of each catalogue lives
LABEL_SECTION = {
    "requirements": "requirements", "instruments": "instruments", "evaluation": "evaluation", "defects": "defects",
    "tolerances": "tolerances", "questionnaire": "questions",
}


class ContractCatalogError(ValueError):
    """A catalogue file is wrong; the application must not start on guessed data."""


def _validate(name: str, catalog: _Catalog) -> None:
    keys = [item.key for item in catalog.items]
    if len(keys) != len(set(keys)):
        raise ContractCatalogError(f"{name}: duplicate keys")
    for item in catalog.items:
        expected = f"contractCatalog.{LABEL_SECTION[name]}.{item.key}"
        if item.label_key != expected:
            raise ContractCatalogError(f"{name}.{item.key}: label_key must be {expected!r}")
        hint = getattr(item, "hint_key", None)
        if hint is not None and hint != f"contractCatalog.hints.{item.key}":
            raise ContractCatalogError(f"{name}.{item.key}: hint_key must be contractCatalog.hints.{item.key}")


@cache
def load_contract_catalog() -> ContractCatalog:
    loaded: dict[str, _Catalog] = {}
    for name, (file_name, model) in SECTIONS.items():
        try:
            catalog = model.model_validate(json.loads((CATALOG_DIR / file_name).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise ContractCatalogError(f"{file_name}: {exc}") from exc
        _validate(name, catalog)
        loaded[name] = catalog
    result = ContractCatalog(**loaded)
    covered = [item.key for item in result.evaluation.items]
    if covered != list(QUALITY_CLASSES):
        raise ContractCatalogError(f"evaluation_conditions.json must cover exactly {list(QUALITY_CLASSES)} in this order, got {covered}")
    instrument_keys = {item.key for item in result.instruments.items}
    for tolerance in result.tolerances.items:
        unknown = [k for k in tolerance.instrument_keys if k not in instrument_keys]
        if unknown:
            raise ContractCatalogError(f"tolerances.{tolerance.key}: unknown instruments {unknown}")
    return result
