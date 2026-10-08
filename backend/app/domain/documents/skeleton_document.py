"""Skeletons of the contract and the protocols (Stage 15G): the structure of a document, with no legal text.

Contracts and protective protocols are Stage 16, the legal knowledge they quote is Stage 17. What 15G gives them is everything
around the words: the header with the number and the date, the executor and the client, the object, numbered sections, a list
of attachments and the signature block, on pages with the same footer and numbering as every other document.

Nothing in a skeleton is wording of a contract. The sections have **no title and no text** of their own: each prints "Sekcja n"
and "— do uzupełnienia —" until the caller supplies a title and paragraphs as data (Stage 16 reads them from the backend's
knowledge base, never from a screen). The titles of the documents themselves are only their names ("Umowa", "Protokół
przekazania", ...). `tests/test_stage15g_skeleton.py` keeps it that way: no clause-like word in a skeleton's labels or template.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.estimate_document import object_lines, party_from_client
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import SKELETON_KINDS, DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError, DocumentTemplateError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.client import Client
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project


@dataclass(frozen=True, slots=True)
class SectionContent:
    """What the caller (Stage 16) supplies for one section: a title and paragraphs, both optional."""

    title: str | None = None
    paragraphs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SectionView:
    key: str
    number: int
    title: str | None
    paragraphs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkeletonDocument:
    kind: DocumentKind
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    sections: tuple[SectionView, ...]
    attachments: tuple[str, ...]

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def document_title(kind: DocumentKind) -> str:
    labels = Labels()
    titles = {
        DocumentKind.CONTRACT: labels("skeleton.title.contract"),
        DocumentKind.HANDOVER_PROTOCOL: labels("skeleton.title.handover"),
        DocumentKind.CONCEALED_WORKS_PROTOCOL: labels("skeleton.title.concealed"),
        DocumentKind.FINAL_PROTOCOL: labels("skeleton.title.final"),
    }
    try:
        return titles[kind]
    except KeyError:
        raise DocumentTemplateError(f"{kind!r} is not a skeleton kind") from None


def build_skeleton_document(
    kind: DocumentKind,
    project: Project,
    client: Client | None,
    executor: ExecutorProfile | None,
    *,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
    content: Mapping[str, SectionContent] | None = None,
    attachments: Sequence[str] = (),
) -> SkeletonDocument:
    if kind not in SKELETON_KINDS:
        raise DocumentTemplateError(f"{kind!r} is not a skeleton kind")
    if executor is None:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a document")
    template = get_template(kind)
    content = content or {}
    unknown = sorted(set(content) - set(template.sections))
    if unknown:
        raise DocumentDataError(
            "SKELETON_SECTION_UNKNOWN",
            f"{kind.value} has no section {', '.join(unknown)}",
            {"unknown": unknown, "known": list(template.sections)},
        )
    sections = tuple(
        SectionView(
            key=key,
            number=n,
            title=(content[key].title or None) if key in content else None,
            paragraphs=tuple(p for p in content[key].paragraphs if p.strip()) if key in content else (),
        )
        for n, key in enumerate(template.sections, start=1)
    )
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=document_title(kind),
            issued_on=issued_on,
            number=number,
            place=executor.city or None,
            sequence=sequence,
        ),
        executor=party_from_executor_profile(executor),
        client=party_from_client(client) if client else None,
        signatures=True,
    )
    return SkeletonDocument(
        kind=kind,
        layout=layout,
        object_name=project.name,
        object_lines=object_lines(project),
        sections=sections,
        attachments=tuple(attachments),
    )


class SkeletonDocumentService:
    """Loads the object, the client and the executor of the caller and builds / prints a skeleton. Owner scoping is the
    project's: a foreign or unknown project is `ProjectNotFoundError`, exactly as for the other documents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        kind: DocumentKind,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        issued_on: date,
        number: str | None = None,
        sequence: int | None = None,
        content: Mapping[str, SectionContent] | None = None,
        attachments: Sequence[str] = (),
    ) -> SkeletonDocument:
        from app.domain.services.project_service import ProjectService

        await ProjectService(self.db).get_project(project_id, owner_id)
        project = (
            await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        ).scalar_one()
        client = None
        if project.client_id is not None:
            client = (
                await self.db.execute(
                    select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id)
                )
            ).scalar_one_or_none()
        executor = await ExecutorProfileService(self.db).get(owner_id)
        return build_skeleton_document(
            kind, project, client, executor, issued_on=issued_on, number=number, sequence=sequence,
            content=content, attachments=attachments,
        )

    @staticmethod
    def html(document: SkeletonDocument) -> str:
        return render_html(get_template(document.kind), document.context())

    async def render(
        self, kind: DocumentKind, owner_id: uuid.UUID, project_id: uuid.UUID, renderer: DocumentRenderer, **kwargs
    ) -> RenderedPdf:
        document = await self.build(kind, owner_id, project_id, **kwargs)
        return await renderer.render(self.html(document))
