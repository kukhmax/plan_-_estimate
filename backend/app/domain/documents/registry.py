"""Registry of document templates (Stage 15B, 16). Every template has a kind and a version; the version is written to the
journal of issued documents (15F), so an old document can always be traced to the layout that produced it.

A kind also knows the prefix of its number (`KOSZ/2026/10/08/1953`) and, for the contract, the keys of its sections. The keys are
internal identifiers: they carry no wording. (The skeletons of 15G, a common template with empty sections, are gone: every kind has
its own template since the final acceptance protocol of 16H.)
"""

import enum
from dataclasses import dataclass

from app.domain.exceptions import DocumentTemplateError


class DocumentKind(str, enum.Enum):
    DIAGNOSTIC = "DIAGNOSTIC"  # the control page: layout, Polish / Cyrillic glyphs, page numbering
    ESTIMATE = "ESTIMATE"  # Kosztorys (15D)
    PHOTO_REPORT = "PHOTO_REPORT"  # Raport fotograficzny (15E)
    CONTRACT = "CONTRACT"  # Umowa: data of the questionnaire, the annexes and the clause catalogue (16E)
    HANDOVER_PROTOCOL = "HANDOVER_PROTOCOL"  # Protokół przekazania pomieszczeń: the state of each room against the requirements (16F)
    CONCEALED_WORKS_PROTOCOL = "CONCEALED_WORKS_PROTOCOL"  # Protokół odbioru robót zanikających: work accepted before it is covered (16G)
    FINAL_PROTOCOL = "FINAL_PROTOCOL"  # Protokół odbioru końcowego / częściowego: the assessment of the work against the contract (16H)
    DECISION_PROTOCOL = "DECISION_PROTOCOL"  # Protokół informacji i decyzji Zamawiającego: a recommendation declined or overruled (16I)
    PRODUCTION_PLAN = "PRODUCTION_PLAN"  # Plan produkcji prac: the sequence, the technological breaks, the works of others (16D)
    TECH_CARD = "TECH_CARD"  # Karta technologiczna: the substrate, the standard and the works of every surface (16C)


@dataclass(frozen=True, slots=True)
class DocumentTemplate:
    kind: DocumentKind
    version: str
    file: str
    number_prefix: str | None = None  # None: never numbered (the control page)
    sections: tuple[str, ...] = ()  # keys of the sections of a contract, in order (no wording: titles are data)


TEMPLATES: dict[DocumentKind, DocumentTemplate] = {
    DocumentKind.DIAGNOSTIC: DocumentTemplate(DocumentKind.DIAGNOSTIC, "1", "diagnostic.html.j2"),
    DocumentKind.ESTIMATE: DocumentTemplate(DocumentKind.ESTIMATE, "1", "estimate.html.j2", "KOSZ"),
    DocumentKind.PHOTO_REPORT: DocumentTemplate(DocumentKind.PHOTO_REPORT, "1", "photo_report.html.j2", "FOTO"),
    DocumentKind.TECH_CARD: DocumentTemplate(DocumentKind.TECH_CARD, "1", "tech_card.html.j2", "KART"),
    DocumentKind.PRODUCTION_PLAN: DocumentTemplate(DocumentKind.PRODUCTION_PLAN, "1", "production_plan.html.j2", "PLAN"),
    DocumentKind.CONTRACT: DocumentTemplate(
        DocumentKind.CONTRACT, "2", "contract.html.j2", "UMOWA",
        (
            "definitions", "subject", "state_of_premises", "remuneration", "additional_works", "advance_and_payments", "deadlines",
            "cooperation", "other_contractors", "downtime", "materials", "organisation", "concealed_works", "acceptance",
            "evaluation_rules", "warranty", "executor_recommendations", "liability", "withdrawal", "consumer_withdrawal",
            "communication", "personal_data", "final_provisions",
        ),
    ),
    DocumentKind.HANDOVER_PROTOCOL: DocumentTemplate(DocumentKind.HANDOVER_PROTOCOL, "1", "handover_protocol.html.j2", "PRZEK"),
    DocumentKind.CONCEALED_WORKS_PROTOCOL: DocumentTemplate(
        DocumentKind.CONCEALED_WORKS_PROTOCOL, "1", "concealed_works_protocol.html.j2", "ZANIK"
    ),
    DocumentKind.FINAL_PROTOCOL: DocumentTemplate(DocumentKind.FINAL_PROTOCOL, "1", "acceptance_protocol.html.j2", "ODBIOR"),
    DocumentKind.DECISION_PROTOCOL: DocumentTemplate(DocumentKind.DECISION_PROTOCOL, "1", "decision_protocol.html.j2", "DECYZ"),
}


def get_template(kind: DocumentKind) -> DocumentTemplate:
    try:
        return TEMPLATES[kind]
    except KeyError:
        raise DocumentTemplateError(f"no template for {kind!r}") from None
