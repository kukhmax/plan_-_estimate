"""The change of the data key of an owner (EN-3b; docs/CLIENT_ENCRYPTION_KEYS_RUNBOOK_RU.md).

When the data key of an owner may have leaked (not the key of the server: that is EN-3a), the data keeps its protection only after every value is sealed
with a NEW data key. Order: `start` makes a new active key for the owner (the old one becomes inactive but stays, wrapped, to read what it sealed);
the backend is recreated so that no request goes on writing with the old key held in memory; `reseal` opens every value of the owner sealed with
another key and seals it with the active one (batches, each in its own transaction, compare-and-swap, resumable; `updated_at` does not move);
`status` shows how many values each key still seals; `retire` deletes an inactive key only when no value is sealed with it any more.
Counts only, never a key or a value.
"""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import Text, Uuid, bindparam, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import data_crypto
from app.core.config import settings
from app.core.key_ring import ring
from app.domain.services.data_key_service import DataKeyService, server_kek
from app.domain.services.data_reencode_service import EncryptedColumn, encrypted_columns
from app.models.data_key import DataKey, WrappedBy


class DataKeyRotationRefusedError(data_crypto.DataCryptoError):
    """A rotation step that would lose data or mix two rotations (a key still seals values, or the previous change is not finished)."""

    code = "DATA_KEY_ROTATION_REFUSED"


@dataclass(slots=True)
class KeyUse:
    key_id: str
    active: bool
    values: int  # the values that this key seals, over every encrypted column of the owner


@dataclass(slots=True)
class OwnerKeys:
    owner_id: uuid.UUID
    keys: list[KeyUse] = field(default_factory=list)

    @property
    def active(self) -> KeyUse | None:
        return next((key for key in self.keys if key.active), None)

    @property
    def to_reseal(self) -> int:
        return sum(key.values for key in self.keys if not key.active)

    @property
    def done(self) -> bool:
        return self.to_reseal == 0


@dataclass(slots=True)
class ResealStats:
    resealed: int = 0
    skipped_changed: int = 0
    undecryptable: int = 0


class DekRotationService:
    def __init__(self, session_factory: Callable[[], AsyncSession], batch_size: int = 200) -> None:
        self._sessions = session_factory
        self._batch = batch_size

    @staticmethod
    async def _prepared(db: AsyncSession) -> None:
        if not await DataKeyService(db).prepare():
            raise data_crypto.DataKeyConfigurationError("DATA_KEK is not configured: nothing to rotate")

    async def _uses(self, db: AsyncSession, owner_id: uuid.UUID, key_id: str) -> int:
        total = 0
        for col in encrypted_columns():
            total += int((await db.execute(
                text(f"SELECT count(*) FROM {col.table} WHERE {col.owner_column} = :owner AND {col.column} LIKE :p").bindparams(bindparam("owner", type_=Uuid)),
                {"owner": owner_id, "p": f"{data_crypto.PREFIX}{key_id}:%"},
            )).scalar_one())
        return total

    async def status(self) -> list[OwnerKeys]:
        async with self._sessions() as db:
            await self._prepared(db)
            rows = (await db.execute(
                select(DataKey).where(DataKey.wrapped_by == WrappedBy.SERVER_KEK.value).order_by(DataKey.owner_id, DataKey.created_at, DataKey.key_id)
            )).scalars().all()
            owners: dict[uuid.UUID, OwnerKeys] = {}
            for row in rows:
                entry = owners.setdefault(row.owner_id, OwnerKeys(row.owner_id))
                entry.keys.append(KeyUse(row.key_id, row.active, await self._uses(db, row.owner_id, row.key_id)))
            return list(owners.values())

    async def start(self, owner_id: uuid.UUID) -> str:
        """Make a new active data key for the owner; the old one stays (inactive) until `retire`. Refused while a previous change is unfinished."""
        kek = server_kek()
        if kek is None:
            raise data_crypto.DataKeyConfigurationError("DATA_KEK is not configured")
        async with self._sessions() as db:
            await self._prepared(db)
            current = (await db.execute(select(DataKey).where(DataKey.owner_id == owner_id, DataKey.active.is_(True)))).scalar_one_or_none()
            if current is None:
                raise DataKeyRotationRefusedError("the owner has no active data key")
            for old in (await db.execute(select(DataKey).where(DataKey.owner_id == owner_id, DataKey.active.is_(False)))).scalars():
                if await self._uses(db, owner_id, old.key_id):
                    raise DataKeyRotationRefusedError("a previous change of the data key is not finished: run reseal first")
            new_id = uuid.uuid4().hex
            await db.execute(update(DataKey).where(DataKey.id == current.id).values(active=False))
            db.add(DataKey(
                owner_id=owner_id, key_id=new_id, wrapped_dek=data_crypto.wrap_key(kek, data_crypto.new_key(), new_id),
                wrapped_by=WrappedBy.SERVER_KEK.value, kek_version=settings.DATA_KEK_VERSION, active=True,
            ))
            await db.commit()
        ring.forget_owner(owner_id)
        return new_id

    async def reseal(self, owner_id: uuid.UUID | None = None, limit: int | None = None) -> ResealStats:
        """Seal with the active key every value of the owner(s) that another key seals. Safe to repeat and to stop."""
        stats = ResealStats()
        remaining = limit
        async with self._sessions() as db:
            await self._prepared(db)
            active = (await db.execute(
                select(DataKey).where(DataKey.active.is_(True), DataKey.wrapped_by == WrappedBy.SERVER_KEK.value)
                .where(*([DataKey.owner_id == owner_id] if owner_id else []))
            )).scalars().all()
            targets = [(row.owner_id, row.key_id) for row in active]
        for owner, key_id in targets:
            for col in encrypted_columns():
                if remaining is not None and remaining <= 0:
                    return stats
                remaining = await self._reseal_column(owner, key_id, col, stats, remaining)
        return stats

    async def _reseal_column(self, owner: uuid.UUID, key_id: str, col: EncryptedColumn, stats: ResealStats, remaining: int | None) -> int | None:
        last = None
        base = (
            f"SELECT id, {col.column} AS value FROM {col.table} WHERE {col.owner_column} = :owner AND {col.column} LIKE :any "
            f"AND {col.column} NOT LIKE :mine"
        )
        while remaining is None or remaining > 0:
            async with self._sessions() as db:
                await self._prepared(db)
                active_key = ring.get(key_id)
                if active_key is None:
                    raise data_crypto.DataKeyUnavailableError(key_id)
                statement = text(f"{base}{' AND id > :after' if last is not None else ''} ORDER BY id LIMIT :n").columns(id=Uuid(), value=Text())
                statement = statement.bindparams(bindparam("owner", type_=Uuid))
                params: dict = {"owner": owner, "any": f"{data_crypto.PREFIX}%", "mine": f"{data_crypto.PREFIX}{key_id}:%", "n": self._batch}
                if last is not None:
                    statement = statement.bindparams(bindparam("after", type_=Uuid))
                    params["after"] = last
                rows = [tuple(r) for r in (await db.execute(statement, params)).all()]
                if not rows:
                    return remaining
                if remaining is not None:
                    rows = rows[:remaining]
                write = text(f"UPDATE {col.table} SET {col.column} = :new WHERE id = :id AND {col.column} = :old").bindparams(
                    bindparam("id", type_=Uuid), bindparam("new", type_=Text), bindparam("old", type_=Text)
                )
                for row_id, stored in rows:
                    try:
                        old_id, nonce, body = data_crypto.split_value(stored)
                        old_dek = ring.get(old_id)
                        if old_dek is None:
                            raise data_crypto.DataKeyUnavailableError(old_id)
                        plain = data_crypto.decrypt_text(old_dek, col.label, nonce, body)
                    except data_crypto.DataCryptoError:
                        stats.undecryptable += 1
                        continue
                    sealed = data_crypto.encrypt_text(active_key, key_id, col.label, plain)
                    changed = (await db.execute(write, {"id": row_id, "new": sealed, "old": stored})).rowcount
                    if changed == 1:
                        stats.resealed += 1
                    else:
                        stats.skipped_changed += 1
                await db.commit()
                last = rows[-1][0]
                if remaining is not None:
                    remaining -= len(rows)
        return remaining

    async def retire(self, owner_id: uuid.UUID | None = None) -> int:
        """Delete the inactive data keys that no value is sealed with any more; refuses (and deletes nothing) if any still seals a value."""
        async with self._sessions() as db:
            await self._prepared(db)
            inactive = (await db.execute(
                select(DataKey).where(DataKey.active.is_(False), DataKey.wrapped_by == WrappedBy.SERVER_KEK.value)
                .where(*([DataKey.owner_id == owner_id] if owner_id else []))
            )).scalars().all()
            for key in inactive:
                if await self._uses(db, key.owner_id, key.key_id):
                    raise DataKeyRotationRefusedError("an inactive data key still seals values: run reseal first; nothing was deleted")
            for key in inactive:
                await db.execute(delete(DataKey).where(DataKey.id == key.id))
            await db.commit()
            return len(inactive)
