from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import urllib.parse
import uuid

import jwt

from app.core.config import settings


class TelegramAuthError(Exception):
    """Base exception for Telegram authentication failures."""
    pass


class InvalidSignatureError(TelegramAuthError):
    pass


class ExpiredDataError(TelegramAuthError):
    pass


class MissingDataError(TelegramAuthError):
    pass


class MockAuthDisallowedError(TelegramAuthError):
    pass


class MockAuthDisabledError(TelegramAuthError):
    pass


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> dict:
    """
    Cryptographically validates raw Telegram Mini App initData query string.
    Follows Telegram Mini App signature specification:
    1. Parses query string into key-value pairs.
    2. Extracts hash.
    3. Sorts remaining key-value pairs alphabetically and joins with newline.
    4. Generates secret_key = HMAC-SHA256("WebAppData", bot_token).
    5. Computes calculated_hash = HMAC-SHA256(secret_key, data_check_string).
    6. Validates hash using constant-time comparison.
    7. Validates auth_date freshness against max_age_seconds.
    8. Extracts and parses user JSON dictionary.
    """
    if not init_data or not init_data.strip():
        raise MissingDataError("Empty initData provided")

    if not bot_token:
        raise InvalidSignatureError("Bot token not configured on server")

    parsed_pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    if not parsed_pairs:
        raise MissingDataError("Unable to parse initData parameters")

    data_dict = dict(parsed_pairs)
    received_hash = data_dict.get("hash")
    if not received_hash:
        raise MissingDataError("Missing hash in initData")

    # Build data_check_string from all fields except hash, sorted alphabetically by key
    items = [(k, v) for k, v in parsed_pairs if k != "hash"]
    items.sort(key=lambda x: x[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in items)

    # Calculate HMAC-SHA256 signature
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise InvalidSignatureError("Telegram signature mismatch")

    # Validate auth_date freshness
    auth_date_str = data_dict.get("auth_date")
    if not auth_date_str:
        raise MissingDataError("Missing auth_date in initData")

    try:
        auth_date = int(auth_date_str)
    except (ValueError, TypeError):
        raise MissingDataError("Invalid auth_date format in initData")

    current_timestamp = int(datetime.now(timezone.utc).timestamp())
    if current_timestamp - auth_date > max_age_seconds:
        raise ExpiredDataError("Telegram initData has expired")

    # Disallow timestamps significantly in the future (more than 2 minutes of clock skew)
    if auth_date > current_timestamp + 120:
        raise ExpiredDataError("Telegram initData auth_date is in the future")

    # Extract user information
    user_str = data_dict.get("user")
    if not user_str:
        raise MissingDataError("Missing user object in initData")

    try:
        user_data = json.loads(user_str)
    except Exception:
        raise MissingDataError("Invalid user JSON in initData")

    if not isinstance(user_data, dict) or "id" not in user_data:
        raise MissingDataError("Missing id in Telegram user data")

    return user_data


def create_access_token(user_id: uuid.UUID | str) -> str:
    """Generates a signed JWT session bearer token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Decodes and validates a JWT session bearer token, returning user UUID."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise ValueError("Token missing sub claim")
        return uuid.UUID(user_id_str)
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid or expired token: {e}")
