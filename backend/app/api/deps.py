from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.domain.services.area_segment_service import AreaSegmentService
from app.domain.services.auth_service import TelegramAuthService
from app.domain.services.checklist_service import ChecklistService
from app.domain.services.client_service import ClientService
from app.domain.services.inspection_service import InspectionService
from app.domain.services.opening_service import OpeningService
from app.domain.services.project_service import ProjectService
from app.domain.services.room_service import RoomService
from app.domain.services.surface_service import SurfaceService
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MISSING_TOKEN", "message": "Authentication credentials required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(e)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User not found or deactivated"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> TelegramAuthService:
    return TelegramAuthService(db)


async def get_client_service(
    db: AsyncSession = Depends(get_db),
) -> ClientService:
    return ClientService(db)


async def get_project_service(
    db: AsyncSession = Depends(get_db),
) -> ProjectService:
    return ProjectService(db)


async def get_room_service(
    db: AsyncSession = Depends(get_db),
) -> RoomService:
    return RoomService(db)


async def get_surface_service(
    db: AsyncSession = Depends(get_db),
) -> SurfaceService:
    return SurfaceService(db)


async def get_opening_service(
    db: AsyncSession = Depends(get_db),
) -> OpeningService:
    return OpeningService(db)


async def get_area_segment_service(
    db: AsyncSession = Depends(get_db),
) -> AreaSegmentService:
    return AreaSegmentService(db)


async def get_checklist_service(
    db: AsyncSession = Depends(get_db),
) -> ChecklistService:
    return ChecklistService(db)


async def get_inspection_service(
    db: AsyncSession = Depends(get_db),
) -> InspectionService:
    return InspectionService(db)
