"""Stage 14C.2 — PhotoAttachmentService: target chain, supported contexts,
duplicates, metadata patch and attachment archive/restore
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §4–§7, §16, §18, C1, C12).
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.domain.exceptions import (
    OpeningNotFoundError,
    PhotoAssetNotFoundError,
    PhotoAttachmentDuplicateError,
    PhotoAttachmentNotFoundError,
    PhotoAttachmentValidationError,
    PhotoContextNotSupportedError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.domain.services.photo_attachment_service import (
    AttachmentTarget,
    PhotoAttachmentService,
    normalize_caption,
)
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.room import Room
from tests.test_estimates import _make_opening, _make_project, _make_room, _make_surface, _make_user
from tests.test_stage14b4_photo_asset import raw_asset

C = PhotoAttachmentContext


async def site(db, user, project=None) -> SimpleNamespace:
    project = project or await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    opening = await _make_opening(db, surface.id)
    return SimpleNamespace(project_id=project.id, room_id=room.id, surface_id=surface.id, opening_id=opening.id)


async def add_asset(db, user_id, project_id, status=PhotoAssetStatus.READY, **kw):
    asset = raw_asset(SimpleNamespace(id=user_id), SimpleNamespace(id=project_id), status=status, **kw)
    db.add(asset)
    await db.commit()
    return asset.id


async def world(db) -> SimpleNamespace:
    me = await _make_user(db, 8001)
    other = await _make_user(db, 8002)
    mine = await site(db, me)
    second = await site(db, me)  # my second project
    foreign = await site(db, other)
    asset_id = await add_asset(db, me.id, mine.project_id)
    return SimpleNamespace(
        me=me.id, other=other.id, mine=mine, second=second, foreign=foreign, asset_id=asset_id
    )


def target_for(s, context) -> AttachmentTarget:
    ids = {
        C.PROJECT: {},
        C.ROOM: {"room_id": s.room_id},
        C.SURFACE: {"surface_id": s.surface_id},
        C.OPENING: {"opening_id": s.opening_id},
    }[context]
    return AttachmentTarget(context=context, **ids)


async def attach(db, w, context=C.ROOM, *, asset_id=None, target=None, **kw) -> PhotoAttachment:
    return await PhotoAttachmentService(db).create_attachment(
        owner_id=kw.pop("owner_id", w.me),
        project_id=kw.pop("project_id", w.mine.project_id),
        asset_id=asset_id or w.asset_id,
        target=target or target_for(w.mine, context),
        **kw,
    )


async def count(db) -> int:
    return (await db.execute(select(func.count()).select_from(PhotoAttachment))).scalar_one()


# ---------------------------------------------------------------------------
# Creation per supported context
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("context", [C.PROJECT, C.ROOM, C.SURFACE, C.OPENING])
async def test_create_supported_context_with_defaults(db_session, context):
    w = await world(db_session)
    att = await attach(db_session, w, context)
    assert att.context is context
    assert att.asset_id == w.asset_id and att.project_id == w.mine.project_id
    assert att.category is PhotoCategory.GENERAL
    assert att.caption is None and att.include_in_report is False and att.position == 0
    assert att.archived_at is None
    expected = target_for(w.mine, context).ids()
    assert {k: getattr(att, k) for k in expected} == expected
    assert att.inspection_id is att.question_id is att.finding_id is att.occurrence_key is att.price_item_id is None


@pytest.mark.parametrize("context", [C.WORK])  # INSPECTION / FINDING are enabled since 14F.2 (own tests)
async def test_future_contexts_not_supported(db_session, context):
    w = await world(db_session)
    with pytest.raises(PhotoContextNotSupportedError) as exc:
        await attach(db_session, w, target=AttachmentTarget(context=context))
    assert exc.value.code == "PHOTO_CONTEXT_NOT_SUPPORTED"
    assert await count(db_session) == 0


@pytest.mark.parametrize(
    "target_fn",
    [
        lambda s: AttachmentTarget(context=C.PROJECT, room_id=s.room_id),
        lambda s: AttachmentTarget(context=C.ROOM),
        lambda s: AttachmentTarget(context=C.ROOM, room_id=s.room_id, surface_id=s.surface_id),
        lambda s: AttachmentTarget(context=C.SURFACE, room_id=s.room_id),
        lambda s: AttachmentTarget(context=C.OPENING, opening_id=s.opening_id, surface_id=s.surface_id),
    ],
    ids=["project+room", "room-missing", "room+surface", "surface-missing", "opening+surface"],
)
async def test_target_shape_rejected(db_session, target_fn):
    w = await world(db_session)
    with pytest.raises(PhotoAttachmentValidationError):
        await attach(db_session, w, target=target_fn(w.mine))
    assert await count(db_session) == 0


@pytest.mark.parametrize(
    ("context", "error"),
    [(C.ROOM, RoomNotFoundError), (C.SURFACE, SurfaceNotFoundError), (C.OPENING, OpeningNotFoundError)],
)
@pytest.mark.parametrize("source", ["foreign", "second", "missing"])
async def test_target_outside_project_is_not_found(db_session, context, error, source):
    w = await world(db_session)
    if source == "missing":
        target = AttachmentTarget(context=context, **{_col(context): uuid.uuid4()})
    else:
        target = target_for(getattr(w, source), context)
    with pytest.raises(error):
        await attach(db_session, w, target=target)
    assert await count(db_session) == 0


def _col(context) -> str:
    return {C.ROOM: "room_id", C.SURFACE: "surface_id", C.OPENING: "opening_id"}[context]


async def test_foreign_project_is_not_found(db_session):
    w = await world(db_session)
    with pytest.raises(ProjectNotFoundError):
        await attach(db_session, w, C.PROJECT, project_id=w.foreign.project_id)
    with pytest.raises(ProjectNotFoundError):
        await attach(db_session, w, C.PROJECT, owner_id=w.other)


@pytest.mark.parametrize("case", ["missing", "foreign_owner", "other_project", "pending", "failed"])
async def test_invisible_asset_is_not_found(db_session, case):
    w = await world(db_session)
    if case == "missing":
        asset_id = uuid.uuid4()
    elif case == "foreign_owner":
        asset_id = await add_asset(db_session, w.other, w.foreign.project_id)
    elif case == "other_project":
        asset_id = await add_asset(db_session, w.me, w.second.project_id)
    else:
        status = PhotoAssetStatus.PENDING if case == "pending" else PhotoAssetStatus.FAILED
        asset_id = await add_asset(db_session, w.me, w.mine.project_id, status=status)
    with pytest.raises(PhotoAssetNotFoundError):
        await attach(db_session, w, C.PROJECT, asset_id=asset_id)
    assert await count(db_session) == 0


async def test_archived_ready_asset_may_be_attached(db_session):
    w = await world(db_session)
    asset_id = await add_asset(db_session, w.me, w.mine.project_id, archived_at=datetime.now(timezone.utc))
    att = await attach(db_session, w, C.PROJECT, asset_id=asset_id)
    assert att.asset_id == asset_id


async def test_archived_target_is_accepted(db_session):
    """C12: no new archived-parent prohibition in 14C."""
    w = await world(db_session)
    room = await db_session.get(Room, w.mine.room_id)
    room.is_archived = True
    await db_session.commit()
    att = await attach(db_session, w, C.ROOM)
    assert att.room_id == w.mine.room_id


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------


def test_normalize_caption():
    assert normalize_caption(None) is None
    assert normalize_caption("   ") is None
    assert normalize_caption("  Pęknięcie przy oknie \n") == "Pęknięcie przy oknie"
    assert normalize_caption("x" * 1000) == "x" * 1000
    assert normalize_caption("  " + "x" * 1000 + "  ") == "x" * 1000
    with pytest.raises(PhotoAttachmentValidationError):
        normalize_caption("x" * 1001)


@pytest.mark.parametrize(
    "kw",
    [{"position": -1}, {"position": True}, {"category": "DEFECT"}, {"include_in_report": 1}, {"caption": 5}],
    ids=["negative-position", "bool-position", "str-category", "int-include", "non-text-caption"],
)
async def test_invalid_fields_rejected(db_session, kw):
    w = await world(db_session)
    with pytest.raises(PhotoAttachmentValidationError):
        await attach(db_session, w, C.PROJECT, **kw)
    assert await count(db_session) == 0


async def test_explicit_fields_persisted(db_session):
    w = await world(db_session)
    att = await attach(
        db_session, w, C.SURFACE,
        category=PhotoCategory.DEFECT, caption="  rysa  ", include_in_report=True, position=3,
    )
    assert (att.category, att.caption, att.include_in_report, att.position) == (
        PhotoCategory.DEFECT, "rysa", True, 3,
    )


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("context", [C.PROJECT, C.ROOM, C.SURFACE, C.OPENING])
async def test_duplicate_active_attachment_rejected(db_session, context):
    w = await world(db_session)
    await attach(db_session, w, context)
    with pytest.raises(PhotoAttachmentDuplicateError) as exc:
        await attach(db_session, w, context, caption="different metadata")
    assert exc.value.code == "PHOTO_ATTACHMENT_DUPLICATE"
    assert await count(db_session) == 1


async def test_same_asset_may_attach_to_several_contexts(db_session):
    w = await world(db_session)
    for context in (C.PROJECT, C.ROOM, C.SURFACE, C.OPENING):
        await attach(db_session, w, context)
    room2 = await _make_room(db_session, w.mine.project_id, name="Kuchnia")
    await attach(db_session, w, target=AttachmentTarget(context=C.ROOM, room_id=room2.id))
    assert await count(db_session) == 5


async def test_unique_index_is_authoritative_when_precheck_misses(db_session, monkeypatch):
    """A concurrent writer slipping past the pre-check still surfaces as the
    domain duplicate error, and the session stays usable."""
    w = await world(db_session)
    await attach(db_session, w, C.ROOM)

    async def no_duplicate(self, attachment):
        return False

    monkeypatch.setattr(PhotoAttachmentService, "_active_duplicate_exists", no_duplicate)
    with pytest.raises(PhotoAttachmentDuplicateError):
        await attach(db_session, w, C.ROOM)
    assert await count(db_session) == 1


# ---------------------------------------------------------------------------
# Read / PATCH
# ---------------------------------------------------------------------------


async def test_get_attachment_scoping(db_session):
    w = await world(db_session)
    att = await attach(db_session, w, C.ROOM)
    service = PhotoAttachmentService(db_session)
    assert (await service.get_attachment(w.me, w.mine.project_id, att.id)).id == att.id
    for owner, project, att_id in [
        (w.other, w.mine.project_id, att.id),
        (w.me, w.second.project_id, att.id),
        (w.me, w.mine.project_id, uuid.uuid4()),
    ]:
        with pytest.raises(PhotoAttachmentNotFoundError) as exc:
            await service.get_attachment(owner, project, att_id)
        assert exc.value.code == "PHOTO_ATTACHMENT_NOT_FOUND"


@pytest.mark.parametrize("status", [PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED])
async def test_attachment_of_not_ready_asset_is_invisible(db_session, status):
    w = await world(db_session)
    asset_id = await add_asset(db_session, w.me, w.mine.project_id, status=status)
    row = PhotoAttachment(
        asset_id=asset_id, project_id=w.mine.project_id, context=C.PROJECT, category=PhotoCategory.GENERAL
    )
    db_session.add(row)
    await db_session.commit()
    with pytest.raises(PhotoAttachmentNotFoundError):
        await PhotoAttachmentService(db_session).get_attachment(w.me, w.mine.project_id, row.id)


async def test_patch_changes_only_given_fields(db_session):
    w = await world(db_session)
    att = await attach(db_session, w, C.ROOM, caption="a", category=PhotoCategory.BEFORE, position=2)
    service = PhotoAttachmentService(db_session)
    patched = await service.update_attachment(w.me, w.mine.project_id, att.id, include_in_report=True)
    assert (patched.caption, patched.category, patched.position, patched.include_in_report) == (
        "a", PhotoCategory.BEFORE, 2, True,
    )
    patched = await service.update_attachment(w.me, w.mine.project_id, att.id, caption="   ", position=0)
    assert patched.caption is None and patched.position == 0
    patched = await service.update_attachment(w.me, w.mine.project_id, att.id, category=PhotoCategory.AFTER)
    assert patched.category is PhotoCategory.AFTER
    assert patched.context is C.ROOM and patched.room_id == w.mine.room_id  # target immutable


@pytest.mark.parametrize(
    "kw", [{"category": None}, {"position": -5}, {"caption": "x" * 1001}, {"include_in_report": None}]
)
async def test_patch_rejects_invalid_values(db_session, kw):
    w = await world(db_session)
    att = await attach(db_session, w, C.ROOM, caption="keep")
    with pytest.raises(PhotoAttachmentValidationError):
        await PhotoAttachmentService(db_session).update_attachment(w.me, w.mine.project_id, att.id, **kw)


async def test_patch_foreign_is_not_found(db_session):
    w = await world(db_session)
    att = await attach(db_session, w, C.ROOM)
    with pytest.raises(PhotoAttachmentNotFoundError):
        await PhotoAttachmentService(db_session).update_attachment(w.other, w.mine.project_id, att.id, position=1)


# ---------------------------------------------------------------------------
# Archive / restore
# ---------------------------------------------------------------------------


async def test_archive_and_restore_are_idempotent(db_session):
    w = await world(db_session)
    att = await attach(db_session, w, C.SURFACE)
    service = PhotoAttachmentService(db_session)
    archived = await service.archive_attachment(w.me, w.mine.project_id, att.id)
    first_archived_at = archived.archived_at
    assert first_archived_at is not None
    again = await service.archive_attachment(w.me, w.mine.project_id, att.id)
    assert again.archived_at == first_archived_at
    restored = await service.restore_attachment(w.me, w.mine.project_id, att.id)
    assert restored.archived_at is None
    assert (await service.restore_attachment(w.me, w.mine.project_id, att.id)).archived_at is None


async def test_archived_duplicate_allows_new_and_blocks_restore(db_session):
    w = await world(db_session)
    service = PhotoAttachmentService(db_session)
    old = await attach(db_session, w, C.OPENING)
    await service.archive_attachment(w.me, w.mine.project_id, old.id)
    new = await attach(db_session, w, C.OPENING)
    assert new.id != old.id
    with pytest.raises(PhotoAttachmentDuplicateError):
        await service.restore_attachment(w.me, w.mine.project_id, old.id)
    await service.archive_attachment(w.me, w.mine.project_id, new.id)
    assert (await service.restore_attachment(w.me, w.mine.project_id, old.id)).archived_at is None


async def test_restore_duplicate_detected_by_index_when_precheck_misses(db_session, monkeypatch):
    w = await world(db_session)
    service = PhotoAttachmentService(db_session)
    old = await attach(db_session, w, C.PROJECT)
    old_id = old.id  # the failed commit's rollback expires loaded instances
    await service.archive_attachment(w.me, w.mine.project_id, old_id)
    await attach(db_session, w, C.PROJECT)

    async def no_duplicate(self, attachment):
        return False

    monkeypatch.setattr(PhotoAttachmentService, "_active_duplicate_exists", no_duplicate)
    with pytest.raises(PhotoAttachmentDuplicateError):
        await service.restore_attachment(w.me, w.mine.project_id, old_id)
    row = await service.get_attachment(w.me, w.mine.project_id, old_id)
    await db_session.refresh(row)
    assert row.archived_at is not None  # rolled back, still archived


async def test_archive_foreign_is_not_found(db_session):
    w = await world(db_session)
    att = await attach(db_session, w, C.ROOM)
    service = PhotoAttachmentService(db_session)
    with pytest.raises(PhotoAttachmentNotFoundError):
        await service.archive_attachment(w.other, w.mine.project_id, att.id)
    with pytest.raises(PhotoAttachmentNotFoundError):
        await service.restore_attachment(w.other, w.mine.project_id, att.id)
