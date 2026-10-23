from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import access_denied_http, get_auth_service, get_current_user, get_password_login_service
from app.core.config import settings
from app.core.security import (
    ExpiredDataError,
    InvalidSignatureError,
    MissingDataError,
    MockAuthDisabledError,
    MockAuthDisallowedError,
)
from app.domain.exceptions import AccessDeniedError, AccountLockedError, InvalidCredentialsError, PasswordLoginDisabledError
from app.domain.services.password_login_service import PasswordLoginService
from app.domain.services.auth_service import TelegramAuthService
from app.models.user import User
from app.schemas.auth import AuthConfigResponse, PasswordLoginRequest, TelegramAuthRequest, TelegramAuthResponse, UserRead

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
    except AccessDeniedError as e:
        raise access_denied_http(e)
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


@router.get(
    "/auth/config",
    response_model=AuthConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="What the sign-in screen needs: is the sign-in by password switched on",
)
async def auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(password_login=settings.AUTH_PASSWORD_ENABLED)


@router.post(
    "/auth/password",
    response_model=TelegramAuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign in with an e-mail and a password (accounts made by the owner; off unless AUTH_PASSWORD_ENABLED)",
)
async def auth_password(
    payload: PasswordLoginRequest,
    service: PasswordLoginService = Depends(get_password_login_service),
) -> TelegramAuthResponse:
    try:
        user, token = await service.authenticate(payload.email, payload.password)
    except PasswordLoginDisabledError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PASSWORD_LOGIN_DISABLED", "message": "Sign-in by password is switched off"},
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Wrong e-mail or password"},
        )
    except AccountLockedError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "ACCOUNT_LOCKED", "message": "Too many attempts: try again later", "retry_after_seconds": e.retry_after_seconds},
            headers={"Retry-After": str(e.retry_after_seconds)},
        )
    except AccessDeniedError as e:
        raise access_denied_http(e)
    return TelegramAuthResponse(access_token=token, token_type="bearer", user=UserRead.model_validate(user), is_dev_auth=False)
