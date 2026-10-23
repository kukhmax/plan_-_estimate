"""V2-1: sign in with an e-mail and a password, and the accounts that can do it (docs/V2_1_PLAN_RU.md).

The password is kept only as a `scrypt` hash from the standard library (no new dependency): `scrypt$N$r$p$salt$hash`, the parameters travel with the
hash so they can be raised later. A web account is an ordinary `User` with a NEGATIVE `telegram_user_id` (real Telegram ids are positive), written to
the access list as ACTIVE, so the block, the list and every owner-scoped query work as for a Telegram account.

Against guessing: five wrong passwords in a row lock the account for fifteen minutes; an unknown e-mail and a wrong password get the same answer after
the same work (a hash is computed for the unknown e-mail too).
"""

import asyncio
import base64
import functools
import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.domain.exceptions import (
    AccountLockedError,
    InvalidCredentialsError,
    PasswordLoginDisabledError,
    WebAccountError,
)
from app.domain.services.access_service import AccessService
from app.models.user import User
from app.models.user_credential import UserCredential

MIN_PASSWORD_LENGTH = 12
MAX_FAILURES = 5
LOCK_FOR = timedelta(minutes=15)
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1
_SCRYPT_MAXMEM = 128 * 1024 * 1024
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def hash_password(password: str, *, n: int = _SCRYPT_N, r: int = _SCRYPT_R, p: int = _SCRYPT_P) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_SCRYPT_MAXMEM, dklen=32)
    return "scrypt${}${}${}${}${}".format(n, r, p, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    """True only for the password that made `stored`; any malformed hash is a False, never an error."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


@functools.cache
def _dummy_hash() -> str:
    """A hash with the real parameters, for the unknown e-mail: the same work, so the answer takes as long as for a known one."""
    return hash_password("a password nobody has")


async def _verify(password: str, stored: str) -> bool:
    """The hash is slow on purpose: it runs in a thread, so the application keeps answering the other requests."""
    return await asyncio.to_thread(verify_password, password, stored)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class PasswordLoginService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def authenticate(self, email: str, password: str) -> tuple[User, str]:
        if not settings.AUTH_PASSWORD_ENABLED:
            raise PasswordLoginDisabledError("password sign-in is switched off")
        credential = (
            await self.db.execute(select(UserCredential).where(UserCredential.email == normalize_email(email)))
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if credential is None:
            await _verify(password, await asyncio.to_thread(_dummy_hash))
            raise InvalidCredentialsError()
        locked_until = _aware(credential.locked_until)
        if locked_until is not None and locked_until > now:
            await _verify(password, await asyncio.to_thread(_dummy_hash))
            raise AccountLockedError(int((locked_until - now).total_seconds()) + 1)
        if not await _verify(password, credential.password_hash):
            credential.failed_attempts += 1
            if credential.failed_attempts >= MAX_FAILURES:
                credential.failed_attempts = 0
                credential.locked_until = now + LOCK_FOR
            await self.db.commit()
            raise InvalidCredentialsError()

        user = (await self.db.execute(select(User).where(User.id == credential.user_id))).scalar_one()
        # the list of access decides at once (a block, the closing of the registration): AccessDeniedError goes up as for a Telegram sign-in
        user.is_admin = await AccessService(self.db).ensure_allowed(user.telegram_user_id)
        credential.failed_attempts = 0
        credential.locked_until = None
        credential.last_login_at = now
        await self.db.commit()
        await self.db.refresh(user)
        user.is_admin = await AccessService(self.db).ensure_allowed(user.telegram_user_id)  # `refresh` drops what is not a column
        return user, create_access_token(user.id)

    # ---- the accounts (the command line) -------------------------------------------------------------------------------------------------

    @staticmethod
    def check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WebAccountError("PASSWORD_TOO_SHORT", f"The password needs at least {MIN_PASSWORD_LENGTH} characters")

    async def create_account(self, email: str, name: str, password: str | None = None) -> tuple[User, str]:
        """A new web account with its place in the access list; returns the user and the password (made here when none was given)."""
        address = normalize_email(email)
        if not _EMAIL.match(address) or len(address) > 254:
            raise WebAccountError("EMAIL_INVALID", "That is not an e-mail address")
        if (await self.db.execute(select(UserCredential.user_id).where(UserCredential.email == address))).first() is not None:
            raise WebAccountError("EMAIL_TAKEN", "An account with this e-mail exists")
        chosen = password if password is not None else secrets.token_urlsafe(12)
        self.check_password(chosen)
        lowest = (await self.db.execute(select(func.min(User.telegram_user_id)))).scalar_one()
        web_id = min(lowest if lowest is not None else 0, 0) - 1  # -1, -2, ...: never a Telegram id
        first_name = name.strip()[:255] or None
        user = User(telegram_user_id=web_id, username=address[:255], first_name=first_name, last_name=None, language_code=None)
        self.db.add(user)
        await self.db.flush()
        self.db.add(UserCredential(user_id=user.id, email=address, password_hash=await asyncio.to_thread(hash_password, chosen)))
        await AccessService(self.db)._create(web_id, {"username": address, "first_name": first_name}, "ACTIVE", datetime.now(UTC))
        await self.db.commit()
        await self.db.refresh(user)
        return user, chosen

    async def set_password(self, email: str, password: str | None = None) -> str:
        credential = (
            await self.db.execute(select(UserCredential).where(UserCredential.email == normalize_email(email)))
        ).scalar_one_or_none()
        if credential is None:
            raise WebAccountError("ACCOUNT_NOT_FOUND", "No account with this e-mail")
        chosen = password if password is not None else secrets.token_urlsafe(12)
        self.check_password(chosen)
        credential.password_hash = await asyncio.to_thread(hash_password, chosen)
        credential.failed_attempts = 0
        credential.locked_until = None
        await self.db.commit()
        return chosen

    async def list_accounts(self) -> list[tuple[str, str | None, datetime | None]]:
        rows = (
            await self.db.execute(
                select(UserCredential.email, User.first_name, UserCredential.last_login_at)
                .join(User, User.id == UserCredential.user_id)
                .order_by(UserCredential.created_at, UserCredential.email)
            )
        ).all()
        return [(email, name, last) for email, name, last in rows]
