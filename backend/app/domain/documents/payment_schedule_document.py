"""The payment schedule (Harmonogram płatności) as a document for the client (V2-9a).

It says in which stages the client pays, how much, by when, and where each stage stands on the day of the document. It is made from the
stages of the schedule (`domain/rules/payment_schedule.py`, the same numbers as the screen "Etapy") and from them only: **the owner's own expenses,
hours and margin never reach this document** (a test pins it). It is a statement of the agreed payments for information, not an invoice and not an
accounting document; the page says so in its own words.

Two forms of one document, like the statement of settlements:

* **issued** (`working=False`): numbered (HPL/...), journalled, no watermark. Refused with a stable code while the object has no stage
  (`PAYMENT_SCHEDULE_EMPTY`) or a stage is a share of an agreed amount that is not set (`PAYMENT_SCHEDULE_UNPRICED`: a numbered document never
  prints an amount that is not known), and while the executor profile is empty (`EXECUTOR_PROFILE_REQUIRED`);
* **working** (`working=True`): the "WERSJA ROBOCZA" watermark, no number, no journal row; it never refuses (an unknown amount prints as "do ustalenia").

Every sum is the server's (`PaymentScheduleService`): this module formats, it never adds money of its own except the display of the gap against the
agreed amount, which the rule has already made. The words are Polish labels (`locales/pl.json`).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents import formatting
from app.domain.documents.estimate_document import object_lines, party_from_client
from app.domain.documents.labels import Labels
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.renderer import DocumentRenderer, RenderedPdf
from app.domain.documents.templating import render_html
from app.domain.exceptions import DocumentDataError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.payment_schedule_service import (
    PaymentScheduleService,
    Schedule,
)
from app.domain.services.project_service import ProjectService
from app.models.client import Client
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project

DASH = "—"


@dataclass(frozen=True, slots=True)
class StageRow:
    number: int
    title: str
    share: str  # "30%" or a dash for a fixed amount
    amount: str  # "12 000,00 zł", or "do ustalenia" while a share has no agreed amount (the working form only)
    due: date | None
    paid: str
    left: str
    state: str  # a word of the document ("Zapłacony")


@dataclass(frozen=True, slots=True)
class ScheduleTotals:
    agreed: str | None
    total: str  # the stages whose amount is known
    received: str
    left: str | None  # still to be paid by the stages; None while some stage has no amount
    note: str | None  # the agreed amount is not covered by the stages / the stages are above it


@dataclass(frozen=True, slots=True)
class PaymentScheduleDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    as_of: date
    stages: tuple[StageRow, ...]
    totals: ScheduleTotals
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


@dataclass(frozen=True, slots=True)
class Sources:
    project: Project
    client: Client | None
    schedule: Schedule


def _percent(value: Decimal) -> str:
    """"30%", "33,5%": the share as the owner typed it, no empty places."""
    return f"{format(value.normalize(), 'f').replace('.', ',')}%"


def build_payment_schedule_document(
    sources: Sources,
    executor: ExecutorProfile | None,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> PaymentScheduleDocument:
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing the payment schedule")
    items, summary = sources.schedule.items, sources.schedule.summary
    if not working and not items:
        raise DocumentDataError("PAYMENT_SCHEDULE_EMPTY", "the object has no stage of the payment schedule yet")
    if not working and summary.unpriced:
        raise DocumentDataError(
            "PAYMENT_SCHEDULE_UNPRICED",
            "a stage is a share of an agreed amount that is not set",
            {"count": summary.unpriced},
        )
    labels = Labels()
    states = {
        "PAID": labels("payment_schedule.state.paid"), "PARTIAL": labels("payment_schedule.state.partial"),
        "OVERDUE": labels("payment_schedule.state.overdue"), "OPEN": labels("payment_schedule.state.open"),
    }
    rows = tuple(
        StageRow(
            number=index,
            title=view.stage.title,
            share=_percent(view.stage.percent) if view.stage.percent is not None else DASH,
            amount=formatting.format_money(view.standing.amount) if view.standing.amount is not None else labels("payment_schedule.unpriced"),
            due=view.stage.due_on,
            paid=formatting.format_money(view.standing.received),
            left=formatting.format_money(view.standing.remaining) if view.standing.remaining is not None else DASH,
            state=states[view.standing.state],
        )
        for index, view in enumerate(items, start=1)
    )
    note = None
    difference = summary.difference
    if difference is not None and not summary.unpriced and items:
        if difference > 0:
            note = labels("payment_schedule.gap", amount=formatting.format_money(difference))
        elif difference < 0:
            note = labels("payment_schedule.over", amount=formatting.format_money(-difference))
    totals = ScheduleTotals(
        agreed=formatting.format_money(summary.agreed) if summary.agreed is not None else None,
        total=formatting.format_money(summary.stages_total),
        received=formatting.format_money(summary.received),
        left=formatting.format_money(summary.to_receive) if summary.to_receive is not None else None,
        note=note,
    )
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("payment_schedule.title"),
            issued_on=issued_on,
            number=number,
            place=(executor.city or None) if executor is not None else None,
            sequence=sequence,
        ),
        executor=party_from_executor_profile(executor) if executor is not None else None,
        client=party_from_client(sources.client) if sources.client is not None else None,
        signatures=False,
        draft=working,
        light_watermark=False,
    )
    return PaymentScheduleDocument(layout, sources.project.name, object_lines(sources.project), issued_on, rows, totals, working)


class PaymentScheduleDocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sources(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, today: date) -> Sources:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        project = (await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one()
        client = None
        if project.client_id is not None:
            client = (
                await self.db.execute(select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id))
            ).scalar_one_or_none()
        return Sources(project, client, await PaymentScheduleService(self.db).schedule(owner_id, project_id, today=today))

    async def build(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, *, working: bool, issued_on: date, number: str | None = None, sequence: int | None = None
    ) -> PaymentScheduleDocument:
        sources = await self.sources(owner_id, project_id, today=issued_on)
        executor = await ExecutorProfileService(self.db).get(owner_id)
        return build_payment_schedule_document(sources, executor, working=working, issued_on=issued_on, number=number, sequence=sequence)

    @staticmethod
    def html(document: PaymentScheduleDocument) -> str:
        return render_html(get_template(DocumentKind.PAYMENT_SCHEDULE), document.context())

    async def render(self, owner_id: uuid.UUID, project_id: uuid.UUID, renderer: DocumentRenderer, **kwargs) -> RenderedPdf:
        document = await self.build(owner_id, project_id, **kwargs)
        return await renderer.render(self.html(document))
