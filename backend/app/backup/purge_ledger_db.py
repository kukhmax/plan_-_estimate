"""The database side of the purge ledger export (archive cleanup AC-3): rows -> the exported file, and the owner's report -> `backup_state`."""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.backup.purge_ledger import LedgerEntry
from app.backup.purge_report import PurgeBackupReport
from app.models.purge_ledger import DONE, PENDING, PurgeLedger


def _iso(moment: datetime) -> str:
    value = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def export_entries(db: AsyncSession, *, pending_only: bool = False) -> list[LedgerEntry]:
    stmt = select(PurgeLedger).order_by(PurgeLedger.purged_at, PurgeLedger.asset_id)
    if pending_only:
        stmt = stmt.where(PurgeLedger.backup_state == PENDING)
    return [
        LedgerEntry(
            id=row.id, asset_id=row.asset_id, storage_name=row.storage_name, key_original=row.storage_key_original,
            key_display=row.storage_key_display, key_thumbnail=row.storage_key_thumbnail, sha256=row.sha256,
            size_original=row.byte_size, size_display=row.display_byte_size, size_thumbnail=row.thumbnail_byte_size, purged_at=_iso(row.purged_at),
        )
        for row in (await db.execute(stmt)).scalars()
    ]


async def mark_backup_done(db: AsyncSession, report: PurgeBackupReport, *, now: datetime | None = None) -> int:
    """Mark the rows whose copies the owner's tool found gone from the backup bucket. Only the PRODUCTION bucket counts: a rehearsal in the
    drill bucket must never mark a row. Returns how many rows were marked."""
    if report.bucket_kind != "prod":
        return 0
    ids: list[uuid.UUID] = [entry.asset_id for entry in report.entries if entry.clean]
    if not ids:
        return 0
    moment = now or datetime.now(UTC)
    result = await db.execute(
        update(PurgeLedger).where(PurgeLedger.asset_id.in_(ids), PurgeLedger.backup_state == PENDING).values(backup_state=DONE, backup_done_at=moment)
    )
    await db.commit()
    return result.rowcount or 0
