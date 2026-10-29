"""The settlements of an object (invoices and advances, IA-1): invoices issued to the client, money taken from the client, expenses on materials.

Every call is owner-scoped. A record is created under an id chosen by the phone and is safe to repeat (`client_ids.find_repeat`, Stage 19C); a record
is archived, never erased (it is accounting) and goes with its object. The rules of a kind are checked here (the database repeats them as CHECKs); every
total is made by `domain/rules/payment_totals.py`.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    PaymentInvalidError,
    PaymentNotFoundError,
    ProjectNotFoundError,
)
from app.domain.rules.payment_totals import (
    Entry,
    InvoiceStanding,
    Summary,
    invoice_standings,
    summarize,
)
from app.domain.services.calendar_service import CalendarService
from app.domain.services.client_ids import find_repeat
from app.models.estimate import Estimate, EstimateStatus
from app.models.payment_stage import PaymentStage
from app.models.project import Project
from app.models.project_payment import ProjectFinance, ProjectPayment

MONEY_IN = ("ADVANCE", "PAYMENT")
# the columns an update may change (the kind and the owner never change)
EDITABLE = (
    "title", "number", "amount_gross", "amount_net", "vat_rate", "occurred_on", "due_on", "settles_id", "stage_id", "counterparty", "document_kind", "category", "note",
)


@dataclass(frozen=True, slots=True)
class PaymentList:
    items: list[ProjectPayment]
    standings: dict[Any, InvoiceStanding]
    summary: Summary
    total: int


@dataclass(frozen=True, slots=True)
class AgreedSuggestion:
    amount: Decimal
    estimate_id: uuid.UUID
    estimate_version: int
    status: str


@dataclass(frozen=True, slots=True)
class FinanceView:
    agreed_amount: Decimal | None
    currency: str
    suggestion: AgreedSuggestion | None


def _entry(row: ProjectPayment) -> Entry:
    return Entry(
        id=row.id, kind=row.kind, amount_gross=row.amount_gross, due_on=row.due_on, settles_id=row.settles_id, is_archived=row.is_archived, category=row.category
    )


def _clean_text(value: str | None, *, required: bool = False) -> str | None:
    text = (value or "").strip()
    if not text:
        if required:
            raise PaymentInvalidError("title is required")
        return None
    return text


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _get(self, owner_id: uuid.UUID, project_id: uuid.UUID, payment_id: uuid.UUID) -> ProjectPayment:
        await self._ensure_project(owner_id, project_id)
        row = (await self.db.execute(
            select(ProjectPayment).where(ProjectPayment.id == payment_id, ProjectPayment.project_id == project_id, ProjectPayment.owner_id == owner_id)
        )).scalar_one_or_none()
        if row is None:
            raise PaymentNotFoundError(f"Payment {payment_id} not found")
        return row

    async def _all(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[ProjectPayment]:
        return list((await self.db.execute(
            select(ProjectPayment).where(ProjectPayment.project_id == project_id, ProjectPayment.owner_id == owner_id)
            .order_by(ProjectPayment.occurred_on.desc(), ProjectPayment.created_at.desc(), ProjectPayment.id.desc())
        )).scalars())

    async def _calendar_follows(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        """A change of a record can move, add or take away the due day of an invoice (IA-5): the reminders follow at once. A fault in the
        calendar is logged and never undoes the record (the periodic reconciliation brings the queue right again)."""
        await self.db.flush()
        await CalendarService(self.db).reconcile_project_guarded(owner_id, project_id)

    # -- the rules of a kind --------------------------------------------------------

    async def _check(self, owner_id: uuid.UUID, project_id: uuid.UUID, own_id: uuid.UUID, kind: str, f: dict[str, Any]) -> None:
        if f["amount_net"] is not None and f["amount_net"] > f["amount_gross"]:
            raise PaymentInvalidError("the net amount cannot be above the gross amount")
        if f["due_on"] is not None and kind != "INVOICE":
            raise PaymentInvalidError("only an invoice has a due date")
        if (f["counterparty"] is not None or f["document_kind"] is not None) and kind != "EXPENSE":
            raise PaymentInvalidError("only an expense has a shop / supplier and a kind of document")
        if f["category"] is not None and kind != "EXPENSE":
            raise PaymentInvalidError("only an expense has a category")
        if f.get("stage_id") is not None:
            if kind not in MONEY_IN:
                raise PaymentInvalidError("only an advance or a payment can belong to a stage of the schedule")
            stage = (await self.db.execute(
                select(PaymentStage.id).where(PaymentStage.id == f["stage_id"], PaymentStage.project_id == project_id, PaymentStage.owner_id == owner_id)
            )).scalar_one_or_none()
            if stage is None:
                raise PaymentInvalidError("the stage must be a stage of the same object")
        if f["settles_id"] is not None:
            if kind not in MONEY_IN:
                raise PaymentInvalidError("only an advance or a payment can settle an invoice")
            if f["settles_id"] == own_id:
                raise PaymentInvalidError("a record cannot settle itself")
            target = (await self.db.execute(
                select(ProjectPayment).where(
                    ProjectPayment.id == f["settles_id"], ProjectPayment.project_id == project_id, ProjectPayment.owner_id == owner_id
                )
            )).scalar_one_or_none()
            if target is None or target.kind != "INVOICE":
                raise PaymentInvalidError("an advance or a payment can settle only an invoice of the same object")

    # -- reading --------------------------------------------------------------------

    async def list_payments(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, *, kind: str | None = None, include_archived: bool = False, today: date | None = None
    ) -> PaymentList:
        await self._ensure_project(owner_id, project_id)
        today = today or datetime.now(UTC).date()
        everything = await self._all(owner_id, project_id)
        entries = [_entry(row) for row in everything]
        finance = await self._finance_row(project_id)
        shown = [row for row in everything if (include_archived or not row.is_archived) and (kind is None or row.kind == kind)]
        return PaymentList(
            items=shown,
            standings=invoice_standings(entries, today),
            summary=summarize(entries, finance.agreed_amount if finance else None, today),
            total=len(shown),
        )

    async def count_payments(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> int:
        await self._ensure_project(owner_id, project_id)
        return len(await self._all(owner_id, project_id))

    # -- writing --------------------------------------------------------------------

    async def create_payment(self, owner_id: uuid.UUID, project_id: uuid.UUID, data: dict[str, Any], *, client_id: uuid.UUID | None = None) -> ProjectPayment:
        await self._ensure_project(owner_id, project_id)
        kind = data["kind"]
        fields = {
            "title": _clean_text(data.get("title"), required=True),
            "number": _clean_text(data.get("number")),
            "amount_gross": data["amount_gross"],
            "amount_net": data.get("amount_net"),
            "vat_rate": data.get("vat_rate"),
            "occurred_on": data["occurred_on"],
            "due_on": data.get("due_on"),
            "settles_id": data.get("settles_id"),
            "stage_id": data.get("stage_id"),
            "counterparty": _clean_text(data.get("counterparty")),
            "document_kind": data.get("document_kind"),
            "category": data.get("category"),
            "note": _clean_text(data.get("note")),
        }
        new_id = client_id or uuid.uuid4()
        await self._check(owner_id, project_id, new_id, kind, fields)
        repeat = await find_repeat(self.db, ProjectPayment, client_id, {"owner_id": owner_id, "project_id": project_id, "kind": kind, **fields})
        if repeat is not None:
            return repeat
        now = datetime.now(UTC)
        row = ProjectPayment(id=new_id, owner_id=owner_id, project_id=project_id, kind=kind, created_at=now, updated_at=now, **fields)
        self.db.add(row)
        await self._calendar_follows(owner_id, project_id)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_payment(self, owner_id: uuid.UUID, project_id: uuid.UUID, payment_id: uuid.UUID, changes: dict[str, Any]) -> ProjectPayment:
        row = await self._get(owner_id, project_id, payment_id)
        merged = {name: getattr(row, name) for name in EDITABLE}
        for name, value in changes.items():
            if name not in EDITABLE:
                raise PaymentInvalidError(f"{name} cannot be changed")
            if value is None and name in ("title", "amount_gross", "occurred_on"):
                raise PaymentInvalidError(f"{name} cannot be empty")
            merged[name] = value
        merged["title"] = _clean_text(merged["title"], required=True)
        for name in ("number", "counterparty", "note"):
            merged[name] = _clean_text(merged[name])
        await self._check(owner_id, project_id, row.id, row.kind, merged)
        for name in EDITABLE:
            setattr(row, name, merged[name])
        row.updated_at = datetime.now(UTC)
        await self._calendar_follows(owner_id, project_id)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def set_archived(self, owner_id: uuid.UUID, project_id: uuid.UUID, payment_id: uuid.UUID, archived: bool) -> ProjectPayment:
        row = await self._get(owner_id, project_id, payment_id)
        row.is_archived = archived
        row.updated_at = datetime.now(UTC)
        await self._calendar_follows(owner_id, project_id)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    # -- the agreed amount -------------------------------------------------------------

    async def _finance_row(self, project_id: uuid.UUID) -> ProjectFinance | None:
        return (await self.db.execute(select(ProjectFinance).where(ProjectFinance.project_id == project_id))).scalar_one_or_none()

    async def _suggestion(self, project_id: uuid.UUID) -> AgreedSuggestion | None:
        """The total of the accepted estimate, else of the final one (the newest version): only a hint, the owner decides the agreed amount."""
        for status in (EstimateStatus.ACCEPTED, EstimateStatus.FINAL):
            estimate = (await self.db.execute(
                select(Estimate).where(Estimate.project_id == project_id, Estimate.status == status, Estimate.total.is_not(None), Estimate.total > 0)
                .order_by(Estimate.version.desc()).limit(1)
            )).scalar_one_or_none()
            if estimate is not None and estimate.net_total is not None:
                return AgreedSuggestion(amount=estimate.net_total, estimate_id=estimate.id, estimate_version=estimate.version, status=status.value)
        return None

    async def get_finance(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> FinanceView:
        await self._ensure_project(owner_id, project_id)
        row = await self._finance_row(project_id)
        return FinanceView(
            agreed_amount=row.agreed_amount if row else None, currency=row.currency if row else "PLN", suggestion=await self._suggestion(project_id)
        )

    async def set_agreed_amount(self, owner_id: uuid.UUID, project_id: uuid.UUID, amount: Decimal | None) -> FinanceView:
        await self._ensure_project(owner_id, project_id)
        row = await self._finance_row(project_id)
        if row is None:
            row = ProjectFinance(project_id=project_id, owner_id=owner_id, agreed_amount=amount)
            self.db.add(row)
        else:
            row.agreed_amount = amount
            row.updated_at = datetime.now(UTC)
        await self._calendar_follows(owner_id, project_id)  # a share of the agreed amount may now be paid in full or not (V2-9b)
        await self.db.commit()
        return await self.get_finance(owner_id, project_id)
