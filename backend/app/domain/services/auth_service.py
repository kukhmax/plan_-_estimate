from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    MockAuthDisabledError,
    MockAuthDisallowedError,
    create_access_token,
    validate_telegram_init_data,
)
from app.models.user import User


class TelegramAuthService:
    """Domain service responsible for Telegram Mini App authentication and user provisioning."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def authenticate(self, init_data: str) -> tuple[User, str, bool]:
        """
        Validates Telegram initData, provisions or updates user in database,
        and generates an authenticated JWT session bearer token.
        Returns: (user, access_token, is_dev_auth)
        """
        init_data_clean = init_data.strip()

        if init_data_clean == "mock":
            if not settings.is_development:
                raise MockAuthDisallowedError(
                    "Mock authentication is prohibited outside development environment"
                )
            if not settings.MOCK_TELEGRAM_AUTH:
                raise MockAuthDisabledError(
                    "Mock authentication is disabled in configuration"
                )

            user_data = {
                "id": 999999999,
                "username": "dev_contractor",
                "first_name": "Jan",
                "last_name": "Kowalski",
                "language_code": "pl",
            }
            is_dev_auth = True
        else:
            user_data = validate_telegram_init_data(
                init_data=init_data_clean,
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                max_age_seconds=settings.TELEGRAM_AUTH_MAX_AGE_SECONDS,
            )
            is_dev_auth = False

        telegram_user_id = user_data["id"]

        # Provision or update existing user
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_user_id=telegram_user_id,
                username=user_data.get("username"),
                first_name=user_data.get("first_name"),
                last_name=user_data.get("last_name"),
                language_code=user_data.get("language_code"),
            )
            self.db.add(user)
        else:
            # Update user profile information upon subsequent logins
            user.username = user_data.get("username")
            user.first_name = user_data.get("first_name")
            user.last_name = user_data.get("last_name")
            user.language_code = user_data.get("language_code")

        await self.db.commit()
        await self.db.refresh(user)

        token = create_access_token(user.id)
        return user, token, is_dev_auth
