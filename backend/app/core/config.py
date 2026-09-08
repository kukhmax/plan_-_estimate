from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/plan_estimate"

    # Telegram Mini App Authentication
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_AUTH_MAX_AGE_SECONDS: int = 86400  # 24 hours
    MOCK_TELEGRAM_AUTH: bool = False

    # JWT Session Configuration
    JWT_SECRET_KEY: str = "insecure-dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    @property
    def is_development(self) -> bool:
        env = (self.APP_ENV or self.ENVIRONMENT or "").lower()
        return env == "development"

    @property
    def is_production(self) -> bool:
        env = (self.APP_ENV or self.ENVIRONMENT or "").lower()
        return env == "production"


settings = Settings()
