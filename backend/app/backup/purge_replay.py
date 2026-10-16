"""Replay the purge ledger on a restored database (archive cleanup AC-3).

A database restored from a dump that is older than a deletion holds the rows of the deleted photos again, while their files are gone from the
backups (and from the working storage). This step removes those rows -- the markers, the attachments, the file sets of exactly the assets the
ledger names -- and puts the ledger rows into the restored database, so that it remembers the deletions as the original did.

It runs **last** in the restore chain, after the media step has proved the restored database against the manifest (the READY set must still match
the dump at that point); the integrity checker the operator runs afterwards then sees a database without the purged photos and a bucket without
their files. It only touches the scratch database the earlier guards already accepted, in one transaction (all or nothing).
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from app.backup.pg_connection import PgConnectionConfig
from app.backup.purge_ledger import PurgeLedgerFile
from app.backup.restore_db import Connect, _close, _connect

logger = logging.getLogger(__name__)

DELETE_ANNOTATIONS = "DELETE FROM photo_annotations WHERE attachment_id IN (SELECT id FROM photo_attachments WHERE asset_id = ANY($1::uuid[]))"
DELETE_ATTACHMENTS = "DELETE FROM photo_attachments WHERE asset_id = ANY($1::uuid[])"
DELETE_ASSETS = "DELETE FROM photo_assets WHERE id = ANY($1::uuid[])"
INSERT_LEDGER = (
    "INSERT INTO purge_ledger (id, owner_id, project_id, asset_id, kind, storage_name, storage_key_original, storage_key_display, "
    "storage_key_thumbnail, sha256, byte_size, display_byte_size, thumbnail_byte_size, purged_at, storage_state, storage_done_at, "
    "backup_state, backup_done_at) VALUES ($1, $2, $3, $4, 'PHOTO', $5, $6, $7, $8, $9, $10, $11, $12, $13::timestamptz, 'DONE', $13::timestamptz, 'DONE', $13::timestamptz) "
    "ON CONFLICT DO NOTHING"
)
# the ledger file carries neither the owner nor the project (they are not needed to remove the rows); a restored ledger row names the nil UUID
NIL = uuid.UUID(int=0)


class PurgeReplayError(Exception):
    """The replay could not be applied; nothing was changed (one transaction). The message names no value."""


@dataclass(frozen=True, slots=True)
class PurgeReplayReport:
    ledger_entries: int
    assets_removed: int
    attachments_removed: int
    annotations_removed: int
    ledger_rows_added: int

    @property
    def ok(self) -> bool:
        return True

    def to_dict(self) -> dict[str, int]:
        return {
            "ledger_entries": self.ledger_entries,
            "assets_removed": self.assets_removed,
            "attachments_removed": self.attachments_removed,
            "annotations_removed": self.annotations_removed,
            "ledger_rows_added": self.ledger_rows_added,
        }


def _count(status: str) -> int:
    """The row count of an asyncpg command tag (`DELETE 3`)."""
    return int(status.rsplit(" ", 1)[-1])


async def replay_purge(database: PgConnectionConfig, ledger: PurgeLedgerFile, *, connect: Connect = asyncpg.connect) -> PurgeReplayReport:
    """Remove the purged photos from the restored database and record the deletions. Idempotent: a second run removes nothing."""
    ids = sorted(ledger.asset_ids)
    try:
        conn = await _connect(connect, database)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        raise PurgeReplayError("the restored database cannot be reached") from None
    try:
        async with conn.transaction():
            annotations = _count(await conn.execute(DELETE_ANNOTATIONS, ids))
            attachments = _count(await conn.execute(DELETE_ATTACHMENTS, ids))
            assets = _count(await conn.execute(DELETE_ASSETS, ids))
            added = 0
            for entry in ledger.entries:
                status = await conn.execute(
                    INSERT_LEDGER, entry.id, NIL, NIL, entry.asset_id, entry.storage_name, entry.key_original, entry.key_display,
                    entry.key_thumbnail, entry.sha256, entry.size_original, entry.size_display, entry.size_thumbnail,
                    datetime.fromisoformat(entry.purged_at),
                )
                added += _count(status)
    except (OSError, asyncpg.PostgresError, TimeoutError, ValueError):
        raise PurgeReplayError("the purge could not be replayed") from None
    finally:
        await _close(conn)
    logger.info("purge replay: entries=%d assets=%d attachments=%d annotations=%d", len(ids), assets, attachments, annotations)
    return PurgeReplayReport(len(ids), assets, attachments, annotations, added)
