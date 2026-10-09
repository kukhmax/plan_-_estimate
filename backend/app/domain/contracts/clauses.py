"""The clause catalogue of the contract (Stage 16E.2): the **wording** of the contract, a server file the owner approves.

16E.2 gives the structure -- the ten sections of the contract in their order with their Polish titles -- and leaves the paragraphs
**empty**: a section without paragraphs prints "— do uzupełnienia —". The wording (16E.3) is written by the owner and checked by a
lawyer; until the catalogue is `approved` (with who and when), every issued contract is printed with the "WERSJA ROBOCZA"
watermark. The version of the catalogue and its approval state are written into the snapshot of an issued contract, so a dispute
can always say which wording the customer had. Nothing here is legal advice and nothing is generated.
"""

import json
from datetime import date
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.documents.registry import DocumentKind, get_template
from app.domain.exceptions import DocumentDataError

CLAUSES_FILE = Path(__file__).resolve().parent / "catalog" / "clauses.json"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClauseSection(_Model):
    key: str = Field(pattern=r"^[a-z]+(_[a-z]+)*$")
    title_pl: str = Field(min_length=3)
    paragraphs_pl: list[str]


class ClauseCatalog(_Model):
    version: int = Field(ge=1)
    approved: bool
    approved_by: str | None
    approved_on: date | None
    sections: list[ClauseSection]

    @model_validator(mode="after")
    def _approval_is_complete_and_sections_match_the_contract(self) -> "ClauseCatalog":
        if self.approved and not (self.approved_by and self.approved_on):
            raise ValueError("an approved catalogue names who approved it and when")
        if not self.approved and (self.approved_by or self.approved_on):
            raise ValueError("an unapproved catalogue carries no approval")
        expected = list(get_template(DocumentKind.CONTRACT).sections)
        if [s.key for s in self.sections] != expected:
            raise ValueError(f"the sections of the catalogue must be exactly {expected} in this order")
        if self.approved and any(not s.paragraphs_pl or any(not p.strip() for p in s.paragraphs_pl) for s in self.sections):
            raise ValueError("an approved catalogue has wording in every section")
        return self


@cache
def load_clause_catalog() -> ClauseCatalog:
    try:
        return ClauseCatalog.model_validate(json.loads(CLAUSES_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise DocumentDataError("CATALOG_INVALID", f"clauses.json: {exc}") from exc
