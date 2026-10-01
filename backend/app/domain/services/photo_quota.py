"""Logical / reserved photo storage accounting (Stage 14C.3; contract §15, C8).

Usage per owner = SUM(byte_size + display_byte_size + thumbnail_byte_size)
over the owner's photo_assets in READY, PENDING and FAILED, archived
included. This is reserved accounting from the recorded sizes, NOT physical
R2 usage: the bucket is never scanned, nothing is cached, there is no quota
table. Only NEW uploads are checked (inside the processing slot, right before
the PENDING insert); replays and resumes are never quota-rejected.
"""

import uuid
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo_asset import PhotoAsset, PhotoAssetStatus

COUNTED_STATUSES = (PhotoAssetStatus.READY, PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED)


class PhotoStorageState(StrEnum):
    OK = "OK"
    WARNING = "WARNING"
    FULL = "FULL"


async def logical_usage_bytes(db: AsyncSession, owner_id: uuid.UUID) -> int:
    stmt = select(
        func.coalesce(
            func.sum(PhotoAsset.byte_size + PhotoAsset.display_byte_size + PhotoAsset.thumbnail_byte_size), 0
        )
    ).where(PhotoAsset.owner_id == owner_id, PhotoAsset.status.in_(COUNTED_STATUSES))
    return int((await db.execute(stmt)).scalar_one())


def storage_state(usage_bytes: int, *, warning_bytes: int, soft_cap_bytes: int) -> PhotoStorageState:
    """OK < warning <= WARNING < soft cap <= FULL."""
    if usage_bytes >= soft_cap_bytes:
        return PhotoStorageState.FULL
    if usage_bytes >= warning_bytes:
        return PhotoStorageState.WARNING
    return PhotoStorageState.OK


def exceeds_soft_cap(usage_bytes: int, new_bytes: int, *, soft_cap_bytes: int) -> bool:
    """New-upload rejection rule: usage + the three new sizes > soft cap."""
    return usage_bytes + new_bytes > soft_cap_bytes
