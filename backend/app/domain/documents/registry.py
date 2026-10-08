"""Registry of document templates (Stage 15B). Every template has a kind and a version; the version is written to the
journal of issued documents (15F), so an old document can always be traced to the layout that produced it."""

import enum
from dataclasses import dataclass

from app.domain.exceptions import DocumentTemplateError


class DocumentKind(str, enum.Enum):
    DIAGNOSTIC = "DIAGNOSTIC"  # the control page: layout, Polish / Cyrillic glyphs, page numbering
    ESTIMATE = "ESTIMATE"  # Kosztorys (15D)
    PHOTO_REPORT = "PHOTO_REPORT"  # Raport fotograficzny (15E)
    # The contract / protocol skeletons (15G) are added with their templates.


@dataclass(frozen=True, slots=True)
class DocumentTemplate:
    kind: DocumentKind
    version: str
    file: str


TEMPLATES: dict[DocumentKind, DocumentTemplate] = {
    DocumentKind.DIAGNOSTIC: DocumentTemplate(DocumentKind.DIAGNOSTIC, "1", "diagnostic.html.j2"),
    DocumentKind.ESTIMATE: DocumentTemplate(DocumentKind.ESTIMATE, "1", "estimate.html.j2"),
    DocumentKind.PHOTO_REPORT: DocumentTemplate(DocumentKind.PHOTO_REPORT, "1", "photo_report.html.j2"),
}


def get_template(kind: DocumentKind) -> DocumentTemplate:
    try:
        return TEMPLATES[kind]
    except KeyError:
        raise DocumentTemplateError(f"no template for {kind!r}") from None
