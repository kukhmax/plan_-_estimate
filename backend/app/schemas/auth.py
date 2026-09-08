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


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    is_dev_auth: bool = False
