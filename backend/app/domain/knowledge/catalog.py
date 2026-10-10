"""The knowledge base (Stage 17): sources of law and norms, short entries about them, situations, and links to the rest of the
application. Structure and checks only -- the content is written and approved by the owner and the lawyer.

The catalogue is a set of versioned files in the repository (`catalog/`), read once and checked before the application
serves anything from it: a wrong file stops the startup instead of showing a guessed answer. Rules of the content
(`docs/STAGE_17_LEGAL_KNOWLEDGE_PLAN_RU.md`, decisions of 2026-10-11):

- every entry and source is `DRAFT` until the owner approves it (who and when) and says when it was checked against the
  published text; a `DRAFT` is shown to the owner with its mark and never goes into a document for a client;
- a norm (PN-EN) or a technical instruction (ITB) is a reference only: designation, title, place, link -- never its text
  and never a paraphrase of its requirements (Q4);
- Polish is the language of the law; the Russian text is an explanation for the contractor (Q3);
- a situation is a closed tree of questions with answers that end in an outcome: steps, entries, phrases for the client
  (Stage 8) and documents to issue (Stages 15-16).
"""

import json
import re
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"
CODE = r"^[A-Z0-9][A-Z0-9_.-]{1,40}$"
TAG = r"^[a-z0-9][a-z0-9_-]{0,30}$"
NODE = r"^[a-z][a-z0-9_]{0,30}$"

SourceKind = Literal["STATUTE", "NORM", "ITB", "OTHER"]
Status = Literal["DRAFT", "APPROVED"]
LinkTarget = Literal["RISK", "CLAUSE", "PHRASE", "DOCUMENT"]
# A source of these kinds is referenced, never told (Q4).
REFERENCE_ONLY: frozenset[str] = frozenset({"NORM", "ITB"})


class KnowledgeCatalogError(ValueError):
    """A file of the knowledge base is wrong; the application must not serve guessed content."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewNote(_Model):
    ref: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=500)
    status: Literal["OPEN", "RESOLVED"]


class _Approved(_Model):
    status: Status
    approved_by: str | None = Field(default=None, max_length=120)
    approved_on: date | None = None
    checked_on: date | None = None

    @model_validator(mode="after")
    def _approval(self):
        if self.status == "APPROVED" and not (self.approved_by and self.approved_on and self.checked_on):
            raise ValueError("an APPROVED item needs approved_by, approved_on and checked_on")
        if self.status == "DRAFT" and (self.approved_by or self.approved_on):
            raise ValueError("a DRAFT item is not approved by anyone yet")
        return self


class Source(_Approved):
    code: str = Field(pattern=CODE)
    kind: SourceKind
    title_pl: str = Field(min_length=1, max_length=300)
    designation: str = Field(min_length=1, max_length=120)
    url: str | None = Field(default=None, pattern=r"^https://[^\s]{4,500}$")


class Entry(_Approved):
    code: str = Field(pattern=CODE)
    source: str = Field(pattern=CODE)
    locator: str | None = Field(default=None, max_length=120)
    title_pl: str = Field(min_length=1, max_length=200)
    title_ru: str = Field(min_length=1, max_length=200)
    summary_pl: str | None = Field(default=None, min_length=1, max_length=2000)
    explanation_ru: str | None = Field(default=None, min_length=1, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    works: list[str] = Field(default_factory=list, max_length=12)
    substrates: list[str] = Field(default_factory=list, max_length=8)
    qualities: list[str] = Field(default_factory=list, max_length=8)
    review_notes: list[ReviewNote] = Field(default_factory=list)


class Answer(_Model):
    text_pl: str = Field(min_length=1, max_length=200)
    text_ru: str = Field(min_length=1, max_length=200)
    next: str = Field(pattern=NODE)


class Question(_Model):
    id: str = Field(pattern=NODE)
    text_pl: str = Field(min_length=1, max_length=300)
    text_ru: str = Field(min_length=1, max_length=300)
    answers: list[Answer] = Field(min_length=2, max_length=8)


class Outcome(_Model):
    id: str = Field(pattern=NODE)
    steps_pl: list[str] = Field(min_length=1, max_length=12)
    steps_ru: list[str] = Field(min_length=1, max_length=12)
    entries: list[str] = Field(default_factory=list, max_length=12)
    phrases: list[str] = Field(default_factory=list, max_length=8)
    documents: list[str] = Field(default_factory=list, max_length=6)
    lawyer: bool = False

    @model_validator(mode="after")
    def _same_steps(self):
        if len(self.steps_pl) != len(self.steps_ru):
            raise ValueError("steps_pl and steps_ru must have the same number of steps")
        return self


class Situation(_Model):
    code: str = Field(pattern=CODE)
    status: Status
    title_pl: str = Field(min_length=1, max_length=200)
    title_ru: str = Field(min_length=1, max_length=200)
    start: str = Field(pattern=NODE)
    questions: list[Question] = Field(min_length=1, max_length=30)
    outcomes: list[Outcome] = Field(min_length=1, max_length=30)


class Link(_Model):
    target_kind: LinkTarget
    target: str = Field(min_length=1, max_length=80)
    entries: list[str] = Field(min_length=1, max_length=12)


class Meta(_Model):
    version: int = Field(ge=1)
    updated_on: date
    disclaimer_pl: str | None = Field(default=None, min_length=1, max_length=600)
    disclaimer_ru: str | None = Field(default=None, min_length=1, max_length=600)
    disclaimer_status: Status


class KnowledgeCatalog(_Model):
    meta: Meta
    sources: list[Source]
    entries: list[Entry]
    situations: list[Situation]
    links: list[Link]

    def source(self, code: str) -> Source | None:
        return next((s for s in self.sources if s.code == code), None)

    def entry(self, code: str) -> Entry | None:
        return next((e for e in self.entries if e.code == code), None)

    def situation(self, code: str) -> Situation | None:
        return next((s for s in self.situations if s.code == code), None)

    def links_to(self, entry_code: str) -> list[Link]:
        return [link for link in self.links if entry_code in link.entries]


FILES = {"meta": "meta.json", "sources": "sources.json", "entries": "entries.json", "situations": "situations.json", "links": "links.json"}


class References(_Model):
    """What the rest of the application offers to be linked to; read from it, never copied here."""

    risks: frozenset[str]
    clauses: frozenset[str]
    phrases: frozenset[str]
    documents: frozenset[str]
    works: frozenset[str]
    substrates: frozenset[str]
    qualities: frozenset[str]


def application_references() -> References:
    from app.domain.contracts.clauses import load_clause_catalog
    from app.domain.data.communication_phrases import (
        build_baseline_communication_phrases,
    )
    from app.domain.data.risk_rules import build_baseline_risk_rules
    from app.models.checklist import QualityLevel, Substrate
    from app.models.issued_document import IssuedDocumentKind
    from app.models.price_item import PriceCategory

    clauses = load_clause_catalog()
    return References(
        risks=frozenset(rule.code for rule in build_baseline_risk_rules()),
        clauses=frozenset(f"{section.key}.{clause.n}" for section in clauses.sections for clause in section.clauses),
        phrases=frozenset(phrase.code for phrase in build_baseline_communication_phrases()),
        documents=frozenset(kind.value for kind in IssuedDocumentKind),
        works=frozenset(category.value for category in PriceCategory),
        substrates=frozenset(substrate.value for substrate in Substrate),
        qualities=frozenset(level.value for level in QualityLevel),
    )


def _unique(name: str, codes: list[str]) -> None:
    seen: set[str] = set()
    for code in codes:
        if code in seen:
            raise KnowledgeCatalogError(f"{name}: duplicate {code!r}")
        seen.add(code)


def _check_situation(situation: Situation, entries: set[str], refs: References) -> None:
    where = f"situations.{situation.code}"
    questions = {q.id: q for q in situation.questions}
    outcomes = {o.id: o for o in situation.outcomes}
    _unique(f"{where} nodes", [*questions, *outcomes])
    if situation.start not in questions:
        raise KnowledgeCatalogError(f"{where}: start {situation.start!r} is not a question")
    for question in situation.questions:
        for answer in question.answers:
            if answer.next not in questions and answer.next not in outcomes:
                raise KnowledgeCatalogError(f"{where}.{question.id}: answer leads to unknown {answer.next!r}")
    # every node is reached from the start, and no path comes back to a question it has passed (the tree ends)
    reached: set[str] = set()

    def walk(node: str, path: tuple[str, ...]) -> None:
        if node in path:
            raise KnowledgeCatalogError(f"{where}: the answers come back to {node!r}")
        reached.add(node)
        if node in questions:
            for answer in questions[node].answers:
                walk(answer.next, (*path, node))

    walk(situation.start, ())
    unreached = sorted((set(questions) | set(outcomes)) - reached)
    if unreached:
        raise KnowledgeCatalogError(f"{where}: never reached {unreached}")
    for outcome in situation.outcomes:
        for code in outcome.entries:
            if code not in entries:
                raise KnowledgeCatalogError(f"{where}.{outcome.id}: unknown entry {code!r}")
        for code in outcome.phrases:
            if code not in refs.phrases:
                raise KnowledgeCatalogError(f"{where}.{outcome.id}: unknown phrase {code!r}")
        for code in outcome.documents:
            if code not in refs.documents:
                raise KnowledgeCatalogError(f"{where}.{outcome.id}: unknown document {code!r}")


def validate(catalog: KnowledgeCatalog, refs: References) -> KnowledgeCatalog:
    _unique("sources", [s.code for s in catalog.sources])
    _unique("entries", [e.code for e in catalog.entries])
    _unique("situations", [s.code for s in catalog.situations])
    sources = {s.code: s for s in catalog.sources}
    entries = {e.code for e in catalog.entries}
    for entry in catalog.entries:
        where = f"entries.{entry.code}"
        source = sources.get(entry.source)
        if source is None:
            raise KnowledgeCatalogError(f"{where}: unknown source {entry.source!r}")
        if entry.status == "APPROVED" and source.status != "APPROVED":
            raise KnowledgeCatalogError(f"{where}: approved, but its source {source.code!r} is not")
        if source.kind in REFERENCE_ONLY and (entry.summary_pl or entry.explanation_ru):
            raise KnowledgeCatalogError(f"{where}: a {source.kind} is referenced only -- no summary and no explanation")
        for field, allowed in (("works", refs.works), ("substrates", refs.substrates), ("qualities", refs.qualities)):
            unknown = sorted(set(getattr(entry, field)) - allowed)
            if unknown:
                raise KnowledgeCatalogError(f"{where}: unknown {field} {unknown}")
        for tag in entry.tags:
            if not _matches(TAG, tag):
                raise KnowledgeCatalogError(f"{where}: tag {tag!r} must be lowercase letters, digits, - or _")
        _unique(f"{where} review notes", [n.ref for n in entry.review_notes])
    for situation in catalog.situations:
        _check_situation(situation, entries, refs)
    allowed_targets = {"RISK": refs.risks, "CLAUSE": refs.clauses, "PHRASE": refs.phrases, "DOCUMENT": refs.documents}
    _unique("links", [f"{link.target_kind}:{link.target}" for link in catalog.links])
    for link in catalog.links:
        where = f"links.{link.target_kind}:{link.target}"
        if link.target not in allowed_targets[link.target_kind]:
            raise KnowledgeCatalogError(f"{where}: the application has no such {link.target_kind.lower()}")
        for code in link.entries:
            if code not in entries:
                raise KnowledgeCatalogError(f"{where}: unknown entry {code!r}")
        _unique(f"{where} entries", link.entries)
    if catalog.meta.disclaimer_status == "APPROVED" and not (catalog.meta.disclaimer_pl and catalog.meta.disclaimer_ru):
        raise KnowledgeCatalogError("meta: an approved disclaimer needs its Polish and Russian text")
    return catalog


def _matches(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None


def read_catalog(directory: Path, refs: References) -> KnowledgeCatalog:
    """Read and check the files of one directory (the repository's, or a test's)."""
    raw: dict[str, object] = {}
    for name, file_name in FILES.items():
        try:
            raw[name] = json.loads((directory / file_name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KnowledgeCatalogError(f"{file_name}: {exc}") from exc
    try:
        catalog = KnowledgeCatalog.model_validate(raw)
    except ValueError as exc:
        raise KnowledgeCatalogError(str(exc)) from exc
    return validate(catalog, refs)


@cache
def load_knowledge_catalog() -> KnowledgeCatalog:
    return read_catalog(CATALOG_DIR, application_references())
