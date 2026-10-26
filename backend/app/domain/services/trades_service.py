"""The trades of an owner (V2-13): read the choice (every trade while none was made) and save it. The rules are in `domain/rules/trades.py`."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules.trades import ALWAYS_CATEGORIES, TRADES, enabled_of, validate_enabled
from app.models.user import User
from app.schemas.trades import TradeRead, TradesRead


def read_of(user: User) -> TradesRead:
    return TradesRead(
        trades=[TradeRead(key=t.key, price_categories=list(t.price_categories), material_packages=list(t.material_packages), room_points=t.room_points) for t in TRADES],
        always_categories=list(ALWAYS_CATEGORIES),
        enabled=list(enabled_of(user.trades)),
    )


class TradesService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save(self, user: User, enabled: list[object]) -> TradesRead:
        """Raises `TradesError` for an unknown trade or a wrong entry; nothing is saved then."""
        user.trades = list(validate_enabled(enabled))
        await self.db.commit()
        await self.db.refresh(user)
        return read_of(user)
