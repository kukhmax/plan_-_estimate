"""Stage 14C.3 — logical / reserved quota accounting (contract §15, C8)."""

import uuid
from datetime import UTC, datetime

import pytest

from app.domain.services.photo_quota import (
    PhotoStorageState,
    exceeds_soft_cap,
    logical_usage_bytes,
    storage_state,
)
from app.models.photo_asset import PhotoAssetStatus
from tests.test_estimates import _make_project, _make_user
from tests.test_stage14b4_photo_asset import raw_asset


async def add(db, user, project, status, sizes=(1000, 200, 30), archived=False):
    db.add(raw_asset(
        user, project, status=status, byte_size=sizes[0], display_byte_size=sizes[1], thumbnail_byte_size=sizes[2],
        archived_at=datetime.now(UTC) if archived else None,
    ))
    await db.commit()


async def test_usage_sums_reserved_sizes_of_every_status_and_archived(db_session):
    me = await _make_user(db_session, 6401)
    other = await _make_user(db_session, 6402)
    mine = await _make_project(db_session, me.id)
    theirs = await _make_project(db_session, other.id)
    assert await logical_usage_bytes(db_session, me.id) == 0
    for status in PhotoAssetStatus:
        await add(db_session, me, mine, status)
    await add(db_session, me, mine, PhotoAssetStatus.READY, archived=True)
    await add(db_session, other, theirs, PhotoAssetStatus.READY, sizes=(10**9, 1, 1))
    assert await logical_usage_bytes(db_session, me.id) == 4 * 1230
    assert await logical_usage_bytes(db_session, uuid.uuid4()) == 0


@pytest.mark.parametrize(
    ("usage", "state"),
    [(0, PhotoStorageState.OK), (7_999_999_999, PhotoStorageState.OK), (8_000_000_000, PhotoStorageState.WARNING),
     (9_999_999_999, PhotoStorageState.WARNING), (10_000_000_000, PhotoStorageState.FULL),
     (12_000_000_000, PhotoStorageState.FULL)],
)
def test_storage_state_thresholds(usage, state):
    assert storage_state(usage, warning_bytes=8_000_000_000, soft_cap_bytes=10_000_000_000) is state


def test_soft_cap_rule_is_strictly_greater():
    assert exceeds_soft_cap(9, 1, soft_cap_bytes=10) is False
    assert exceeds_soft_cap(9, 2, soft_cap_bytes=10) is True
    assert exceeds_soft_cap(10, 0, soft_cap_bytes=10) is False


def test_quota_module_never_touches_storage():
    import app.domain.services.photo_quota as quota

    with open(quota.__file__) as fh:
        source = fh.read()
    assert "MediaStorage" not in source and "head_object" not in source and "iter_keys" not in source
