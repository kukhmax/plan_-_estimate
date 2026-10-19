"""What production must not start without (Stage 20E): the secrets that authentication stands on.

A weak `JWT_SECRET_KEY` lets anybody who knows it (the example file is public) sign a session token for any user; an empty or wrong
`TELEGRAM_BOT_TOKEN` makes the signature check of `initData` a check against a key everybody can compute. The messages name the settings,
never a value.
"""
import re

from app.core.config import Settings

MIN_JWT_SECRET_LENGTH = 32
PLACEHOLDER_MARKERS = ("change", "insecure", "example", "placeholder", "secret-key", "your-", "xxx", "todo")
BOT_TOKEN_SHAPE = re.compile(r"^[0-9]{6,}:[A-Za-z0-9_-]{30,}$")


def production_problems(config: Settings) -> list[str]:
    """The settings that are unsafe in production, by name; empty when the configuration may go on."""
    if not config.is_production:
        return []
    problems: list[str] = []
    secret = config.JWT_SECRET_KEY.strip()
    if len(secret) < MIN_JWT_SECRET_LENGTH or any(marker in secret.lower() for marker in PLACEHOLDER_MARKERS):
        problems.append("JWT_SECRET_KEY (at least 32 characters, not a placeholder: `openssl rand -hex 32`)")
    if not BOT_TOKEN_SHAPE.match(config.TELEGRAM_BOT_TOKEN.strip()):
        problems.append("TELEGRAM_BOT_TOKEN (the token of the bot from BotFather)")
    if config.MOCK_TELEGRAM_AUTH:
        problems.append("MOCK_TELEGRAM_AUTH (must be false)")
    if config.DEBUG:
        problems.append("DEBUG (must be false)")
    return problems


def ensure_production_configuration(config: Settings) -> None:
    problems = production_problems(config)
    if problems:
        raise RuntimeError("production configuration is unsafe, fix: " + "; ".join(problems))
