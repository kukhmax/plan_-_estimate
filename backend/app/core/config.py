import os
import tempfile
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PHOTO_TEMP_DIR = os.path.join(tempfile.gettempdir(), "plan-estimate-photos")


class MediaConfigurationError(Exception):
    """Invalid combination of media settings. Deliberately NOT a ValueError:
    pydantic would wrap a ValueError into a ValidationError whose `errors()`
    carries the raw input (including MEDIA_S3_* secrets). This error names
    fields only and propagates unchanged, so startup fails visibly."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Never echo raw input values (e.g. MEDIA_S3_SECRET_ACCESS_KEY) in
        # validation errors.
        hide_input_in_errors=True,
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

    # Media storage (Stage 14B.3; docs/STAGE_14B_MEDIA_INFRASTRUCTURE_PLAN.md §11)
    MEDIA_STORAGE_BACKEND: Literal["disabled", "s3"] = "disabled"
    MEDIA_STORAGE_NAME: str = "r2-primary"
    MEDIA_S3_ENDPOINT_URL: str = ""
    MEDIA_S3_BUCKET: str = ""
    MEDIA_S3_REGION: str = "auto"
    MEDIA_S3_ACCESS_KEY_ID: SecretStr = SecretStr("")
    MEDIA_S3_SECRET_ACCESS_KEY: SecretStr = SecretStr("")

    # Photo feature gate and limits
    PHOTO_UPLOADS_ENABLED: bool = False
    PHOTO_SIGNED_URL_TTL_SECONDS: int = Field(default=300, ge=60, le=3600)
    PHOTO_MAX_UPLOAD_BYTES: int = Field(default=25_000_000, gt=0)
    # Whole multipart request (Stage 14C contract C3): image limit + multipart overhead.
    PHOTO_MAX_REQUEST_BYTES: int = Field(default=27_000_000, gt=0)
    PHOTO_MAX_DECODED_PIXELS: int = Field(default=60_000_000, gt=0)
    PHOTO_STORAGE_WARNING_BYTES: int = Field(default=8_000_000_000, gt=0)
    PHOTO_STORAGE_SOFT_CAP_BYTES: int = Field(default=10_000_000_000, gt=0)
    PHOTO_TEMP_DIR: str = DEFAULT_PHOTO_TEMP_DIR
    # OWNER APPROVED initial production defaults after the ARM64 benchmark
    # (14B plan §23.12); configuration values, not domain invariants.
    PHOTO_TEMP_STALE_AFTER_SECONDS: int = Field(default=86400, gt=0)
    PHOTO_PROCESSING_WAIT_SECONDS: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def _validate_media_configuration(self) -> "Settings":
        # Messages name fields only, never values (see MediaConfigurationError).
        if self.MEDIA_STORAGE_BACKEND == "s3":
            missing = [
                name
                for name, value in (
                    ("MEDIA_S3_ENDPOINT_URL", self.MEDIA_S3_ENDPOINT_URL),
                    ("MEDIA_S3_BUCKET", self.MEDIA_S3_BUCKET),
                    ("MEDIA_S3_REGION", self.MEDIA_S3_REGION),
                    ("MEDIA_S3_ACCESS_KEY_ID", self.MEDIA_S3_ACCESS_KEY_ID.get_secret_value()),
                    ("MEDIA_S3_SECRET_ACCESS_KEY", self.MEDIA_S3_SECRET_ACCESS_KEY.get_secret_value()),
                )
                if not value.strip()
            ]
            if missing:
                raise MediaConfigurationError(
                    "MEDIA_STORAGE_BACKEND=s3 requires: " + ", ".join(missing)
                )
            if not self.MEDIA_S3_ENDPOINT_URL.startswith("https://"):
                raise MediaConfigurationError("MEDIA_S3_ENDPOINT_URL must be an https:// URL")
        if self.PHOTO_UPLOADS_ENABLED and self.MEDIA_STORAGE_BACKEND != "s3":
            raise MediaConfigurationError("PHOTO_UPLOADS_ENABLED=true requires MEDIA_STORAGE_BACKEND=s3")
        if self.PHOTO_STORAGE_SOFT_CAP_BYTES < self.PHOTO_STORAGE_WARNING_BYTES:
            raise MediaConfigurationError(
                "PHOTO_STORAGE_SOFT_CAP_BYTES must be >= PHOTO_STORAGE_WARNING_BYTES"
            )
        if self.PHOTO_MAX_REQUEST_BYTES <= self.PHOTO_MAX_UPLOAD_BYTES:
            raise MediaConfigurationError("PHOTO_MAX_REQUEST_BYTES must be > PHOTO_MAX_UPLOAD_BYTES")
        if not self.PHOTO_TEMP_DIR.strip():
            raise MediaConfigurationError("PHOTO_TEMP_DIR must not be empty")
        return self

    @property
    def is_development(self) -> bool:
        env = (self.APP_ENV or self.ENVIRONMENT or "").lower()
        return env == "development"

    @property
    def is_production(self) -> bool:
        env = (self.APP_ENV or self.ENVIRONMENT or "").lower()
        return env == "production"


settings = Settings()
