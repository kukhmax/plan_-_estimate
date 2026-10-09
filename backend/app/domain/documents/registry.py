"""Registry of document templates (Stage 15B, 15G). Every template has a kind and a version; the version is written to the
journal of issued documents (15F), so an old document can always be traced to the layout that produced it.

A kind also knows the prefix of its number (`KOSZ/2026/10/08/1953`) and, for the contract and protocol skeletons of 15G, the
keys of the sections it is expected to have. The keys are internal identifiers: they carry no wording. The titles and the text
of the sections are written in Stage 16 / 17 and arrive as data; until then the skeleton prints "Sekcja 1", "Sekcja 2", ...
"""

import enum
from dataclasses import dataclass

from app.domain.exceptions import DocumentTemplateError


class DocumentKind(str, enum.Enum):
    DIAGNOSTIC = "DIAGNOSTIC"  # the control page: layout, Polish / Cyrillic glyphs, page numbering
    ESTIMATE = "ESTIMATE"  # Kosztorys (15D)
    PHOTO_REPORT = "PHOTO_REPORT"  # Raport fotograficzny (15E)
    CONTRACT = "CONTRACT"  # Umowa: data of the questionnaire, the annexes and the clause catalogue (16E)
    HANDOVER_PROTOCOL = "HANDOVER_PROTOCOL"  # Protokół przekazania terenu / obiektu: a skeleton (15G)
    CONCEALED_WORKS_PROTOCOL = "CONCEALED_WORKS_PROTOCOL"  # Protokół odbioru robót zanikających: a skeleton (15G)
    FINAL_PROTOCOL = "FINAL_PROTOCOL"  # Protokół odbioru końcowego: a skeleton (15G)
    PRODUCTION_PLAN = "PRODUCTION_PLAN"  # Plan produkcji prac: the sequence, the technological breaks, the works of others (16D)
    TECH_CARD = "TECH_CARD"  # Karta technologiczna: the substrate, the standard and the works of every surface (16C)


@dataclass(frozen=True, slots=True)
class DocumentTemplate:
    kind: DocumentKind
    version: str
    file: str
    number_prefix: str | None = None  # None: never numbered (the control page)
    sections: tuple[str, ...] = ()  # keys of the sections of a skeleton, in order (no wording: titles are data)


SKELETON_FILE = "skeleton.html.j2"
SKELETON_VERSION = "skeleton-1"

TEMPLATES: dict[DocumentKind, DocumentTemplate] = {
    DocumentKind.DIAGNOSTIC: DocumentTemplate(DocumentKind.DIAGNOSTIC, "1", "diagnostic.html.j2"),
    DocumentKind.ESTIMATE: DocumentTemplate(DocumentKind.ESTIMATE, "1", "estimate.html.j2", "KOSZ"),
    DocumentKind.PHOTO_REPORT: DocumentTemplate(DocumentKind.PHOTO_REPORT, "1", "photo_report.html.j2", "FOTO"),
    DocumentKind.TECH_CARD: DocumentTemplate(DocumentKind.TECH_CARD, "1", "tech_card.html.j2", "KART"),
    DocumentKind.PRODUCTION_PLAN: DocumentTemplate(DocumentKind.PRODUCTION_PLAN, "1", "production_plan.html.j2", "PLAN"),
    DocumentKind.CONTRACT: DocumentTemplate(
        DocumentKind.CONTRACT, "1", "contract.html.j2", "UMOWA",
        ("subject", "scope_of_work", "price", "schedule", "payment_terms", "acceptance", "downtime", "warranty", "penalty", "other_provisions"),
    ),
    DocumentKind.HANDOVER_PROTOCOL: DocumentTemplate(
        DocumentKind.HANDOVER_PROTOCOL, SKELETON_VERSION, SKELETON_FILE, "PRZEK",
        ("site_description", "condition_at_handover", "utilities_and_access", "remarks"),
    ),
    DocumentKind.CONCEALED_WORKS_PROTOCOL: DocumentTemplate(
        DocumentKind.CONCEALED_WORKS_PROTOCOL, SKELETON_VERSION, SKELETON_FILE, "ZANIK",
        ("works_covered", "inspection_result", "photo_evidence", "remarks"),
    ),
    DocumentKind.FINAL_PROTOCOL: DocumentTemplate(
        DocumentKind.FINAL_PROTOCOL, SKELETON_VERSION, SKELETON_FILE, "ODBIOR",
        ("scope_completed", "inspection_result", "defects_found", "deadlines_for_defects", "remarks"),
    ),
}

SKELETON_KINDS: tuple[DocumentKind, ...] = tuple(kind for kind, template in TEMPLATES.items() if template.file == SKELETON_FILE)


def get_template(kind: DocumentKind) -> DocumentTemplate:
    try:
        return TEMPLATES[kind]
    except KeyError:
        raise DocumentTemplateError(f"no template for {kind!r}") from None
