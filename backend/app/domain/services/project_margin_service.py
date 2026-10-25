"""The margin of an object (V2-9): reads the agreed amount (or the hint of the estimate), the expenses, the hours and the hourly rate, and lets
`domain/rules/margin.py` count. Owner-scoped; nothing is stored."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules import margin as rules
from app.domain.services.payment_service import PaymentService
from app.domain.services.work_hours_service import WorkHoursService
from app.models.executor_profile import ExecutorProfile


class ProjectMarginService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def hourly_rate(self, owner_id: uuid.UUID):
        return (await self.db.execute(select(ExecutorProfile.hourly_rate).where(ExecutorProfile.owner_id == owner_id))).scalar_one_or_none()

    async def margin(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> rules.Margin:
        payments = PaymentService(self.db)
        listed = await payments.list_payments(owner_id, project_id, today=datetime.now(UTC).date())
        finance = await payments.get_finance(owner_id, project_id)
        hours = await WorkHoursService(self.db).total_hours(owner_id, project_id)
        return rules.compute(
            finance.agreed_amount,
            finance.suggestion.amount if finance.suggestion else None,
            listed.summary.expenses,
            hours,
            await self.hourly_rate(owner_id),
        )
