"""The rotation of the key of the server (EN-3a): re-wrap every data key with the new `DATA_KEK`; the data itself is not touched.

Order of a rotation (docs/CLIENT_ENCRYPTION_KEYS_RUNBOOK_RU.md): the new key is made and saved by the owner, `.env.production` gets
`DATA_KEK=<new>`, `DATA_KEK_VERSION=<n+1>` and `DATA_KEK_PREVIOUS=<old>`, the backend is recreated (it now reads the data keys wrapped by either),
`rewrap` re-wraps them all with the new key, `verify` proves that every one opens with the new key ALONE, and only then `DATA_KEK_PREVIOUS` is removed.

`rewrap` is all or nothing: one transaction for every row, undone when any row opens with neither key. A row is changed only where its wrapped value
is still the one read (a concurrent change makes it a conflict, undone as well). Counts only, never a key or a value.
"""
import base64
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import data_crypto
from app.core.config import settings
from app.domain.services.data_key_service import previous_kek, server_kek
from app.models.data_key import DataKey, WrappedBy


@dataclass(slots=True)
class KekStatus:
    total: int = 0  # the keys wrapped by the key of the server
    owner_wrapped: int = 0  # wrapped by a key of an owner (V2): not this command's
    current: int = 0  # open with the current key of the server alone
    previous_only: int = 0  # open only with the previous key: still to be re-wrapped
    unreadable: int = 0  # open with neither
    versions: dict[int, int] = field(default_factory=dict)  # kek_version -> number of keys
    rewrapped: int = 0

    @property
    def done(self) -> bool:
        """Every key opens with the current key alone: the previous key may be removed."""
        return self.unreadable == 0 and self.previous_only == 0 and self.current == self.total


class KekRotationService:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_maker

    @staticmethod
    def _keys() -> tuple[bytes, bytes | None]:
        kek = server_kek()
        if kek is None:
            raise data_crypto.DataKeyConfigurationError("DATA_KEK is not configured")
        previous = previous_kek()
        if previous is not None and previous == kek:
            raise data_crypto.DataKeyConfigurationError("DATA_KEK_PREVIOUS is the same key as DATA_KEK")
        return kek, previous

    @staticmethod
    def _opens(kek: bytes | None, row: DataKey) -> bool:
        if kek is None:
            return False
        try:
            data_crypto.unwrap_key(kek, row.wrapped_dek, row.key_id)
        except data_crypto.DataDecryptError:
            return False
        return True

    async def _rows(self, db: AsyncSession) -> list[DataKey]:
        return list((await db.execute(select(DataKey).where(DataKey.wrapped_by == WrappedBy.SERVER_KEK.value).order_by(DataKey.key_id))).scalars())

    async def status(self) -> KekStatus:
        kek, previous = self._keys()
        async with self._sessions() as db:
            return await self._classify(db, kek, previous)

    async def _classify(self, db: AsyncSession, kek: bytes, previous: bytes | None) -> KekStatus:
        status = KekStatus()
        status.owner_wrapped = len((await db.execute(select(DataKey.id).where(DataKey.wrapped_by != WrappedBy.SERVER_KEK.value))).scalars().all())
        for row in await self._rows(db):
            status.total += 1
            status.versions[row.kek_version] = status.versions.get(row.kek_version, 0) + 1
            if self._opens(kek, row):
                status.current += 1
            elif self._opens(previous, row):
                status.previous_only += 1
            else:
                status.unreadable += 1
        return status

    async def rewrap(self) -> KekStatus:
        """Re-wrap every key that opens only with the previous key; stamp `kek_version` on every key. All or nothing."""
        kek, previous = self._keys()
        async with self._sessions() as db:
            status = await self._classify(db, kek, previous)
            if status.unreadable:
                await db.rollback()
                return status
            if status.previous_only and previous is None:
                raise data_crypto.DataKeyConfigurationError("DATA_KEK_PREVIOUS is not configured but some keys are wrapped by the old key")
            for row in await self._rows(db):
                wrapped = row.wrapped_dek
                if not self._opens(kek, row):
                    wrapped = data_crypto.wrap_key(kek, data_crypto.unwrap_key(previous, row.wrapped_dek, row.key_id), row.key_id)  # type: ignore[arg-type]
                    status.rewrapped += 1
                if wrapped == row.wrapped_dek and row.kek_version == settings.DATA_KEK_VERSION:
                    continue
                done = await db.execute(
                    update(DataKey)
                    .where(DataKey.id == row.id, DataKey.wrapped_dek == row.wrapped_dek)
                    .values(wrapped_dek=wrapped, kek_version=settings.DATA_KEK_VERSION)
                )
                if done.rowcount != 1:  # type: ignore[attr-defined]
                    await db.rollback()
                    raise data_crypto.DataKeyUnavailableError("a data key changed while it was re-wrapped; nothing was changed")
            await db.commit()
        after = await self.status()
        after.rewrapped = status.rewrapped
        return after

    @staticmethod
    def new_kek_text() -> str:
        """A fresh key of the server in the form DATA_KEK is written in (printed once by the owner's command, never stored here)."""
        return base64.b64encode(data_crypto.new_key()).decode("ascii")


