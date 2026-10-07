"""Stage 14C.5 — photo read model: visibility views, ownership chain,
ordering and the opaque, filter-bound keyset cursor
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §18, §21, §11c)."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.domain.exceptions import (
    PhotoAssetNotFoundError,
    PhotoAttachmentValidationError,
    PhotoContextNotSupportedError,
    PhotoCursorInvalidError,
    ProjectNotFoundError,
    RoomNotFoundError,
)
from app.domain.services.photo_query_service import (
    MAX_LIMIT,
    PhotoListFilters,
    PhotoQueryService,
    decode_cursor,
)
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests.test_estimates import _make_project, _make_room, _make_user
from tests.test_stage14b4_photo_asset import raw_asset

C = PhotoAttachmentContext
T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def world(db) -> SimpleNamespace:
    me = await _make_user(db, 7501)
    other = await _make_user(db, 7502)
    project = await _make_project(db, me.id)
    project2 = await _make_project(db, me.id, name="Drugi")
    room = await _make_room(db, project.id)
    room2 = await _make_room(db, project.id, name="Kuchnia")
    return SimpleNamespace(me=me, other=other, project=project, project2=project2, room=room, room2=room2)


async def photo(db, w, *, minute=0, position=0, status=PhotoAssetStatus.READY, context=C.PROJECT,
                room=None, project=None, att_project=None, asset_archived=False, att_archived=False,
                category=PhotoCategory.GENERAL, include=False, owner=None):
    project = project or w.project
    asset = raw_asset(owner or w.me, project, status=status, uploaded_at=T0 + timedelta(minutes=minute),
                      archived_at=T0 if asset_archived else None)
    db.add(asset)
    await db.flush()
    att = PhotoAttachment(
        asset_id=asset.id, project_id=(att_project or project).id, context=context,
        room_id=room.id if room else None, category=category, include_in_report=include,
        position=position, archived_at=T0 if att_archived else None,
    )
    db.add(att)
    await db.commit()
    return asset, att


def ids(page) -> list[uuid.UUID]:
    return [att.id for att, _ in page.items]


async def test_normal_view_is_active_attachment_and_active_ready_asset(db_session):
    w = await world(db_session)
    _, visible = await photo(db_session, w)
    await photo(db_session, w, minute=1, att_archived=True)
    await photo(db_session, w, minute=2, asset_archived=True)
    await photo(db_session, w, minute=3, status=PhotoAssetStatus.PENDING)
    await photo(db_session, w, minute=4, status=PhotoAssetStatus.FAILED)
    page = await PhotoQueryService(db_session).list_photos(w.me.id, w.project.id, PhotoListFilters())
    assert ids(page) == [visible.id] and page.next_cursor is None


async def test_archive_view_is_archived_attachment_or_archived_asset_only(db_session):
    w = await world(db_session)
    await photo(db_session, w)  # active: not in the archive view
    _, a = await photo(db_session, w, minute=1, att_archived=True)
    _, b = await photo(db_session, w, minute=2, asset_archived=True)  # active attachment of an archived asset
    _, c = await photo(db_session, w, minute=3, att_archived=True, asset_archived=True)
    await photo(db_session, w, minute=4, status=PhotoAssetStatus.PENDING, att_archived=True)
    page = await PhotoQueryService(db_session).list_photos(w.me.id, w.project.id, PhotoListFilters(archived=True))
    assert ids(page) == [a.id, b.id, c.id]


async def test_ownership_chain_is_enforced_even_against_corrupted_rows(db_session):
    w = await world(db_session)
    _, mine = await photo(db_session, w)
    # attachment says project2, asset is in project: must be invisible everywhere
    await photo(db_session, w, minute=1, att_project=w.project2)
    # foreign owner's asset in my project row (corrupted): invisible
    await photo(db_session, w, minute=2, owner=w.other)
    service = PhotoQueryService(db_session)
    assert ids(await service.list_photos(w.me.id, w.project.id, PhotoListFilters())) == [mine.id]
    assert ids(await service.list_photos(w.me.id, w.project2.id, PhotoListFilters())) == []
    with pytest.raises(ProjectNotFoundError):
        await service.list_photos(w.other.id, w.project.id, PhotoListFilters())


async def test_filters(db_session):
    w = await world(db_session)
    _, p = await photo(db_session, w)
    _, r = await photo(db_session, w, minute=1, context=C.ROOM, room=w.room, category=PhotoCategory.DEFECT,
                       include=True)
    _, r2 = await photo(db_session, w, minute=2, context=C.ROOM, room=w.room2)
    service = PhotoQueryService(db_session)
    q = lambda **f: service.list_photos(w.me.id, w.project.id, PhotoListFilters(**f))  # noqa: E731
    assert ids(await q()) == [p.id, r.id, r2.id]
    assert ids(await q(context=C.PROJECT)) == [p.id]
    assert ids(await q(context=C.ROOM, room_id=w.room.id)) == [r.id]
    assert ids(await q(category=PhotoCategory.DEFECT)) == [r.id]
    assert ids(await q(include_in_report=True)) == [r.id]
    assert ids(await q(include_in_report=False)) == [p.id, r2.id]


@pytest.mark.parametrize(
    ("filters", "error"),
    [
        (lambda w: PhotoListFilters(room_id=w.room.id), PhotoAttachmentValidationError),  # target without context
        (lambda w: PhotoListFilters(context=C.ROOM), PhotoAttachmentValidationError),  # context without target
        (lambda w: PhotoListFilters(context=C.PROJECT, room_id=w.room.id), PhotoAttachmentValidationError),
        (lambda w: PhotoListFilters(context=C.ROOM, room_id=uuid.uuid4()), RoomNotFoundError),
        (lambda w: PhotoListFilters(context=C.WORK), PhotoContextNotSupportedError),
    ],
    ids=["target-no-context", "context-no-target", "project-with-room", "foreign-room", "inspection"],
)
async def test_filter_validation(db_session, filters, error):
    w = await world(db_session)
    with pytest.raises(error):
        await PhotoQueryService(db_session).list_photos(w.me.id, w.project.id, filters(w))


async def test_ordering_position_then_uploaded_at_then_id(db_session):
    w = await world(db_session)
    _, late_pos0 = await photo(db_session, w, minute=9, position=0)
    _, early_pos1 = await photo(db_session, w, minute=1, position=1)
    _, early_pos0 = await photo(db_session, w, minute=1, position=0)
    tie = [await photo(db_session, w, minute=5, position=0) for _ in range(3)]
    page = await PhotoQueryService(db_session).list_photos(w.me.id, w.project.id, PhotoListFilters())
    tie_ids = sorted(att.id for _, att in tie)
    assert ids(page) == [early_pos0.id, *tie_ids, late_pos0.id, early_pos1.id]


async def test_keyset_pages_have_no_gaps_or_duplicates(db_session):
    w = await world(db_session)
    for i in range(11):
        await photo(db_session, w, minute=i % 4, position=i % 3)
    service = PhotoQueryService(db_session)
    full = ids(await service.list_photos(w.me.id, w.project.id, PhotoListFilters(), limit=MAX_LIMIT))
    seen, cursor = [], None
    while True:
        page = await service.list_photos(w.me.id, w.project.id, PhotoListFilters(), limit=3, cursor=cursor)
        seen += ids(page)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert seen == full and len(set(seen)) == 11


@pytest.mark.parametrize("limit", [0, MAX_LIMIT + 1])
async def test_limit_bounds(db_session, limit):
    w = await world(db_session)
    with pytest.raises(PhotoAttachmentValidationError):
        await PhotoQueryService(db_session).list_photos(w.me.id, w.project.id, PhotoListFilters(), limit=limit)


async def first_cursor(db, w, filters=PhotoListFilters()):
    for i in range(3):
        await photo(db, w, minute=i)
    page = await PhotoQueryService(db).list_photos(w.me.id, w.project.id, filters, limit=1)
    assert page.next_cursor
    return page.next_cursor


@pytest.mark.parametrize(
    "other_filters",
    [PhotoListFilters(archived=True), PhotoListFilters(category=PhotoCategory.BEFORE),
     PhotoListFilters(include_in_report=False)],
    ids=["archive-view", "category", "include"],
)
async def test_cursor_is_bound_to_its_filter_set(db_session, other_filters):
    w = await world(db_session)
    cursor = await first_cursor(db_session, w)
    with pytest.raises(PhotoCursorInvalidError):
        await PhotoQueryService(db_session).list_photos(w.me.id, w.project.id, other_filters, cursor=cursor)


async def test_cursor_is_bound_to_its_project(db_session):
    w = await world(db_session)
    cursor = await first_cursor(db_session, w)
    with pytest.raises(PhotoCursorInvalidError):
        await PhotoQueryService(db_session).list_photos(w.me.id, w.project2.id, PhotoListFilters(), cursor=cursor)


def reencode(payload) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


def valid_payload(fp: str) -> dict:
    return {"v": 1, "p": 0, "u": T0.isoformat(), "i": str(uuid.uuid4()), "f": fp}


FP = "f" * 32


@pytest.mark.parametrize(
    "cursor",
    [
        "", "not base64!", "%%%%", "a" * 600, base64.urlsafe_b64encode(b"\xff\xfe").decode().rstrip("="),
        reencode([1, 2, 3]), reencode({**valid_payload(FP), "extra": 1}),
        reencode({k: v for k, v in valid_payload(FP).items() if k != "i"}),
        reencode({**valid_payload(FP), "v": 2}), reencode({**valid_payload(FP), "v": True}),
        reencode({**valid_payload(FP), "p": -1}), reencode({**valid_payload(FP), "p": True}),
        reencode({**valid_payload(FP), "p": "0"}), reencode({**valid_payload(FP), "i": "not-a-uuid"}),
        reencode({**valid_payload(FP), "u": "yesterday"}), reencode({**valid_payload(FP), "f": "0" * 32}),
        reencode({**valid_payload(FP), "u": "DROP TABLE photo_attachments"}),
    ],
)
def test_malformed_schema_invalid_or_mismatched_cursor_rejected(cursor):
    with pytest.raises(PhotoCursorInvalidError):
        decode_cursor(cursor, FP)


def test_valid_cursor_decodes_to_typed_values_only():
    payload = valid_payload(FP)
    decoded = decode_cursor(reencode(payload), FP)
    assert (decoded.position, decoded.uploaded_at, str(decoded.attachment_id)) == (0, T0, payload["i"])


async def test_detail_requires_ready_owned_asset_and_lists_all_attachments(db_session):
    w = await world(db_session)
    asset, first = await photo(db_session, w, asset_archived=True)
    second = PhotoAttachment(asset_id=asset.id, project_id=w.project.id, context=C.ROOM, room_id=w.room.id,
                             category=PhotoCategory.GENERAL, archived_at=T0)
    corrupt = PhotoAttachment(asset_id=asset.id, project_id=w.project2.id, context=C.PROJECT,
                              category=PhotoCategory.GENERAL, archived_at=T0)  # cross-project row
    db_session.add_all([second, corrupt])
    await db_session.commit()
    service = PhotoQueryService(db_session)
    got, attachments = await service.get_detail(w.me.id, w.project.id, asset.id)
    assert got.id == asset.id and [a.id for a in attachments] == [first.id, second.id]  # corrupt row excluded
    for status in (PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED):
        hidden, _ = await photo(db_session, w, status=status)
        with pytest.raises(PhotoAssetNotFoundError):
            await service.get_detail(w.me.id, w.project.id, hidden.id)
    with pytest.raises(PhotoAssetNotFoundError):
        await service.get_detail(w.me.id, w.project2.id, asset.id)
    with pytest.raises(ProjectNotFoundError):
        await service.get_detail(w.other.id, w.project.id, asset.id)
