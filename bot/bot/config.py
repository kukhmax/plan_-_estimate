from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    WEBAPP_URL: str = "http://localhost:5173"


bot_settings = BotSettings()
