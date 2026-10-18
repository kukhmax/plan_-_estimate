"""The re-encoding of the plain values of the encrypted columns (EN-2b-1; docs/CLIENT_ENCRYPTION_EN2B1_RUNBOOK_RU.md).

EN-2a writes ciphertext and reads plain text as it is; the values written before it stay open. This service turns them into ciphertext:
the list of the columns comes from the models themselves (every `EncryptedText` column), so a column added later is covered without a change here.
It works in batches, each in its own transaction, and can be stopped and started again (a value that is already ciphertext is skipped).
A value is replaced only if it is still what was read (compare-and-swap): a record the owner changed in the meantime is skipped and found by the next run.
It writes with plain SQL, so `updated_at` of a record does not move. It never prints a value or a key: only counts.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Text, Uuid, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  (registers every table)
from app.core import data_crypto
from app.core.database import Base
from app.core.encrypted_text import EncryptedText
from app.core.key_ring import ring
from app.domain.services.data_key_service import DataKeyService

IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
PREFIX_LIKE = data_crypto.PREFIX + "%"


@dataclass(frozen=True)
class EncryptedColumn:
    table: str
    column: str
    label: str
    owner_column: str


@dataclass
class ColumnStats:
    table: str
    column: str
    non_null: int = 0
    encrypted: int = 0
    converted: int = 0
    skipped_changed: int = 0
    undecryptable: int = 0

    @property
    def plain(self) -> int:
        return self.non_null - self.encrypted


def encrypted_columns() -> list[EncryptedColumn]:
    found = []
    for table in Base.metadata.sorted_tables:
        owner = "owner_id" if "owner_id" in table.c else "owner_user_id" if "owner_user_id" in table.c else None
        for column in table.columns:
            if isinstance(column.type, EncryptedText):
                assert owner is not None, f"{table.name} has encrypted columns and no owner column"
                names = (table.name, column.name, owner)
                assert all(IDENT.match(n) for n in names), names
                found.append(EncryptedColumn(table.name, column.name, column.type.label, owner))
    return found


class DataReencodeService:
    def __init__(self, session_factory: Callable[[], AsyncSession], batch_size: int = 200) -> None:
        self._sessions = session_factory
        self._batch = batch_size

    async def _prepared(self, db: AsyncSession) -> None:
        if not await DataKeyService(db).prepare():
            raise data_crypto.DataKeyConfigurationError("DATA_KEK is not configured: nothing to encrypt with")

    async def count(self, verify: bool = False) -> list[ColumnStats]:
        """Read only: per column, how many values are stored, how many are ciphertext; with `verify` every ciphertext is also decrypted."""
        result = []
        async with self._sessions() as db:
            await self._prepared(db)
            for col in encrypted_columns():
                stats = ColumnStats(col.table, col.column)
                row = (await db.execute(text(
                    f"SELECT count({col.column}), COALESCE(sum(CASE WHEN {col.column} LIKE :p THEN 1 ELSE 0 END), 0) FROM {col.table}"
                ), {"p": PREFIX_LIKE})).one()
                stats.non_null, stats.encrypted = int(row[0]), int(row[1])
                if verify:
                    last = None
                    while True:
                        rows = await self._batch_of(db, col, encrypted=True, after=last)
                        if not rows:
                            break
                        for row_id, _owner, value in rows:
                            try:
                                key_id, nonce, body = data_crypto.split_value(value)
                                dek = ring.get(key_id)
                                if dek is None:
                                    raise data_crypto.DataKeyUnavailableError(key_id)
                                data_crypto.decrypt_text(dek, col.label, nonce, body)
                            except data_crypto.DataCryptoError:
                                stats.undecryptable += 1
                        last = rows[-1][0]
                result.append(stats)
        return result

    async def _batch_of(self, db: AsyncSession, col: EncryptedColumn, *, encrypted: bool, after) -> list[tuple]:
        condition = f"{col.column} LIKE :p" if encrypted else f"{col.column} NOT LIKE :p"
        keyset = " AND id > :after" if after is not None else ""
        statement = text(
            f"SELECT id, {col.owner_column} AS owner, {col.column} AS value FROM {col.table} "
            f"WHERE {col.column} IS NOT NULL AND {condition}{keyset} ORDER BY id LIMIT :n"
        ).columns(id=Uuid(), owner=Uuid(), value=Text())
        params: dict = {"p": PREFIX_LIKE, "n": self._batch}
        if after is not None:
            statement = statement.bindparams(bindparam("after", type_=Uuid))
            params["after"] = after
        return [tuple(r) for r in (await db.execute(statement, params)).all()]

    async def apply(self, limit: int | None = None) -> list[ColumnStats]:
        """Turn the plain values into ciphertext, at most `limit` values in this run (None = all). Safe to repeat and to stop."""
        remaining = limit
        result = []
        for col in encrypted_columns():
            stats = ColumnStats(col.table, col.column)
            last = None
            while remaining is None or remaining > 0:
                async with self._sessions() as db:
                    await self._prepared(db)
                    rows = await self._batch_of(db, col, encrypted=False, after=last)
                    if not rows:
                        break
                    if remaining is not None:
                        rows = rows[:remaining]
                    service = DataKeyService(db)
                    update = text(f"UPDATE {col.table} SET {col.column} = :new WHERE id = :id AND {col.column} = :old").bindparams(
                        bindparam("id", type_=Uuid), bindparam("new", type_=Text), bindparam("old", type_=Text)
                    )
                    for row_id, owner_id, plain in rows:
                        key = await service.owner_key(owner_id)
                        sealed = data_crypto.encrypt_text(key.dek, key.key_id, col.label, plain)
                        changed = (await db.execute(update, {"id": row_id, "new": sealed, "old": plain})).rowcount
                        if changed == 1:
                            stats.converted += 1
                        else:
                            stats.skipped_changed += 1
                    await db.commit()
                    last = rows[-1][0]
                    if remaining is not None:
                        remaining -= len(rows)
            result.append(stats)
        counted = {(s.table, s.column): s for s in await self.count()}
        for stats in result:
            now = counted[(stats.table, stats.column)]
            stats.non_null, stats.encrypted = now.non_null, now.encrypted
        return result
