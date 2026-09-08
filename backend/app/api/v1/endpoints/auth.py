from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_auth_service, get_current_user
from app.core.security import (
    ExpiredDataError,
    InvalidSignatureError,
    MissingDataError,
    MockAuthDisabledError,
    MockAuthDisallowedError,
)
from app.domain.services.auth_service import TelegramAuthService
from app.models.user import User
from app.schemas.auth import TelegramAuthRequest, TelegramAuthResponse, UserRead

router = APIRouter()


@router.post(
    "/auth/telegram",
    response_model=TelegramAuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate via Telegram Mini App initData",
)
async def auth_telegram(
    payload: TelegramAuthRequest,
    auth_service: TelegramAuthService = Depends(get_auth_service),
) -> TelegramAuthResponse:
    """Thin API route delegating to TelegramAuthService."""
    try:
        user, token, is_dev_auth = await auth_service.authenticate(payload.init_data)
    except MockAuthDisallowedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MOCK_AUTH_DISALLOWED_IN_PRODUCTION", "message": str(e)},
        )
    except MockAuthDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MOCK_AUTH_DISABLED", "message": str(e)},
        )
    except InvalidSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TELEGRAM_SIGNATURE", "message": str(e)},
        )
    except ExpiredDataError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TELEGRAM_AUTH_EXPIRED", "message": str(e)},
        )
    except MissingDataError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_TELEGRAM_DATA", "message": str(e)},
        )

    return TelegramAuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
        is_dev_auth=is_dev_auth,
    )


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Thin API route returning authenticated user profile."""
    return UserRead.model_validate(current_user)
