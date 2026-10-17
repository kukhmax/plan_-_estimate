"""The statement of settlements (Rozliczenie) as a document for the client (invoices and advances, IA-6a).

It says what was invoiced to the client, what the client paid (advances and payments, each with the invoice it settles) and what is
left. It is made from the settlement records of the object and from them only: **the expenses on materials are the owner's own costs
and never reach this document** (a test pins it). It is a statement for information, not an invoice and not an accounting document;
the page says so in its own words.

Two forms of one document, like the technological card:

* **issued** (`working=False`): numbered (ROZL/...), journalled, no watermark. It is refused with a stable code while there is nothing to
  state (no invoice and no payment of the object), so a numbered statement is never empty;
* **working** (`working=True`): a draft with the "WERSJA ROBOCZA" watermark, no number, no journal row; it never refuses.

Every sum is the one of `domain/rules/payment_totals.py` (the same that the screen shows): this module formats, it never adds. The words
are Polish labels (`locales/pl.json`).
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
from app.domain.rules.payment_totals import INVOICE, MONEY_IN, Entry, invoice_standings, summarize
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.project_service import ProjectService
from app.models.client import Client
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project
from app.models.project_payment import ProjectFinance, ProjectPayment


@dataclass(frozen=True, slots=True)
class InvoiceRow:
    number: str  # the number written on the invoice, else its subject
    title: str
    issued_on: date
    due_on: date | None
    gross: str
    settled: str
    remaining: str
    state: str  # a word of the document ("Opłacona")


@dataclass(frozen=True, slots=True)
class MoneyRow:
    day: date
    kind: str  # "Zaliczka" / "Wpłata"
    title: str
    amount: str
    invoice: str | None  # the invoice it settles, by its number


@dataclass(frozen=True, slots=True)
class SettlementTotals:
    agreed: str | None
    invoiced: str
    received: str
    unpaid: str  # what is still to be paid of the invoices
    left_label: str | None  # "Pozostało do zapłaty z umówionej kwoty" or "Nadpłata"
    left: str | None


@dataclass(frozen=True, slots=True)
class SettlementDocument:
    layout: DocumentLayout
    object_name: str
    object_lines: tuple[str, ...]
    as_of: date
    invoices: tuple[InvoiceRow, ...]
    money: tuple[MoneyRow, ...]
    totals: SettlementTotals
    working: bool

    def context(self) -> dict[str, object]:
        return {"layout": self.layout, "doc": self}


@dataclass(frozen=True, slots=True)
class Sources:
    project: Project
    client: Client | None
    payments: tuple[ProjectPayment, ...]
    agreed: Decimal | None


def _entry(row: ProjectPayment) -> Entry:
    return Entry(row.id, row.kind, row.amount_gross, row.due_on, row.settles_id, row.is_archived)


def build_settlement_document(
    sources: Sources,
    executor: ExecutorProfile | None,
    *,
    working: bool,
    issued_on: date,
    number: str | None = None,
    sequence: int | None = None,
) -> SettlementDocument:
    if working and number is not None:
        raise DocumentDataError("DRAFT_NUMBERED", "a working version is never numbered")
    if executor is None and not working:
        raise DocumentDataError("EXECUTOR_PROFILE_REQUIRED", "fill in the executor profile before issuing a statement of settlements")
    labels = Labels()
    # archived records count for nothing and are not printed; only invoices and money received are taken, so the owner's own expenses never are
    live = [row for row in sources.payments if not row.is_archived]
    invoices = sorted((row for row in live if row.kind == INVOICE), key=lambda row: (row.occurred_on, row.created_at, str(row.id)))
    money = sorted((row for row in live if row.kind in MONEY_IN), key=lambda row: (row.occurred_on, row.created_at, str(row.id)))
    if not working and not invoices and not money:
        raise DocumentDataError("SETTLEMENT_EMPTY", "the object has no invoice and no payment to state yet")

    entries = [_entry(row) for row in sources.payments]
    standings = invoice_standings(entries, issued_on)
    summary = summarize(entries, sources.agreed, issued_on)
    name_of = {row.id: (row.number or row.title) for row in invoices}
    states = {
        "PAID": labels("settlement.state.paid"), "PARTIAL": labels("settlement.state.partial"),
        "OVERDUE": labels("settlement.state.overdue"), "OPEN": labels("settlement.state.open"),
    }
    kinds = {"ADVANCE": labels("settlement.kind.advance"), "PAYMENT": labels("settlement.kind.payment")}
    invoice_rows = tuple(
        InvoiceRow(
            number=row.number or labels("settlement.no_number"),
            title=row.title,
            issued_on=row.occurred_on,
            due_on=row.due_on,
            gross=formatting.format_money(row.amount_gross),
            settled=formatting.format_money(standings[row.id].settled),
            remaining=formatting.format_money(standings[row.id].remaining),
            state=states[standings[row.id].state],
        )
        for row in invoices
    )
    money_rows = tuple(
        MoneyRow(row.occurred_on, kinds[row.kind], row.title, formatting.format_money(row.amount_gross), name_of.get(row.settles_id) if row.settles_id else None)
        for row in money
    )
    left_label = left = None
    if summary.to_receive is not None:
        # the sign decides the words only; the number is the server's own
        left_label = labels("settlement.overpaid") if summary.to_receive < 0 else labels("settlement.left")
        left = formatting.format_money(abs(summary.to_receive))
    totals = SettlementTotals(
        agreed=formatting.format_money(sources.agreed) if sources.agreed is not None else None,
        invoiced=formatting.format_money(summary.invoiced),
        received=formatting.format_money(summary.received),
        unpaid=formatting.format_money(summary.invoiced_unpaid),
        left_label=left_label,
        left=left,
    )
    layout = DocumentLayout(
        meta=DocumentMeta(
            title=labels("settlement.title"),
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
    return SettlementDocument(layout, sources.project.name, object_lines(sources.project), issued_on, invoice_rows, money_rows, totals, working)


class SettlementDocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sources(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> Sources:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        project = (await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one()
        client = None
        if project.client_id is not None:
            client = (
                await self.db.execute(select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id))
            ).scalar_one_or_none()
        payments = tuple(
            (await self.db.execute(select(ProjectPayment).where(ProjectPayment.project_id == project_id, ProjectPayment.owner_id == owner_id))).scalars()
        )
        agreed = (await self.db.execute(select(ProjectFinance.agreed_amount).where(ProjectFinance.project_id == project_id))).scalar_one_or_none()
        return Sources(project, client, payments, agreed)

    async def build(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, *, working: bool, issued_on: date, number: str | None = None, sequence: int | None = None
    ) -> SettlementDocument:
        sources = await self.sources(owner_id, project_id)
        executor = await ExecutorProfileService(self.db).get(owner_id)
        return build_settlement_document(sources, executor, working=working, issued_on=issued_on, number=number, sequence=sequence)

    @staticmethod
    def html(document: SettlementDocument) -> str:
        return render_html(get_template(DocumentKind.SETTLEMENT), document.context())

    async def render(self, owner_id: uuid.UUID, project_id: uuid.UUID, renderer: DocumentRenderer, **kwargs) -> RenderedPdf:
        document = await self.build(owner_id, project_id, **kwargs)
        return await renderer.render(self.html(document))
