"""Stage 14B.4 — PhotoAsset model, constraints and persistence primitives."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import (
    PhotoAssetAlreadyExistsError,
    PhotoAssetNotFoundError,
    PhotoAssetStateError,
    PhotoAssetValidationError,
    ProjectNotFoundError,
)
from app.domain.photos.image_processing import DerivativeInfo, ProcessedImage
from app.domain.photos.keys import PhotoFormat
from app.domain.services.photo_asset_service import (
    ALLOWED_TRANSITIONS,
    PhotoAssetService,
    sanitize_original_filename,
)
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType
from app.models.project import Project
from tests.test_estimates import _make_project, _make_user

SHA = "ab" * 32


def processed(**overrides) -> ProcessedImage:
    base = dict(
        format=PhotoFormat.JPEG,
        extension="jpg",
        content_type="image/jpeg",
        byte_size=1_234_567,
        sha256=SHA,
        stored_width=4000,
        stored_height=3000,
        width=3000,
        height=4000,
        exif_orientation=6,
        captured_at=datetime(2026, 9, 28, 10, 11, 12),
        display=DerivativeInfo(path=Path("display.jpg"), width=1536, height=2048, byte_size=450_000),
        thumbnail=DerivativeInfo(path=Path("thumb.jpg"), width=360, height=480, byte_size=25_000),
    )
    base.update(overrides)
    return ProcessedImage(**base)


async def setup(db, tg=5001):
    user = await _make_user(db, tg)
    project = await _make_project(db, user.id)
    return user, project


async def create(db, user, project, asset_id=None, **kw):
    return await PhotoAssetService(db).create_pending(
        asset_id=asset_id or uuid.uuid4(),
        owner_id=user.id,
        project_id=project.id,
        storage_name=kw.pop("storage_name", "r2-primary"),
        processed=kw.pop("processed", processed()),
        original_filename=kw.pop("original_filename", "IMG_0001.JPG"),
    )


def raw_asset(user, project, **overrides) -> PhotoAsset:
    asset_id = overrides.pop("id", uuid.uuid4())
    values = dict(
        id=asset_id,
        owner_id=user.id,
        project_id=project.id,
        status=PhotoAssetStatus.PENDING,
        storage_name="r2-primary",
        storage_key_original=f"photos/v1/{asset_id}/original.jpg",
        storage_key_display=f"photos/v1/{asset_id}/display.jpg",
        storage_key_thumbnail=f"photos/v1/{asset_id}/thumb.jpg",
        content_type=PhotoContentType.JPEG,
        byte_size=10,
        display_byte_size=5,
        thumbnail_byte_size=2,
        width=1,
        height=1,
        sha256=SHA,
    )
    values.update(overrides)
    return PhotoAsset(**values)


# --------------------------------------------------------------------------
# Persistence round trip
# --------------------------------------------------------------------------


async def test_create_pending_round_trip(db_session):
    user, project = await setup(db_session)
    user_id, project_id = user.id, project.id
    asset_id = uuid.uuid4()
    asset = await create(db_session, user, project, asset_id)
    created_id = asset.id
    db_session.expire_all()
    row = (await db_session.execute(select(PhotoAsset).where(PhotoAsset.id == asset_id))).scalar_one()
    assert row.status is PhotoAssetStatus.PENDING
    assert row.owner_id == user_id and row.project_id == project_id
    assert row.storage_name == "r2-primary"
    assert row.storage_key_original == f"photos/v1/{asset_id}/original.jpg"
    assert row.storage_key_display == f"photos/v1/{asset_id}/display.jpg"
    assert row.storage_key_thumbnail == f"photos/v1/{asset_id}/thumb.jpg"
    assert row.content_type is PhotoContentType.JPEG
    assert (row.byte_size, row.display_byte_size, row.thumbnail_byte_size) == (1_234_567, 450_000, 25_000)
    assert (row.width, row.height) == (3000, 4000)  # oriented dimensions
    assert row.sha256 == SHA
    assert row.original_filename == "IMG_0001.JPG"
    assert row.captured_at == datetime(2026, 9, 28, 10, 11, 12)
    assert row.captured_at.tzinfo is None  # camera-local, never converted
    assert row.uploaded_at is not None and row.created_at is not None and row.updated_at is not None
    assert row.archived_at is None
    assert created_id == asset_id


@pytest.mark.parametrize(
    "fmt, ctype, ext",
    [(PhotoFormat.JPEG, PhotoContentType.JPEG, "jpg"), (PhotoFormat.PNG, PhotoContentType.PNG, "png"),
     (PhotoFormat.WEBP, PhotoContentType.WEBP, "webp")],
)
async def test_content_type_and_key_follow_decoded_format(db_session, fmt, ctype, ext):
    user, project = await setup(db_session)
    asset = await create(db_session, user, project, processed=processed(format=fmt))
    assert asset.content_type is ctype
    assert asset.storage_key_original.endswith(f"/original.{ext}")


async def test_filename_never_influences_keys(db_session):
    user, project = await setup(db_session)
    asset = await create(db_session, user, project, original_filename="../../evil name.png")
    assert asset.original_filename == "evil name.png"
    assert "evil" not in asset.storage_key_original


def test_sanitize_original_filename():
    assert sanitize_original_filename(None) is None
    assert sanitize_original_filename("  ") is None
    assert sanitize_original_filename("C:\\Users\\x\\IMG 1.jpg") == "IMG 1.jpg"
    assert sanitize_original_filename("a\x00b\nc.jpg") == "abc.jpg"
    assert len(sanitize_original_filename("x" * 400 + ".jpg")) == 255


async def test_no_url_or_credential_columns():
    names = set(PhotoAsset.__table__.columns.keys())
    assert not {n for n in names if "url" in n or "secret" in n or "credential" in n}
    forbidden = {"room_id", "surface_id", "inspection_id", "finding_id", "occurrence_key", "caption",
                 "category", "include_in_report", "x", "y", "storage_backend"}
    assert not names & forbidden


# --------------------------------------------------------------------------
# Ownership and identity
# --------------------------------------------------------------------------


async def test_project_must_belong_to_owner(db_session):
    user, _ = await setup(db_session, 5002)
    _, foreign_project = await setup(db_session, 5003)
    with pytest.raises(ProjectNotFoundError):
        await create(db_session, user, foreign_project)
    assert (await db_session.execute(select(PhotoAsset))).first() is None


async def test_upload_id_is_unique_across_owners_without_leaking_owner(db_session):
    user_a, project_a = await setup(db_session, 5004)
    user_b, project_b = await setup(db_session, 5005)
    asset_id = uuid.uuid4()
    await create(db_session, user_a, project_a, asset_id)
    with pytest.raises(PhotoAssetAlreadyExistsError) as exc:
        await create(db_session, user_b, project_b, asset_id)
    assert str(user_a.id) not in str(exc.value)


async def test_upload_id_uniqueness_enforced_by_primary_key(db_session):
    user, project = await setup(db_session)
    asset_id = uuid.uuid4()
    db_session.add(raw_asset(user, project, id=asset_id))
    await db_session.commit()
    db_session.expunge_all()  # bypass the identity map: the database PK must refuse it
    db_session.add(raw_asset(user, project, id=asset_id, storage_key_original="x/o", storage_key_display="x/d",
                             storage_key_thumbnail="x/t"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_get_for_owner_is_owner_scoped(db_session):
    user, project = await setup(db_session, 5006)
    other, _ = await setup(db_session, 5007)
    asset = await create(db_session, user, project)
    assert (await PhotoAssetService(db_session).get_for_owner(asset.id, user.id)).id == asset.id
    with pytest.raises(PhotoAssetNotFoundError):
        await PhotoAssetService(db_session).get_for_owner(asset.id, other.id)


# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------


async def test_pending_to_ready(db_session):
    user, project = await setup(db_session)
    asset = await create(db_session, user, project)
    ready = await PhotoAssetService(db_session).transition(asset.id, user.id, PhotoAssetStatus.READY)
    assert ready.status is PhotoAssetStatus.READY
    assert ready.sha256 == SHA and ready.byte_size == 1_234_567  # metadata unchanged


async def test_pending_to_failed_and_retry_back_to_pending(db_session):
    user, project = await setup(db_session)
    asset = await create(db_session, user, project)
    svc = PhotoAssetService(db_session)
    assert (await svc.transition(asset.id, user.id, PhotoAssetStatus.FAILED)).status is PhotoAssetStatus.FAILED
    assert (await svc.transition(asset.id, user.id, PhotoAssetStatus.PENDING)).status is PhotoAssetStatus.PENDING
    assert (await svc.transition(asset.id, user.id, PhotoAssetStatus.READY)).status is PhotoAssetStatus.READY


@pytest.mark.parametrize(
    "path",
    [
        [PhotoAssetStatus.READY, PhotoAssetStatus.FAILED],
        [PhotoAssetStatus.READY, PhotoAssetStatus.PENDING],
        [PhotoAssetStatus.PENDING],
        [PhotoAssetStatus.FAILED, PhotoAssetStatus.READY],
        [PhotoAssetStatus.FAILED, PhotoAssetStatus.FAILED],
    ],
)
async def test_invalid_transitions_rejected(db_session, path):
    user, project = await setup(db_session)
    asset = await create(db_session, user, project)
    asset_id, owner_id = asset.id, user.id
    svc = PhotoAssetService(db_session)
    *allowed, forbidden = path
    for status in allowed:
        await svc.transition(asset_id, owner_id, status)
    before = (await svc.get_for_owner(asset_id, owner_id)).status
    with pytest.raises(PhotoAssetStateError):
        await svc.transition(asset_id, owner_id, forbidden)
    await db_session.rollback()
    assert (await svc.get_for_owner(asset_id, owner_id)).status is before


def test_ready_is_terminal():
    assert ALLOWED_TRANSITIONS[PhotoAssetStatus.READY] == frozenset()


async def test_other_owner_cannot_transition(db_session):
    user, project = await setup(db_session, 5008)
    other, _ = await setup(db_session, 5009)
    asset = await create(db_session, user, project)
    with pytest.raises(PhotoAssetNotFoundError):
        await PhotoAssetService(db_session).transition(asset.id, other.id, PhotoAssetStatus.READY)


# --------------------------------------------------------------------------
# Service validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"sha256": "AB" * 32},
        {"sha256": "ab" * 31},
        {"sha256": "zz" * 32},
        {"byte_size": 0},
        {"width": 0},
        {"height": -1},
        {"display": DerivativeInfo(path=Path("d"), width=1, height=1, byte_size=0)},
        {"thumbnail": DerivativeInfo(path=Path("t"), width=1, height=1, byte_size=0)},
        {"captured_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    ],
)
async def test_invalid_metadata_rejected_before_insert(db_session, overrides):
    user, project = await setup(db_session)
    with pytest.raises(PhotoAssetValidationError):
        await create(db_session, user, project, processed=processed(**overrides))
    assert (await db_session.execute(select(PhotoAsset))).first() is None


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
async def test_invalid_storage_name_rejected(db_session, name):
    user, project = await setup(db_session)
    with pytest.raises(PhotoAssetValidationError):
        await create(db_session, user, project, storage_name=name)


async def test_non_v4_asset_id_rejected(db_session):
    user, project = await setup(db_session)
    with pytest.raises(PhotoAssetValidationError):
        await create(db_session, user, project, asset_id=uuid.uuid1())


# --------------------------------------------------------------------------
# Database constraints (service bypassed)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"byte_size": 0},
        {"display_byte_size": 0},
        {"thumbnail_byte_size": -5},
        {"width": 0},
        {"height": 0},
        {"sha256": "ab" * 31},
        {"sha256": "AB" * 32},
        {"storage_name": "   "},
        {"storage_key_display": ""},
    ],
)
async def test_db_check_constraints(db_session, overrides):
    user, project = await setup(db_session)
    db_session.add(raw_asset(user, project, **overrides))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.parametrize("column", ["storage_key_original", "storage_key_display", "storage_key_thumbnail"])
async def test_storage_keys_unique(db_session, column):
    user, project = await setup(db_session)
    first = raw_asset(user, project)
    db_session.add(first)
    await db_session.commit()
    second = raw_asset(user, project)
    setattr(second, column, getattr(first, column))
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_sha256_not_unique(db_session):
    user, project = await setup(db_session)
    db_session.add_all([raw_asset(user, project), raw_asset(user, project)])
    await db_session.commit()
    assert len((await db_session.execute(select(PhotoAsset).where(PhotoAsset.sha256 == SHA))).all()) == 2


async def test_project_delete_restricted_by_asset(db_session):
    user, project = await setup(db_session)
    await create(db_session, user, project)
    with pytest.raises(IntegrityError):
        await db_session.execute(delete(Project).where(Project.id == project.id))
        await db_session.commit()


async def test_valid_pending_ready_failed_rows(db_session):
    user, project = await setup(db_session)
    for status in PhotoAssetStatus:
        db_session.add(raw_asset(user, project, status=status))
    await db_session.commit()
    statuses = {r.status for r in (await db_session.execute(select(PhotoAsset))).scalars()}
    assert statuses == set(PhotoAssetStatus)


# --------------------------------------------------------------------------
# Integrity listing
# --------------------------------------------------------------------------


async def test_list_for_integrity_all_owners_and_storage_filter(db_session):
    user_a, project_a = await setup(db_session, 5010)
    user_b, project_b = await setup(db_session, 5011)
    await create(db_session, user_a, project_a)
    await create(db_session, user_b, project_b, storage_name="backup-oci")
    svc = PhotoAssetService(db_session)
    assert len(await svc.list_for_integrity()) == 2
    only = await svc.list_for_integrity("backup-oci")
    assert [s.storage_name for s in only] == ["backup-oci"]
