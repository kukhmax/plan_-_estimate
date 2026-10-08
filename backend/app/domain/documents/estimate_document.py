"""The estimate (Kosztorys) as a document (Stage 15D).

`build_estimate_document` is pure: it turns the stored snapshot of an estimate into what the template prints and checks
that the print can be trusted -- the lines add up to the stored total, nothing priced in a second currency, no raw
translation key reaches the client. The template only prints; every number it shows is a stored snapshot value (no price
is computed here, only the sums of the stored line amounts that must match the stored total).

No VAT: the document shows the final price for the client (owner decision 2026-10-08).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.catalog import localize_description
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta, Party
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.rules.polish_identifiers import format_nip, normalize_nip
from app.domain.services.estimate_service import EstimateService
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.client import Client
from app.models.estimate import EstimateStatus
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project
from app.schemas.estimate import EstimateRead


@dataclass(frozen=True, slots=True)
class EstimateLineView:
    number: int
    description: str
    detail: str | None
    unit: str
    quantity: Decimal
    unit_price: Decimal | None
    amount: Decimal | None


@dataclass(frozen=True, slots=True)
class EstimateGroupView:
    title: str | None  # the room; None = lines that belong to no room
    lines: tuple[EstimateLineView, ...]
    subtotal: Decimal | None  # None while any line of the group has no price


@dataclass(frozen=True, slots=True)
class EstimateDocument:
    layout: DocumentLayout
    name: str | None
    version: int
    object_name: str
    object_lines: tuple[str, ...]
    groups: tuple[EstimateGroupView, ...]
    total: Decimal | None
    currency: str

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


def party_from_client(client: Client) -> Party:
    """The client block: a company by its name, a private person by first and last name."""
    person = " ".join(part for part in (client.first_name, client.last_name) if part)
    name = client.company_name or person or "—"
    tax_id = None
    if client.nip:
        try:
            tax_id = format_nip(normalize_nip(client.nip))
        except ValueError:
            tax_id = client.nip  # stored as the owner typed it; print it, do not hide it
    return Party(name=name, tax_id=tax_id, phone=client.phone, email=client.email)


def object_lines(project: Project) -> tuple[str, ...]:
    city_line = " ".join(part for part in (project.postal_code, project.city) if part)
    return tuple(line for line in (project.address, city_line) if line)


def build_estimate_document(
    estimate: EstimateRead,
    project: Project,
    client: Client | None,
    executor: ExecutorProfile | None,
    *,
    issued_on: date,
    number: str | None = None,
) -> EstimateDocument:
    if estimate.status is EstimateStatus.ARCHIVED:
        raise DocumentDataError("ESTIMATE_ARCHIVED", "an archived estimate cannot be printed")
    draft = estimate.status is EstimateStatus.DRAFT
    if draft and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if executor is None and not draft:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing an estimate")
    if not estimate.lines:
        raise DocumentDataError("ESTIMATE_EMPTY", "an estimate without lines cannot be printed")
    if any(line.currency != estimate.currency for line in estimate.lines):
        raise DocumentDataError("ESTIMATE_CURRENCY_MIXED", "lines in more than one currency cannot be added up")

    unpriced = any(line.amount is None or line.unit_price is None for line in estimate.lines)
    if unpriced and not draft:
        raise DocumentDataError("ESTIMATE_UNPRICED", "an issued estimate has no line without a price")
    total: Decimal | None = None
    if not unpriced:
        total = sum((line.amount for line in estimate.lines if line.amount is not None), Decimal(0))
        if estimate.total != total:
            raise DocumentDataError("ESTIMATE_TOTAL_MISMATCH", "the stored total does not equal the sum of the lines")

    order: list[str | None] = []
    members: dict[str | None, list] = {}
    for line in sorted(estimate.lines, key=lambda item: item.position):
        room = line.room_name or None
        if room not in members:
            order.append(room)
            members[room] = []
        members[room].append(line)

    groups: list[EstimateGroupView] = []
    counter = 0
    for room in order:
        views = []
        for line in members[room]:
            counter += 1
            detail = " · ".join(part for part in (line.surface_name, line.opening_name) if part) or None
            views.append(
                EstimateLineView(
                    number=counter,
                    description=localize_description(line.description),
                    detail=detail,
                    unit=line.unit.value,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    amount=line.amount,
                )
            )
        subtotal = None if any(v.amount is None for v in views) else sum((v.amount for v in views), Decimal(0))
        groups.append(EstimateGroupView(title=room, lines=tuple(views), subtotal=subtotal))

    meta = DocumentMeta(
        title=Labels()("estimate.title"),
        issued_on=issued_on,
        number=number,
        place=executor.city if executor and executor.city else None,
    )
    layout = DocumentLayout(
        meta=meta,
        executor=party_from_executor_profile(executor) if executor else None,
        client=party_from_client(client) if client else None,
        draft=draft,
    )
    return EstimateDocument(
        layout=layout,
        name=estimate.name,
        version=estimate.version,
        object_name=project.name,
        object_lines=object_lines(project),
        groups=tuple(groups),
        total=total,
        currency=estimate.currency,
    )


class EstimateDocumentService:
    """Loads one estimate of the caller and prints it. Owner scoping is the estimate service's: a foreign or unknown
    estimate is `EstimateNotFoundError`, exactly as for the estimate screens."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        project_id: uuid.UUID,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        issued_on: date,
        number: str | None = None,
    ) -> EstimateDocument:
        estimate = await EstimateService(self.db).get_estimate_read_with_provenance(project_id, estimate_id, owner_id)
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
        return build_estimate_document(estimate, project, client, executor, issued_on=issued_on, number=number)

    @staticmethod
    def html(document: EstimateDocument) -> str:
        return render_html(get_template(DocumentKind.ESTIMATE), document.context())

    async def render(
        self,
        project_id: uuid.UUID,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        renderer: DocumentRenderer,
        *,
        issued_on: date,
        number: str | None = None,
    ) -> RenderedPdf:
        document = await self.build(project_id, estimate_id, owner_id, issued_on=issued_on, number=number)
        return await renderer.render(self.html(document))
