"""The payment schedule of an object (V2-9): the owner's list of stages, what was received for each, where each stands.

Every call is owner-scoped. What a stage is worth and its state are made by `domain/rules/payment_schedule.py` from the stage, the agreed amount of the object
and the advances / payments that name the stage; nothing of it is stored. "Receive" books the rest of a stage as one payment in a single step. A stage is a plan,
not accounting: deleting it leaves the money it received in place, without a stage.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    PaymentStageInvalidError,
    PaymentStageNotFoundError,
    ProjectNotFoundError,
)
from app.domain.rules import payment_schedule as rules
from app.domain.services.payment_service import PaymentService
from app.models.payment_stage import PaymentStage
from app.models.project import Project
from app.models.project_payment import ProjectFinance, ProjectPayment


@dataclass(frozen=True, slots=True)
class StageView:
    stage: PaymentStage
    standing: rules.StageStanding


@dataclass(frozen=True, slots=True)
class Schedule:
    items: list[StageView]
    summary: rules.ScheduleSummary


def _entry(stage: PaymentStage) -> rules.StageEntry:
    return rules.StageEntry(id=stage.id, position=stage.position, percent=stage.percent, amount=stage.amount, due_on=stage.due_on)


def _title(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        raise PaymentStageInvalidError("STAGE_INVALID", "a stage needs a title")
    return text


class PaymentScheduleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _get(self, owner_id: uuid.UUID, project_id: uuid.UUID, stage_id: uuid.UUID) -> PaymentStage:
        await self._ensure_project(owner_id, project_id)
        row = (await self.db.execute(
            select(PaymentStage).where(PaymentStage.id == stage_id, PaymentStage.project_id == project_id, PaymentStage.owner_id == owner_id)
        )).scalar_one_or_none()
        if row is None:
            raise PaymentStageNotFoundError(f"Stage {stage_id} not found")
        return row

    async def _agreed(self, project_id: uuid.UUID) -> Decimal | None:
        row = (await self.db.execute(select(ProjectFinance).where(ProjectFinance.project_id == project_id))).scalar_one_or_none()
        return row.agreed_amount if row else None

    async def _money(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[rules.Received]:
        rows = (await self.db.execute(
            select(ProjectPayment).where(
                ProjectPayment.project_id == project_id, ProjectPayment.owner_id == owner_id, ProjectPayment.stage_id.is_not(None)
            )
        )).scalars()
        return [rules.Received(stage_id=r.stage_id, amount_gross=r.amount_gross, is_archived=r.is_archived) for r in rows]

    # -- reading ------------------------------------------------------------------

    async def schedule(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, today: date | None = None) -> Schedule:
        await self._ensure_project(owner_id, project_id)
        today = today or datetime.now(UTC).date()
        stages = list((await self.db.execute(
            select(PaymentStage).where(PaymentStage.project_id == project_id, PaymentStage.owner_id == owner_id)
        )).scalars())
        entries = [_entry(s) for s in stages]
        agreed = await self._agreed(project_id)
        found = rules.standings(entries, await self._money(owner_id, project_id), agreed, today)
        by_id = {s.id: s for s in stages}
        return Schedule(
            items=[StageView(by_id[e.id], found[e.id]) for e in rules.ordered(entries)],
            summary=rules.summarize(entries, found, agreed),
        )

    # -- writing ------------------------------------------------------------------

    async def create(self, owner_id: uuid.UUID, project_id: uuid.UUID, data: dict[str, Any]) -> PaymentStage:
        await self._ensure_project(owner_id, project_id)
        position = (await self.db.execute(
            select(func.coalesce(func.max(PaymentStage.position), -1)).where(PaymentStage.project_id == project_id)
        )).scalar_one() + 1
        now = datetime.now(UTC)
        row = PaymentStage(
            owner_id=owner_id, project_id=project_id, position=position, title=_title(data.get("title")),
            percent=data.get("percent"), amount=data.get("amount"), due_on=data.get("due_on"), created_at=now, updated_at=now,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def change(self, owner_id: uuid.UUID, project_id: uuid.UUID, stage_id: uuid.UUID, changes: dict[str, Any]) -> PaymentStage:
        row = await self._get(owner_id, project_id, stage_id)
        if "title" in changes:
            if changes["title"] is None:
                raise PaymentStageInvalidError("STAGE_INVALID", "a stage needs a title")
            row.title = _title(changes["title"])
        if changes.get("percent") is not None:
            row.percent, row.amount = changes["percent"], None
        elif changes.get("amount") is not None:
            row.amount, row.percent = changes["amount"], None
        if "due_on" in changes:
            row.due_on = changes["due_on"]
        row.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete(self, owner_id: uuid.UUID, project_id: uuid.UUID, stage_id: uuid.UUID) -> None:
        row = await self._get(owner_id, project_id, stage_id)
        # the money received for the stage stays: it only loses the stage (the database does the same with ON DELETE SET NULL)
        await self.db.execute(update(ProjectPayment).where(ProjectPayment.stage_id == row.id).values(stage_id=None))
        await self.db.execute(delete(PaymentStage).where(PaymentStage.id == row.id))
        await self.db.commit()

    async def receive(self, owner_id: uuid.UUID, project_id: uuid.UUID, stage_id: uuid.UUID, *, today: date | None = None) -> ProjectPayment:
        """The rest of the stage as one payment dated today, tied to the stage (and named after it): the one-tap "received"."""
        today = today or datetime.now(UTC).date()
        stage = await self._get(owner_id, project_id, stage_id)
        view = next(v for v in (await self.schedule(owner_id, project_id, today=today)).items if v.stage.id == stage.id)
        if view.standing.remaining is None:
            raise PaymentStageInvalidError("STAGE_AMOUNT_UNKNOWN", "the stage is a share of an agreed amount that is not set")
        if view.standing.remaining <= 0:
            raise PaymentStageInvalidError("STAGE_NOTHING_LEFT", "the stage is already paid")
        return await PaymentService(self.db).create_payment(
            owner_id, project_id,
            {"kind": "PAYMENT", "title": stage.title, "amount_gross": view.standing.remaining, "occurred_on": today, "stage_id": stage.id},
        )
