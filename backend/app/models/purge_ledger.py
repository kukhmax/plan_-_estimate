"""The ledger of what was deleted for good (archive cleanup AC-2): one row per deleted photo file set.

It holds **no content and no names** -- only the storage keys, the sums and sizes, the time, and two states: whether the objects were
removed from the working storage (`storage_state`) and from the backups (`backup_state`, done by the owner's separate script, AC-3).
It is deliberately **not tied to any other table** (plain ids, no foreign keys): the rows of the photo, of its object and of its owner may
all be gone while the obligation to clean the backups remains. A restore from an old backup replays this ledger (AC-3).
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import CHAR, BigInteger, CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

PENDING = "PENDING"
DONE = "DONE"


def _now() -> datetime:
    return datetime.now(UTC)


class PurgeLedger(Base):
    __tablename__ = "purge_ledger"
    __table_args__ = (
        CheckConstraint("kind IN ('PHOTO')", name="ck_purge_ledger_kind"),
        CheckConstraint("storage_state IN ('PENDING', 'DONE')", name="ck_purge_ledger_storage_state"),
        CheckConstraint("backup_state IN ('PENDING', 'DONE')", name="ck_purge_ledger_backup_state"),
        CheckConstraint("storage_state <> 'DONE' OR storage_done_at IS NOT NULL", name="ck_purge_ledger_storage_done_at"),
        CheckConstraint("backup_state <> 'DONE' OR backup_done_at IS NOT NULL", name="ck_purge_ledger_backup_done_at"),
        Index("ix_purge_ledger_owner_states", "owner_id", "storage_state", "backup_state"),
        Index("uq_purge_ledger_asset", "asset_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="PHOTO")
    storage_name: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key_original: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key_display: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key_thumbnail: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    thumbnail_byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    storage_state: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING)
    storage_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    backup_state: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING)
    backup_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def keys(self) -> list[str]:
        return [self.storage_key_thumbnail, self.storage_key_display, self.storage_key_original]
