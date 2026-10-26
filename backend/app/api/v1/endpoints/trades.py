"""The trades (packages of professions) of the authenticated owner (V2-13): thin routes over `TradesService`."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.domain.rules.trades import TradesError
from app.domain.services.trades_service import TradesService, read_of
from app.models.user import User
from app.schemas.trades import TradesRead, TradesWrite

router = APIRouter()


@router.get("/trades", response_model=TradesRead, summary="The trades (what each one owns) and the ones the owner works in; every trade while none was chosen")
async def get_trades(current_user: User = Depends(get_current_user)) -> TradesRead:
    return read_of(current_user)


@router.put("/trades", response_model=TradesRead, summary="Choose the trades the owner works in (known trades only; an empty choice is allowed)")
async def put_trades(payload: TradesWrite, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> TradesRead:
    try:
        return await TradesService(db).save(current_user, payload.enabled)
    except TradesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "TRADES_INVALID", "message": str(exc), "details": {"reason": exc.reason, "key": exc.key}},
        ) from None
