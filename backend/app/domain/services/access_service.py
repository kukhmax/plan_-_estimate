"""Closed registration: who may enter (backlog item, not a roadmap stage).

Two decisions are made here and nowhere else:

* `admit_login` -- at the sign-in with Telegram. Registration CLOSED: only an ACTIVE entry enters; anyone else is noted as PENDING (so that the
  administrator sees who asked) and refused. Registration OPEN (the setting is "0" or absent, as before the change): anyone enters except a
  BLOCKED account, and is written to the list as ACTIVE, so that closing the registration later keeps everyone who works.
* `ensure_allowed` -- at every request with a token: the same rule, READ ONLY, so that a block or the closing takes effect at once and not when
  the seven-day token expires.

An administrator always enters. The administrator is changed only by `python -m app.cli.access`, never through the screen.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    AccessAdminProtectedError,
    AccessDeniedError,
    AccessEntryNotFoundError,
    AccessSettingsInvalidError,
)
from app.models.access_entry import AccessEntry, AccessSetting, AccessStatus
from app.models.user import User

CLOSED_KEY = "closed"
CONTACT_KEY = "contact"
PENDING_CAP = 200  # requests kept while the registration is closed: a guard against a flood of foreign accounts, not a quota
CONTACT_MAX_LENGTH = 300
_ORDER = {AccessStatus.PENDING.value: 0, AccessStatus.ACTIVE.value: 1, AccessStatus.BLOCKED.value: 2}


class AccessService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---- the settings -------------------------------------------------------------------------------------------------------------------

    async def _setting(self, key: str) -> str | None:
        return (await self.db.execute(select(AccessSetting.value).where(AccessSetting.key == key))).scalar_one_or_none()

    async def _put_setting(self, key: str, value: str) -> None:
        row = await self.db.get(AccessSetting, key)
        if row is None:
            self.db.add(AccessSetting(key=key, value=value))
        else:
            row.value = value

    async def is_closed(self) -> bool:
        return (await self._setting(CLOSED_KEY)) == "1"

    async def contact(self) -> str:
        return (await self._setting(CONTACT_KEY)) or ""

    async def _entry(self, telegram_user_id: int) -> AccessEntry | None:
        return (await self.db.execute(select(AccessEntry).where(AccessEntry.telegram_user_id == telegram_user_id))).scalar_one_or_none()

    # ---- the two decisions --------------------------------------------------------------------------------------------------------------

    async def admit_login(self, telegram_user_id: int, profile: dict) -> AccessEntry:
        entry = await self._entry(telegram_user_id)
        if entry is not None and entry.is_admin:
            return entry
        if entry is not None and entry.status == AccessStatus.BLOCKED.value:
            raise AccessDeniedError(await self.contact(), blocked=True)
        if entry is not None and entry.status == AccessStatus.ACTIVE.value:
            return entry

        now = datetime.now(UTC)
        if not await self.is_closed():
            if entry is None:
                entry = await self._create(telegram_user_id, profile, AccessStatus.ACTIVE.value, now)
            else:  # a pending request while the registration was closed: it was opened since
                entry.status = AccessStatus.ACTIVE.value
                entry.decided_at = now
            await self.db.commit()
            return entry

        if entry is None:
            pending = (await self.db.execute(select(func.count()).select_from(AccessEntry).where(AccessEntry.status == AccessStatus.PENDING.value))).scalar_one()
            if pending < PENDING_CAP:
                await self._create(telegram_user_id, profile, AccessStatus.PENDING.value, None)
        else:
            self._copy_profile(entry, profile)
        await self.db.commit()
        raise AccessDeniedError(await self.contact())

    @staticmethod
    def fact_columns() -> tuple:
        """The three facts `judge` needs, as scalar subqueries over a `users` row: the request that loads the user reads them in the SAME
        statement (a request pays no query for the access check). Add them to `select(User, *AccessService.fact_columns())`."""
        entry = AccessEntry.telegram_user_id == User.telegram_user_id
        return (
            select(AccessEntry.status).where(entry).scalar_subquery(),
            select(AccessEntry.is_admin).where(entry).scalar_subquery(),
            select(AccessSetting.value).where(AccessSetting.key == CLOSED_KEY).scalar_subquery(),
        )

    async def judge(self, status: str | None, is_admin: bool | None, closed: str | None) -> bool:
        """The rule of every request, from the facts only. Returns whether the account is an administrator; raises `AccessDeniedError` when it
        may not work (the contact text is read only then)."""
        if is_admin:
            return True
        if status == AccessStatus.BLOCKED.value:
            raise AccessDeniedError(await self.contact(), blocked=True)
        if closed == "1" and status != AccessStatus.ACTIVE.value:
            raise AccessDeniedError(await self.contact())
        return False

    async def ensure_allowed(self, telegram_user_id: int) -> bool:
        """Read only, by the Telegram id. Returns whether the account is an administrator; raises `AccessDeniedError` when it may not work."""
        entry = await self._entry(telegram_user_id)
        closed = await self._setting(CLOSED_KEY)
        return await self.judge(entry.status if entry else None, entry.is_admin if entry else None, closed)

    async def admit_account(self, telegram_user_id: int, profile: dict) -> AccessEntry:
        """Write an account that was made by the owner (a web account) to the list as ACTIVE; an existing entry is kept as it is."""
        entry = await self._entry(telegram_user_id)
        if entry is None:
            entry = await self._create(telegram_user_id, profile, AccessStatus.ACTIVE.value, datetime.now(UTC))
            await self.db.commit()
        return entry

    async def is_admin(self, telegram_user_id: int) -> bool:
        entry = await self._entry(telegram_user_id)
        return bool(entry and entry.is_admin)

    async def _create(self, telegram_user_id: int, profile: dict, status: str, decided_at: datetime | None) -> AccessEntry:
        entry = AccessEntry(telegram_user_id=telegram_user_id, status=status, decided_at=decided_at)
        self._copy_profile(entry, profile)
        try:
            async with self.db.begin_nested():
                self.db.add(entry)
                await self.db.flush()
        except IntegrityError:  # two sign-ins of the same account at once: the other one wrote the row first
            existing = await self._entry(telegram_user_id)
            if existing is None:
                raise
            return existing
        return entry

    @staticmethod
    def _copy_profile(entry: AccessEntry, profile: dict) -> None:
        for field in ("username", "first_name", "last_name"):
            value = profile.get(field)
            setattr(entry, field, str(value)[:255] if value else None)

    # ---- the screen of the administrator ------------------------------------------------------------------------------------------------

    async def list_entries(self) -> list[AccessEntry]:
        rows = (await self.db.execute(select(AccessEntry))).scalars().all()
        return sorted(rows, key=lambda row: (_ORDER.get(row.status, 9), row.created_at, str(row.id)))

    async def settings(self) -> tuple[bool, str]:
        return await self.is_closed(), await self.contact()

    async def decide(self, entry_id: uuid.UUID, status: str) -> AccessEntry:
        entry = await self._get(entry_id)
        if entry.is_admin:
            raise AccessAdminProtectedError()
        entry.status = status
        entry.decided_at = datetime.now(UTC)
        await self.db.commit()
        return entry

    async def remove(self, entry_id: uuid.UUID) -> None:
        entry = await self._get(entry_id)
        if entry.is_admin:
            raise AccessAdminProtectedError()
        await self.db.delete(entry)
        await self.db.commit()

    async def update_settings(self, closed: bool | None, contact: str | None) -> tuple[bool, str]:
        if contact is not None:
            contact = contact.strip()
            if len(contact) > CONTACT_MAX_LENGTH:
                raise AccessSettingsInvalidError()
            await self._put_setting(CONTACT_KEY, contact)
        if closed is not None:
            await self._put_setting(CLOSED_KEY, "1" if closed else "0")
        await self.db.commit()
        return await self.settings()

    async def _get(self, entry_id: uuid.UUID) -> AccessEntry:
        entry = await self.db.get(AccessEntry, entry_id)
        if entry is None:
            raise AccessEntryNotFoundError()
        return entry

    # ---- the command line (recovery) ----------------------------------------------------------------------------------------------------

    async def set_admin(self, telegram_user_id: int) -> None:
        """Make this account the only administrator (it is admitted if it was not). The previous administrator stays an ordinary ACTIVE entry."""
        for row in (await self.db.execute(select(AccessEntry).where(AccessEntry.is_admin.is_(True)))).scalars():
            row.is_admin = False
        entry = await self._entry(telegram_user_id)
        if entry is None:
            entry = await self._create(telegram_user_id, {}, AccessStatus.ACTIVE.value, datetime.now(UTC))
        entry.status = AccessStatus.ACTIVE.value
        entry.is_admin = True
        entry.decided_at = datetime.now(UTC)
        await self.db.commit()

    async def set_closed(self, closed: bool) -> None:
        await self._put_setting(CLOSED_KEY, "1" if closed else "0")
        await self.db.commit()
