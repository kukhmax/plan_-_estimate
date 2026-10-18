"""The data keys of the owners (EN-2a): load them into the ring, make the key of an owner, put it in force for a request or a job.

The wrapped keys live in `data_keys`; the key of the server (`DATA_KEK`) lives only in the environment. Without `DATA_KEK` the ring is off
(development, tests): the encrypted columns pass plain text through. In production the application does not start without it.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import data_crypto
from app.core.config import settings
from app.core.key_ring import OwnerKey, ring, set_owner_key
from app.models.data_key import DataKey, WrappedBy


def server_kek() -> bytes | None:
    """The key of the server, or None while it is not configured. A configured but invalid one is an error (never a silent off)."""
    text = settings.DATA_KEK.get_secret_value()
    return data_crypto.parse_kek(text) if text.strip() else None


class DataKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def prepare(self) -> bool:
        """Switch the ring on or off by the configuration and load the keys it does not know yet. True when encryption is on."""
        kek = server_kek()
        if kek is None:
            ring.disable()
            return False
        ring.enable()
        ring.strict = settings.DATA_STRICT_READ
        known = ring.known()
        statement = select(DataKey).where(DataKey.wrapped_by == WrappedBy.SERVER_KEK.value)
        if known:
            statement = statement.where(DataKey.key_id.not_in(known))
        for row in (await self.db.execute(statement)).scalars():
            ring.add(row.key_id, data_crypto.unwrap_key(kek, row.wrapped_dek, row.key_id))
        return True

    async def owner_key(self, owner_id: uuid.UUID) -> OwnerKey:
        """The active key of the owner; made on the first need. Committed at once: a key must outlive the request that needed it."""
        cached = ring.owner(owner_id)
        if cached is not None:
            return cached
        kek = server_kek()
        if kek is None:
            raise data_crypto.DataKeyConfigurationError("DATA_KEK is not configured")
        row = await self._active_row(owner_id)
        if row is None:
            dek = data_crypto.new_key()
            key_id = uuid.uuid4().hex
            try:
                # In a savepoint: when another request made the key of this owner at the same moment, only this insert is undone, the rest of the
                # session (the user already loaded, for one) stays valid.
                async with self.db.begin_nested():
                    self.db.add(
                        DataKey(
                            owner_id=owner_id,
                            key_id=key_id,
                            wrapped_dek=data_crypto.wrap_key(kek, dek, key_id),
                            wrapped_by=WrappedBy.SERVER_KEK.value,
                            kek_version=settings.DATA_KEK_VERSION,
                            active=True,
                        )
                    )
            except IntegrityError:
                row = await self._active_row(owner_id)
                if row is None:
                    raise
                key = OwnerKey(row.key_id, data_crypto.unwrap_key(kek, row.wrapped_dek, row.key_id))
            else:
                await self.db.commit()
                key = OwnerKey(key_id, dek)
        else:
            key = OwnerKey(row.key_id, data_crypto.unwrap_key(kek, row.wrapped_dek, row.key_id))
        ring.set_owner(owner_id, key)
        return key

    async def put_in_force(self, owner_id: uuid.UUID) -> None:
        """For a request or a job of this owner: keys loaded, the owner key set. A no-op while encryption is off."""
        if not await self.prepare():
            set_owner_key(None)
            return
        set_owner_key(await self.owner_key(owner_id))

    async def _active_row(self, owner_id: uuid.UUID) -> DataKey | None:
        return (
            await self.db.execute(select(DataKey).where(DataKey.owner_id == owner_id, DataKey.active.is_(True)))
        ).scalar_one_or_none()
