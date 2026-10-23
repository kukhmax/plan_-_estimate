from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(..., description="Raw Telegram Mini App initData query string")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    telegram_user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    created_at: datetime
    updated_at: datetime
    is_admin: bool = False  # closed registration: may open the screen of the access list


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    is_dev_auth: bool = False


class PasswordLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=512)


class AuthConfigResponse(BaseModel):
    """What the sign-in screen needs before anyone is signed in."""

    password_login: bool
