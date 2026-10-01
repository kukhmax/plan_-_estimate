"""Stage 14C.2 — PhotoAsset compare-and-set transitions and the
non-committing `add_pending` + first-attachment transaction
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §11 steps 10/12/17, C10).
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, update

from app.domain.exceptions import (
    PhotoAssetAlreadyExistsError,
    PhotoAssetNotFoundError,
    PhotoAssetStateError,
    PhotoAssetTransitionConflictError,
    ProjectNotFoundError,
    RoomNotFoundError,
)
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import AttachmentTarget, PhotoAttachmentService
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests.conftest import TestingSessionLocal
from tests.test_estimates import _make_project, _make_room, _make_user
from tests.test_stage14b4_photo_asset import processed, raw_asset

P, R, F = PhotoAssetStatus.PENDING, PhotoAssetStatus.READY, PhotoAssetStatus.FAILED


async def world(db) -> SimpleNamespace:
    me = await _make_user(db, 9001)
    other = await _make_user(db, 9002)
    project = await _make_project(db, me.id)
    foreign_project = await _make_project(db, other.id)
    room = await _make_room(db, project.id)
    foreign_room = await _make_room(db, foreign_project.id)
    return SimpleNamespace(
        me=me.id, other=other.id, project_id=project.id, room_id=room.id, foreign_room_id=foreign_room.id
    )


async def add_asset(db, w, status=P) -> uuid.UUID:
    asset = raw_asset(SimpleNamespace(id=w.me), SimpleNamespace(id=w.project_id), status=status)
    db.add(asset)
    await db.commit()
    return asset.id


async def status_in_db(asset_id) -> PhotoAssetStatus | None:
    """Read through a second session. The test engine shares ONE SQLite
    connection (StaticPool), so this sees committed state only after the
    writer's transaction ended; "not committed" is proven by commit spies
    plus rollback instead."""
    async with TestingSessionLocal() as other:
        return (await other.execute(select(PhotoAsset.status).where(PhotoAsset.id == asset_id))).scalar_one_or_none()


async def counts() -> tuple[int, int]:
    async with TestingSessionLocal() as other:
        assets = (await other.execute(select(func.count()).select_from(PhotoAsset))).scalar_one()
        atts = (await other.execute(select(func.count()).select_from(PhotoAttachment))).scalar_one()
    return assets, atts


# ---------------------------------------------------------------------------
# Compare-and-set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("start", "target"), [(P, R), (P, F), (F, P)])
async def test_cas_applies_allowed_transition_and_commits(db_session, start, target):
    w = await world(db_session)
    asset_id = await add_asset(db_session, w, start)
    asset = await PhotoAssetService(db_session).compare_and_set_status(
        asset_id, w.me, expected=start, target=target
    )
    assert asset.status is target
    assert await status_in_db(asset_id) is target


@pytest.mark.parametrize(("start", "target"), [(R, P), (R, F), (F, R), (P, P)])
async def test_cas_rejects_disallowed_transition_without_writing(db_session, start, target):
    w = await world(db_session)
    asset_id = await add_asset(db_session, w, start)
    with pytest.raises(PhotoAssetStateError) as exc:
        await PhotoAssetService(db_session).compare_and_set_status(asset_id, w.me, expected=start, target=target)
    assert not isinstance(exc.value, PhotoAssetTransitionConflictError)
    assert await status_in_db(asset_id) is start


async def test_cas_loses_race_and_ready_never_regresses(db_session):
    """A parallel request finalized READY; a stale PENDING->FAILED must lose."""
    w = await world(db_session)
    asset_id = await add_asset(db_session, w, P)
    async with TestingSessionLocal() as parallel:
        await PhotoAssetService(parallel).compare_and_set_status(asset_id, w.me, expected=P, target=R)
    with pytest.raises(PhotoAssetTransitionConflictError) as exc:
        await PhotoAssetService(db_session).compare_and_set_status(asset_id, w.me, expected=P, target=F)
    assert exc.value.current_status is R
    assert await status_in_db(asset_id) is R


async def test_second_finalize_reports_ready_conflict(db_session):
    """Two concurrent finalizers: exactly one wins, the loser sees READY."""
    w = await world(db_session)
    asset_id = await add_asset(db_session, w, P)
    service = PhotoAssetService(db_session)
    await service.compare_and_set_status(asset_id, w.me, expected=P, target=R)
    with pytest.raises(PhotoAssetTransitionConflictError) as exc:
        await service.compare_and_set_status(asset_id, w.me, expected=P, target=R)
    assert exc.value.current_status is R


async def test_transition_with_stale_identity_map_does_not_overwrite(db_session):
    """transition() reads the status, but the write is still CAS: a
    stale in-session PENDING cannot overwrite a parallel READY."""
    w = await world(db_session)
    asset_id = await add_asset(db_session, w, P)
    service = PhotoAssetService(db_session)
    loaded = await service.get_for_owner(asset_id, w.me)
    assert loaded.status is P
    async with TestingSessionLocal() as parallel:
        await parallel.execute(update(PhotoAsset).where(PhotoAsset.id == asset_id).values(status=R))
        await parallel.commit()
    with pytest.raises(PhotoAssetTransitionConflictError) as exc:
        await service.transition(asset_id, w.me, F)
    assert exc.value.current_status is R
    assert await status_in_db(asset_id) is R
    assert loaded.status is R  # identity map refreshed by the reload


async def test_cas_foreign_or_missing_is_not_found(db_session):
    w = await world(db_session)
    asset_id = await add_asset(db_session, w, P)
    service = PhotoAssetService(db_session)
    with pytest.raises(PhotoAssetNotFoundError):
        await service.compare_and_set_status(asset_id, w.other, expected=P, target=R)
    with pytest.raises(PhotoAssetNotFoundError):
        await service.compare_and_set_status(uuid.uuid4(), w.me, expected=P, target=R)
    assert await status_in_db(asset_id) is P


# ---------------------------------------------------------------------------
# Non-committing add_pending + first attachment in one transaction
# ---------------------------------------------------------------------------


async def _add_pending(db, w, asset_id=None):
    return await PhotoAssetService(db).add_pending(
        asset_id=asset_id or uuid.uuid4(),
        owner_id=w.me,
        project_id=w.project_id,
        storage_name="r2-primary",
        processed=processed(),
        original_filename="IMG_0001.JPG",
    )


def spy_commits(db, monkeypatch) -> list[None]:
    calls: list[None] = []
    original = db.commit

    async def counting_commit():
        calls.append(None)
        await original()

    monkeypatch.setattr(db, "commit", counting_commit)
    return calls


async def test_add_pending_flushes_but_never_commits(db_session, monkeypatch):
    w = await world(db_session)
    commits = spy_commits(db_session, monkeypatch)
    asset = await _add_pending(db_session, w)
    assert asset.status is P
    assert commits == []
    assert db_session.in_transaction() and asset in db_session and asset not in db_session.new  # flushed
    await db_session.rollback()
    assert await counts() == (0, 0)


async def test_asset_and_first_attachment_commit_together(db_session, monkeypatch):
    w = await world(db_session)
    commits = spy_commits(db_session, monkeypatch)
    asset = await _add_pending(db_session, w)
    att = await PhotoAttachmentService(db_session).add_initial_attachment(
        asset=asset,
        owner_id=w.me,
        target=AttachmentTarget(context=PhotoAttachmentContext.ROOM, room_id=w.room_id),
        category=PhotoCategory.BEFORE,
        caption="  przed  ",
    )
    assert commits == []  # neither service committed: one open transaction
    await db_session.commit()
    assert len(commits) == 1
    assert await counts() == (1, 1)
    async with TestingSessionLocal() as other:
        row = (await other.execute(select(PhotoAttachment).where(PhotoAttachment.id == att.id))).scalar_one()
    assert (row.asset_id, row.project_id, row.room_id) == (asset.id, w.project_id, w.room_id)
    assert (row.category, row.caption, row.position) == (PhotoCategory.BEFORE, "przed", 0)


async def test_rollback_discards_asset_and_first_attachment(db_session):
    w = await world(db_session)
    asset = await _add_pending(db_session, w)
    await PhotoAttachmentService(db_session).add_initial_attachment(
        asset=asset, owner_id=w.me, target=AttachmentTarget(context=PhotoAttachmentContext.PROJECT)
    )
    await db_session.rollback()
    assert await counts() == (0, 0)


async def test_invalid_first_target_leaves_nothing_after_rollback(db_session):
    w = await world(db_session)
    asset = await _add_pending(db_session, w)
    with pytest.raises(RoomNotFoundError):
        await PhotoAttachmentService(db_session).add_initial_attachment(
            asset=asset,
            owner_id=w.me,
            target=AttachmentTarget(context=PhotoAttachmentContext.ROOM, room_id=w.foreign_room_id),
        )
    await db_session.rollback()
    assert await counts() == (0, 0)


@pytest.mark.parametrize("case", ["ready", "foreign_owner"])
async def test_initial_attachment_requires_own_pending_asset(db_session, case):
    w = await world(db_session)
    asset = await _add_pending(db_session, w)
    owner = w.me
    if case == "ready":
        asset.status = R
    else:
        owner = w.other
    with pytest.raises(PhotoAssetNotFoundError):
        await PhotoAttachmentService(db_session).add_initial_attachment(
            asset=asset, owner_id=owner, target=AttachmentTarget(context=PhotoAttachmentContext.PROJECT)
        )
    await db_session.rollback()
    assert await counts() == (0, 0)


async def test_add_pending_existing_id_and_foreign_project(db_session):
    w = await world(db_session)
    asset_id = await add_asset(db_session, w, P)
    with pytest.raises(PhotoAssetAlreadyExistsError):
        await _add_pending(db_session, w, asset_id)
    with pytest.raises(ProjectNotFoundError):
        await PhotoAssetService(db_session).add_pending(
            asset_id=uuid.uuid4(), owner_id=w.other, project_id=w.project_id,
            storage_name="r2-primary", processed=processed(),
        )


async def test_create_pending_still_commits(db_session):
    w = await world(db_session)
    asset = await PhotoAssetService(db_session).create_pending(
        asset_id=uuid.uuid4(), owner_id=w.me, project_id=w.project_id,
        storage_name="r2-primary", processed=processed(),
    )
    assert await status_in_db(asset.id) is P
