"""Stage 14C.3 — upload orchestration: gate, validation, new upload, quota,
replay, resume, storage/DB failure handling, CAS races
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §11–§15, §19, C8–C11, C16).

Real 14B image pipeline + InMemoryMediaStorage (write-once) wrapped by a
fault-injecting, call-recording storage. "Parallel" requests are run
deterministically at a hooked point with a second session (the test engine
shares one SQLite connection, so asyncio.gather would not model isolation).
"""

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.domain.exceptions import (
    MediaObjectConflict,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
    OpeningNotFoundError,
    PhotoAttachmentValidationError,
    PhotoInvalidImageError,
    PhotoProcessingBusyError,
    PhotoStorageQuotaExceededError,
    PhotoTooLargeError,
    PhotoUnsupportedFormatError,
    PhotoUploadMalformedError,
    PhotoUploadResumeMismatchError,
    PhotoUploadsDisabledError,
    ProjectNotFoundError,
    RoomNotFoundError,
)
from app.domain.photos.image_processing import ImagePipelineConfig, ImageProcessor, process_image_file
from app.domain.photos.temp import PHOTO_TEMP_PREFIX
from app.domain.services import photo_upload_service as ups
from app.domain.services.media_integrity import FindingKind, run_integrity_check
from app.domain.services.media_storage import InMemoryMediaStorage
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import AttachmentTarget
from app.domain.services.photo_quota import PhotoStorageState
from app.domain.services.photo_upload_service import (
    PhotoUploadConfig,
    PhotoUploadOutcome,
    PhotoUploadRequest,
    PhotoUploadService,
)
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests.conftest import TestingSessionLocal
from tests.test_estimates import _make_opening, _make_project, _make_room, _make_surface, _make_user

C = PhotoAttachmentContext
P, R, F = PhotoAssetStatus.PENDING, PhotoAssetStatus.READY, PhotoAssetStatus.FAILED
VARIANTS = ("original", "display", "thumbnail")


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class RecordingStorage:
    """InMemoryMediaStorage + call log + fault injection + async hooks."""

    def __init__(self) -> None:
        self.inner = InMemoryMediaStorage()
        self.puts: list[str] = []
        self.heads: list[str] = []
        self.put_faults: dict[str, Exception] = {}  # key suffix -> error
        self.head_fault: Exception | None = None
        self.before_put = None  # one-shot async callable(key, source)
        self.before_head = None  # one-shot async callable(key)

    async def put_object(self, key, source, content_type):
        if self.before_put is not None:
            hook, self.before_put = self.before_put, None
            await hook(key, source)
        for suffix, error in self.put_faults.items():
            if key.endswith(suffix):
                raise error
        self.puts.append(key)
        await self.inner.put_object(key, source, content_type)

    async def head_object(self, key):
        if self.before_head is not None:
            hook, self.before_head = self.before_head, None
            await hook(key)
        if self.head_fault is not None:
            raise self.head_fault
        self.heads.append(key)
        return await self.inner.head_object(key)

    async def presign_get(self, key, ttl_seconds):
        return await self.inner.presign_get(key, ttl_seconds)

    async def download_to(self, key, path):
        await self.inner.download_to(key, path)

    def iter_keys(self, prefix):
        return self.inner.iter_keys(prefix)

    # test helpers
    def keys(self) -> set[str]:
        return set(self.inner._objects)

    def drop(self, key: str) -> None:
        del self.inner._objects[key]

    def overwrite(self, key: str, data: bytes) -> None:
        self.inner._objects[key].data = data


def suffix(variant: str) -> str:
    return {"original": "/original.jpg", "display": "/display.jpg", "thumbnail": "/thumb.jpg"}[variant]


def key_of(asset: PhotoAsset, variant: str) -> str:
    return {
        "original": asset.storage_key_original,
        "display": asset.storage_key_display,
        "thumbnail": asset.storage_key_thumbnail,
    }[variant]


def image_file(tmp_path: Path, name: str = "a.jpg", color=(200, 30, 30), fmt: str = "JPEG", size=(64, 48)) -> Path:
    buf = io.BytesIO()
    image = Image.new("RGB", size, color)
    image.putpixel((1, 1), (0, 0, 0))
    image.save(buf, format=fmt)
    path = tmp_path / name
    path.write_bytes(buf.getvalue())
    return path


def make_config(tmp_path: Path, **overrides) -> PhotoUploadConfig:
    values = dict(
        uploads_enabled=True,
        storage_backend="s3",
        storage_name="r2-primary",
        max_upload_bytes=25_000_000,
        warning_bytes=8_000_000_000,
        soft_cap_bytes=10_000_000_000,
        temp_dir=str(tmp_path / "photo-temp"),
    )
    values.update(overrides)
    return PhotoUploadConfig(**values)


def make_processor(**config) -> ImageProcessor:
    return ImageProcessor(ImagePipelineConfig(**config), wait_seconds=5)


@pytest.fixture
async def env(db_session, tmp_path):
    me = await _make_user(db_session, 6301)
    other = await _make_user(db_session, 6302)
    project = await _make_project(db_session, me.id)
    project2 = await _make_project(db_session, me.id, name="Drugi")
    foreign_project = await _make_project(db_session, other.id, name="Obcy")
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    opening = await _make_opening(db_session, surface.id)
    foreign_room = await _make_room(db_session, foreign_project.id)
    room2 = await _make_room(db_session, project2.id)
    e = SimpleNamespace(
        db=db_session, tmp=tmp_path, me=me.id, other=other.id, project=project.id, project2=project2.id,
        foreign_project=foreign_project.id, room=room.id, surface=surface.id, opening=opening.id,
        foreign_room=foreign_room.id, room2=room2.id,
        storage=RecordingStorage(), processor=make_processor(), config=make_config(tmp_path),
    )
    e.service = lambda db=None, **kw: PhotoUploadService(
        db or e.db, kw.get("storage", e.storage), kw.get("processor", e.processor), kw.get("config", e.config)
    )
    return e


def req(e, path: Path, *, upload_id: str | None = None, owner=None, project=None, target=None, **kw):
    return PhotoUploadRequest(
        owner_id=owner or e.me,
        project_id=project or e.project,
        upload_id=str(uuid.uuid4()) if upload_id is None else upload_id,
        target=target or AttachmentTarget(context=C.ROOM, room_id=e.room),
        original_path=path,
        **kw,
    )


async def counts(db) -> tuple[int, int]:
    assets = (await db.execute(select(func.count()).select_from(PhotoAsset))).scalar_one()
    atts = (await db.execute(select(func.count()).select_from(PhotoAttachment))).scalar_one()
    return assets, atts


async def status_of(db, asset_id) -> PhotoAssetStatus:
    stmt = select(PhotoAsset.status).where(PhotoAsset.id == asset_id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one()


async def integrity(e):
    snapshots = await PhotoAssetService(e.db).list_for_integrity()
    return await run_integrity_check(
        snapshots, e.storage.inner, storage_name="r2-primary", temp_dir=str(e.tmp / "integrity")
    )


def kinds(report) -> list[FindingKind]:
    return [f.kind for f in report.findings]


def temp_is_clean(e) -> bool:
    base = Path(e.config.temp_dir)
    return not base.exists() or not any(p.name.startswith(PHOTO_TEMP_PREFIX) for p in base.iterdir())


async def pending_with_all_objects(e, monkeypatch, path: Path, upload_id: str) -> PhotoAsset:
    """Simulate 'READY commit failed': all three objects written, row PENDING."""
    original_cas = PhotoAssetService.compare_and_set_status

    async def failing_ready(self, asset_id, owner_id, *, expected, target):
        if target is R:
            raise OperationalError("UPDATE photo_assets", {}, Exception("db down"))
        return await original_cas(self, asset_id, owner_id, expected=expected, target=target)

    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", failing_ready)
    with pytest.raises(OperationalError):
        await e.service().upload(req(e, path, upload_id=upload_id))
    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", original_cas)
    asset = await e.db.get(PhotoAsset, uuid.UUID(upload_id), populate_existing=True)
    assert asset.status is P
    return asset


# ---------------------------------------------------------------------------
# Gate (§19)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides", [{"uploads_enabled": False}, {"storage_backend": "disabled"}], ids=["flag-off", "storage-disabled"]
)
async def test_gate_blocks_new_upload_before_anything(env, monkeypatch, overrides):
    calls = []
    monkeypatch.setattr(ups, "hash_file_bounded", lambda *a: calls.append("hash"))
    service = env.service(config=make_config(env.tmp, **overrides))
    with pytest.raises(PhotoUploadsDisabledError) as exc:
        await service.upload(req(env, image_file(env.tmp)))
    assert exc.value.code == "PHOTO_UPLOADS_DISABLED"
    assert calls == [] and env.storage.puts == [] and env.storage.heads == []
    assert await counts(env.db) == (0, 0)


async def test_gate_blocks_replay_and_resume(env, monkeypatch):
    path = image_file(env.tmp)
    ready_id = str(uuid.uuid4())
    await env.service().upload(req(env, path, upload_id=ready_id))
    pending_id = str(uuid.uuid4())
    await pending_with_all_objects(env, monkeypatch, image_file(env.tmp, "b.jpg", (1, 2, 3)), pending_id)
    env.storage.puts.clear()
    env.storage.heads.clear()
    off = env.service(config=make_config(env.tmp, uploads_enabled=False))
    for upload_id, file in ((ready_id, path), (pending_id, env.tmp / "b.jpg")):
        with pytest.raises(PhotoUploadsDisabledError):
            await off.upload(req(env, file, upload_id=upload_id))
    assert env.storage.puts == [] and env.storage.heads == []
    assert await status_of(env.db, uuid.UUID(pending_id)) is P


def test_config_from_settings_maps_fields():
    settings = SimpleNamespace(
        PHOTO_UPLOADS_ENABLED=False, MEDIA_STORAGE_BACKEND="s3", MEDIA_STORAGE_NAME="r2-primary",
        PHOTO_MAX_UPLOAD_BYTES=25_000_000, PHOTO_STORAGE_WARNING_BYTES=8, PHOTO_STORAGE_SOFT_CAP_BYTES=10,
        PHOTO_TEMP_DIR="/tmp/x",
    )
    config = PhotoUploadConfig.from_settings(settings)
    assert config.uploads_available is False
    assert (config.storage_name, config.soft_cap_bytes, config.warning_bytes) == ("r2-primary", 10, 8)


# ---------------------------------------------------------------------------
# Step 7 validation (no row, no processing, no object)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-uuid",
        "",
        str(uuid.uuid1()),
        "12345678-1234-1234-1234-123456789abc",  # version 1 nibble
        str(uuid.uuid4()).upper(),
        "{" + str(uuid.uuid4()) + "}",
        str(uuid.uuid4()).replace("-", ""),
    ],
    ids=["garbage", "empty", "v1", "v1-shape", "uppercase", "braces", "no-dashes"],
)
async def test_upload_id_must_be_canonical_lowercase_v4(env, raw):
    with pytest.raises(PhotoUploadMalformedError) as exc:
        await env.service().upload(req(env, image_file(env.tmp), upload_id=raw))
    assert exc.value.code == "PHOTO_UPLOAD_MALFORMED"
    assert await counts(env.db) == (0, 0)


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"hello, this is text", PhotoUnsupportedFormatError),
        (b"GIF89a" + b"\x00" * 64, PhotoUnsupportedFormatError),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 40, PhotoUnsupportedFormatError),  # unidentifiable
        (b"", PhotoInvalidImageError),
    ],
    ids=["text-disguised", "gif", "corrupt-jpeg", "empty"],
)
async def test_rejected_images_create_nothing(env, data, error):
    path = env.tmp / "photo.jpg"
    path.write_bytes(data)
    with pytest.raises(error):
        await env.service().upload(req(env, path))
    assert await counts(env.db) == (0, 0)
    assert env.storage.keys() == set() and temp_is_clean(env)


async def test_truncated_jpeg_rejected(env):
    good = image_file(env.tmp).read_bytes()
    path = env.tmp / "cut.jpg"
    path.write_bytes(good[: len(good) // 2])
    with pytest.raises(PhotoInvalidImageError):
        await env.service().upload(req(env, path))
    assert await counts(env.db) == (0, 0) and env.storage.keys() == set()


async def test_oversized_bytes_rejected_at_hashing(env):
    service = env.service(config=make_config(env.tmp, max_upload_bytes=100))
    with pytest.raises(PhotoTooLargeError):
        await service.upload(req(env, image_file(env.tmp)))
    assert await counts(env.db) == (0, 0)


@pytest.mark.parametrize(
    ("target_fn", "error"),
    [
        (lambda e: AttachmentTarget(context=C.ROOM, room_id=e.foreign_room), RoomNotFoundError),
        (lambda e: AttachmentTarget(context=C.ROOM, room_id=e.room2), RoomNotFoundError),
        (lambda e: AttachmentTarget(context=C.OPENING, opening_id=uuid.uuid4()), OpeningNotFoundError),
        (lambda e: AttachmentTarget(context=C.WORK), PhotoAttachmentValidationError),
        (lambda e: AttachmentTarget(context=C.ROOM), PhotoAttachmentValidationError),
    ],
    ids=["foreign-room", "other-project-room", "missing-opening", "inspection", "room-missing-id"],
)
async def test_target_errors_before_processing(env, monkeypatch, target_fn, error):
    monkeypatch.setattr(env.processor, "run_in_slot", _never)
    with pytest.raises(error):
        await env.service().upload(req(env, image_file(env.tmp), target=target_fn(env)))
    assert await counts(env.db) == (0, 0)


async def test_invalid_metadata_rejected_before_processing(env, monkeypatch):
    monkeypatch.setattr(env.processor, "run_in_slot", _never)
    for kw in ({"caption": "x" * 1001}, {"category": "DEFECT"}, {"include_in_report": "yes"}):
        with pytest.raises(PhotoAttachmentValidationError):
            await env.service().upload(req(env, image_file(env.tmp), **kw))
    assert await counts(env.db) == (0, 0)


async def test_foreign_project_rejected(env):
    with pytest.raises(ProjectNotFoundError):
        await env.service().upload(req(env, image_file(env.tmp), project=env.foreign_project))


async def _never(*args, **kwargs):
    raise AssertionError("must not be called")


# ---------------------------------------------------------------------------
# Processing slot
# ---------------------------------------------------------------------------


async def test_processing_busy_creates_nothing(env):
    processor = ImageProcessor(ImagePipelineConfig(), wait_seconds=0.05)
    async with processor.slot():
        with pytest.raises(PhotoProcessingBusyError) as exc:
            await env.service(processor=processor).upload(req(env, image_file(env.tmp)))
    assert exc.value.code == "PHOTO_PROCESSING_BUSY"
    assert await counts(env.db) == (0, 0) and env.storage.keys() == set()


async def test_slot_is_held_through_quota_and_pending_insert(env, monkeypatch):
    seen = []
    original_add = PhotoAssetService.add_pending

    async def spy(self, **kw):
        seen.append(env.processor._slot.locked())
        return await original_add(self, **kw)

    monkeypatch.setattr(PhotoAssetService, "add_pending", spy)
    original_put = env.storage.put_object

    async def spy_put(key, source, content_type):
        seen.append(env.processor._slot.locked())
        await original_put(key, source, content_type)

    monkeypatch.setattr(env.storage, "put_object", spy_put)
    await env.service().upload(req(env, image_file(env.tmp)))
    assert seen == [True, False, False, False]  # insert inside the slot, PUTs outside


# ---------------------------------------------------------------------------
# New upload
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("fmt", "ext", "ctype"), [("JPEG", "jpg", "image/jpeg"), ("PNG", "png", "image/png"),
                                                   ("WEBP", "webp", "image/webp")])
async def test_new_upload_success(env, fmt, ext, ctype):
    path = image_file(env.tmp, f"p.{ext}", fmt=fmt)
    upload_id = str(uuid.uuid4())
    result = await env.service().upload(
        req(env, path, upload_id=upload_id, category=PhotoCategory.BEFORE, caption="  przed  ",
            include_in_report=True, original_filename="../IMG_1.JPG")
    )
    assert result.outcome is PhotoUploadOutcome.CREATED and result.outcome.created
    asset = result.asset
    assert str(asset.id) == upload_id and asset.status is R
    assert asset.storage_key_original == f"photos/v1/{upload_id}/original.{ext}"
    assert asset.content_type.value == ctype and asset.original_filename == "IMG_1.JPG"
    assert env.storage.puts == [asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail]
    assert env.storage.inner.get_bytes(asset.storage_key_original) == path.read_bytes()
    assert env.storage.inner.get_content_type(asset.storage_key_original) == ctype
    assert env.storage.inner.get_content_type(asset.storage_key_display) == "image/jpeg"
    att = result.attachment
    assert (att.context, att.room_id, att.category, att.caption, att.include_in_report, att.position) == (
        C.ROOM, env.room, PhotoCategory.BEFORE, "przed", True, 0,
    )
    assert result.storage_state is PhotoStorageState.OK
    assert await counts(env.db) == (1, 1)
    report = await integrity(env)
    assert report.errors == [] and FindingKind.ORPHAN_CANDIDATE not in kinds(report)
    assert temp_is_clean(env)


@pytest.mark.parametrize("context", [C.PROJECT, C.SURFACE, C.OPENING])
async def test_new_upload_other_contexts(env, context):
    target = {
        C.PROJECT: AttachmentTarget(context=C.PROJECT),
        C.SURFACE: AttachmentTarget(context=C.SURFACE, surface_id=env.surface),
        C.OPENING: AttachmentTarget(context=C.OPENING, opening_id=env.opening),
    }[context]
    result = await env.service().upload(req(env, image_file(env.tmp), target=target))
    assert result.attachment.context is context and result.attachment.category is PhotoCategory.GENERAL


async def test_first_attachment_failure_rolls_back_the_asset(env, monkeypatch):
    from app.domain.services.photo_attachment_service import PhotoAttachmentService

    async def boom(self, **kw):
        raise RuntimeError("attachment insert failed")

    monkeypatch.setattr(PhotoAttachmentService, "add_initial_attachment", boom)
    with pytest.raises(RuntimeError):
        await env.service().upload(req(env, image_file(env.tmp)))
    assert await counts(env.db) == (0, 0) and env.storage.keys() == set() and temp_is_clean(env)


async def test_step10_commit_failure_leaves_no_row_and_no_object(env, monkeypatch):
    from app.domain.services.photo_attachment_service import PhotoAttachmentService

    original_commit = env.db.commit
    original_add = PhotoAttachmentService.add_initial_attachment
    state = {"armed": False}

    async def arming_add(self, **kw):
        attachment = await original_add(self, **kw)
        state["armed"] = True  # the next commit is the step-10 commit
        return attachment

    async def failing_commit():
        if state["armed"]:
            state["armed"] = False
            raise OperationalError("COMMIT", {}, Exception("db down"))
        await original_commit()

    monkeypatch.setattr(PhotoAttachmentService, "add_initial_attachment", arming_add)
    monkeypatch.setattr(env.db, "commit", failing_commit)
    with pytest.raises(OperationalError):
        await env.service().upload(req(env, image_file(env.tmp)))
    assert await counts(env.db) == (0, 0) and env.storage.keys() == set()


# ---------------------------------------------------------------------------
# Quota (§15) on the new-upload path
# ---------------------------------------------------------------------------


def new_sizes(tmp_path: Path, path: Path) -> int:
    ws = tmp_path / "measure"
    ws.mkdir(exist_ok=True)
    p = process_image_file(path, ws, ImagePipelineConfig())
    return p.byte_size + p.display.byte_size + p.thumbnail.byte_size


async def seed_usage(e, status=R, archived=False, owner=None) -> int:
    from tests.test_stage14b4_photo_asset import raw_asset

    owner_id = owner or e.me
    project = e.project if owner_id == e.me else e.foreign_project
    asset = raw_asset(
        SimpleNamespace(id=owner_id), SimpleNamespace(id=project), status=status,
        byte_size=1000, display_byte_size=200, thumbnail_byte_size=30,
        archived_at=datetime.now(UTC) if archived else None,
    )
    e.db.add(asset)
    await e.db.commit()
    return 1230


@pytest.mark.parametrize(
    ("status", "archived"),
    [(R, False), (R, True), (P, False), (F, False)],
    ids=["ready", "archived", "pending", "failed"],
)
async def test_quota_counts_reserved_statuses_and_archived(env, status, archived):
    used = await seed_usage(env, status=status, archived=archived)
    await seed_usage(env, owner=env.other)  # another owner's usage never counts
    path = image_file(env.tmp)
    cap = used + new_sizes(env.tmp, path)
    ok = await env.service(config=make_config(env.tmp, soft_cap_bytes=cap, warning_bytes=1)).upload(req(env, path))
    assert ok.outcome is PhotoUploadOutcome.CREATED  # usage + new == cap is allowed
    assert ok.storage_state is PhotoStorageState.FULL  # at the cap


async def test_quota_soft_cap_rejects_new_upload(env):
    used = await seed_usage(env, archived=True)
    path = image_file(env.tmp)
    cap = used + new_sizes(env.tmp, path) - 1
    service = env.service(config=make_config(env.tmp, soft_cap_bytes=cap, warning_bytes=1))
    with pytest.raises(PhotoStorageQuotaExceededError) as exc:
        await service.upload(req(env, path))
    assert exc.value.code == "PHOTO_STORAGE_QUOTA_EXCEEDED"
    assert await counts(env.db) == (1, 0) and env.storage.keys() == set() and temp_is_clean(env)


async def test_quota_warning_state_reported_without_rejection(env):
    await seed_usage(env)
    result = await env.service(config=make_config(env.tmp, warning_bytes=1000)).upload(
        req(env, image_file(env.tmp))
    )
    assert result.outcome is PhotoUploadOutcome.CREATED and result.storage_state is PhotoStorageState.WARNING


# ---------------------------------------------------------------------------
# READY replay (C16)
# ---------------------------------------------------------------------------


async def test_replay_returns_existing_without_side_effects(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    first = await env.service().upload(req(env, path, upload_id=upload_id, caption="pierwszy"))
    env.storage.puts.clear()
    monkeypatch.setattr(env.processor, "run_in_slot", _never)
    replay = await env.service(config=make_config(env.tmp, soft_cap_bytes=1, warning_bytes=1)).upload(
        req(env, path, upload_id=upload_id, caption="inny", category=PhotoCategory.DAMAGE,
            target=AttachmentTarget(context=C.SURFACE, surface_id=env.surface))
    )
    assert replay.outcome is PhotoUploadOutcome.REPLAYED and not replay.outcome.created
    assert replay.asset.id == first.asset.id
    assert replay.attachment.id == first.attachment.id
    assert (replay.attachment.caption, replay.attachment.context) == ("pierwszy", C.ROOM)  # metadata ignored
    assert env.storage.puts == [] and env.storage.heads == []
    assert await counts(env.db) == (1, 1)


async def test_replay_of_archived_asset_and_archived_first_attachment(env):
    from app.domain.services.photo_attachment_service import PhotoAttachmentService

    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    first = await env.service().upload(req(env, path, upload_id=upload_id))
    await PhotoAttachmentService(env.db).archive_attachment(env.me, env.project, first.attachment.id)
    later = await PhotoAttachmentService(env.db).create_attachment(
        owner_id=env.me, project_id=env.project, asset_id=first.asset.id,
        target=AttachmentTarget(context=C.PROJECT),
    )
    asset = await env.db.get(PhotoAsset, first.asset.id)
    asset.archived_at = datetime.now(UTC)
    await env.db.commit()
    replay = await env.service().upload(req(env, path, upload_id=upload_id))
    assert replay.outcome is PhotoUploadOutcome.REPLAYED
    assert replay.asset.archived_at is not None
    assert replay.attachment.id == first.attachment.id != later.id  # first attachment, archived or not


# ---------------------------------------------------------------------------
# Resume (steps 12-16)
# ---------------------------------------------------------------------------


async def test_resume_pending_all_objects_present(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    await pending_with_all_objects(env, monkeypatch, path, upload_id)
    env.storage.puts.clear()
    monkeypatch.setattr(env.processor, "run_in_slot", _never)
    result = await env.service(config=make_config(env.tmp, soft_cap_bytes=1, warning_bytes=1)).upload(
        req(env, path, upload_id=upload_id, caption="ignored")
    )
    assert result.outcome is PhotoUploadOutcome.RESUMED and result.asset.status is R
    assert env.storage.puts == [] and len(env.storage.heads) == 3
    assert result.attachment is not None and result.attachment.caption is None
    assert await counts(env.db) == (1, 1)


@pytest.mark.parametrize("variant", VARIANTS)
async def test_resume_pending_with_one_object_missing(env, monkeypatch, variant):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    asset = await pending_with_all_objects(env, monkeypatch, path, upload_id)
    key = key_of(asset, variant)
    before = env.storage.inner.get_bytes(key)
    env.storage.drop(key)
    env.storage.puts.clear()
    processed = []
    original_run = env.processor.run_in_slot

    async def spy(source, workspace):
        processed.append(source)
        return await original_run(source, workspace)

    monkeypatch.setattr(env.processor, "run_in_slot", spy)
    result = await env.service().upload(req(env, path, upload_id=upload_id))
    assert result.outcome is PhotoUploadOutcome.RESUMED
    assert env.storage.puts == [key]
    assert env.storage.inner.get_bytes(key) == before  # deterministic regeneration / same original
    assert len(processed) == (0 if variant == "original" else 1)
    report = await integrity(env)
    assert report.errors == [] and report.warnings == []
    assert await counts(env.db) == (1, 1) and temp_is_clean(env)


async def test_resume_with_all_objects_missing(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    asset = await pending_with_all_objects(env, monkeypatch, path, upload_id)
    for variant in VARIANTS:
        env.storage.drop(key_of(asset, variant))
    env.storage.puts.clear()
    result = await env.service().upload(req(env, path, upload_id=upload_id))
    assert result.outcome is PhotoUploadOutcome.RESUMED
    assert env.storage.puts == [key_of(asset, v) for v in VARIANTS]


@pytest.mark.parametrize("variant", VARIANTS)
async def test_resume_wrong_size_object_is_conflict_and_failed(env, monkeypatch, variant):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    asset = await pending_with_all_objects(env, monkeypatch, path, upload_id)
    key = key_of(asset, variant)
    env.storage.overwrite(key, b"x" * 7)
    env.storage.puts.clear()
    for _ in range(2):  # stays 409 until operator action
        with pytest.raises(MediaObjectConflict):
            await env.service().upload(req(env, path, upload_id=upload_id))
        assert await status_of(env.db, asset.id) is F
    assert env.storage.puts == [] and env.storage.inner.get_bytes(key) == b"x" * 7  # untouched


async def test_resume_retry_sha_mismatch_is_uniform_conflict(env, monkeypatch):
    from app.domain.exceptions import PhotoUploadIdConflictError

    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    await pending_with_all_objects(env, monkeypatch, path, upload_id)
    env.storage.heads.clear()
    with pytest.raises(PhotoUploadIdConflictError):
        await env.service().upload(req(env, image_file(env.tmp, "other.jpg", (9, 9, 9)), upload_id=upload_id))
    assert env.storage.heads == [] and await status_of(env.db, uuid.UUID(upload_id)) is P


async def test_failed_asset_resumes_and_finalizes(env):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    env.storage.put_faults[suffix("thumbnail")] = MediaStorageUnavailable("timeout")
    with pytest.raises(MediaStorageUnavailable):
        await env.service().upload(req(env, path, upload_id=upload_id))
    assert await status_of(env.db, uuid.UUID(upload_id)) is F
    env.storage.put_faults.clear()
    env.storage.puts.clear()
    result = await env.service(config=make_config(env.tmp, soft_cap_bytes=1, warning_bytes=1)).upload(
        req(env, path, upload_id=upload_id)
    )
    assert result.outcome is PhotoUploadOutcome.RESUMED and result.asset.status is R
    assert env.storage.puts == [result.asset.storage_key_thumbnail]
    assert await counts(env.db) == (1, 1)


async def test_resume_mismatch_marks_failed_and_writes_nothing(env, monkeypatch):
    path = image_file(env.tmp, size=(640, 480))
    upload_id = str(uuid.uuid4())
    asset = await pending_with_all_objects(env, monkeypatch, path, upload_id)
    env.storage.drop(asset.storage_key_display)
    env.storage.puts.clear()
    different = make_processor(display_max_edge=100)  # regenerates a different display size
    for _ in range(2):
        with pytest.raises(PhotoUploadResumeMismatchError) as exc:
            await env.service(processor=different).upload(req(env, path, upload_id=upload_id))
        assert exc.value.code == "PHOTO_UPLOAD_RESUME_MISMATCH"
        assert await status_of(env.db, asset.id) is F
    assert env.storage.puts == []


async def test_resume_pipeline_rejection_is_mismatch(env, monkeypatch):
    path = image_file(env.tmp, size=(640, 480))
    upload_id = str(uuid.uuid4())
    asset = await pending_with_all_objects(env, monkeypatch, path, upload_id)
    env.storage.drop(asset.storage_key_thumbnail)
    stricter = make_processor(max_decoded_pixels=1000)
    with pytest.raises(PhotoUploadResumeMismatchError):
        await env.service(processor=stricter).upload(req(env, path, upload_id=upload_id))
    assert await status_of(env.db, asset.id) is F


async def test_resume_head_failure_marks_failed(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    await pending_with_all_objects(env, monkeypatch, path, upload_id)
    env.storage.head_fault = MediaStorageUnavailable("timeout")
    with pytest.raises(MediaStorageUnavailable):
        await env.service().upload(req(env, path, upload_id=upload_id))
    assert await status_of(env.db, uuid.UUID(upload_id)) is F


# ---------------------------------------------------------------------------
# Storage failures on the new-upload path; write-once
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize(
    "error", [MediaStorageUnavailable("timeout"), MediaStorageMisconfigured("403"), MediaObjectConflict("x")],
    ids=["unavailable", "misconfigured", "object-conflict"],
)
async def test_put_failure_marks_failed_and_keeps_earlier_objects(env, variant, error):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    env.storage.put_faults[suffix(variant)] = error
    with pytest.raises(type(error)):
        await env.service().upload(req(env, path, upload_id=upload_id))
    asset_id = uuid.UUID(upload_id)
    assert await status_of(env.db, asset_id) is F
    written = VARIANTS[: VARIANTS.index(variant)]
    assert len(env.storage.keys()) == len(written)
    assert await counts(env.db) == (1, 1)  # the first attachment was committed with the asset
    report = await integrity(env)
    assert kinds(report) == [FindingKind.FAILED_RELATED]
    assert temp_is_clean(env)


async def test_existing_foreign_object_at_key_is_never_overwritten(env):
    """Write-once: an object already at the key with different bytes (e.g. a
    manual external write) -> MediaObjectConflict, FAILED, object untouched."""
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    key = f"photos/v1/{upload_id}/original.jpg"
    stray = env.tmp / "stray.bin"
    stray.write_bytes(b"something else")
    await env.storage.inner.put_object(key, stray, "image/jpeg")
    with pytest.raises(MediaObjectConflict):
        await env.service().upload(req(env, path, upload_id=upload_id))
    assert env.storage.inner.get_bytes(key) == b"something else"
    assert await status_of(env.db, uuid.UUID(upload_id)) is F


async def test_failed_commit_failure_leaves_pending(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    original_cas = PhotoAssetService.compare_and_set_status

    async def failing_failed(self, asset_id, owner_id, *, expected, target):
        if target is F:
            raise OperationalError("UPDATE photo_assets", {}, Exception("db down"))
        return await original_cas(self, asset_id, owner_id, expected=expected, target=target)

    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", failing_failed)
    env.storage.put_faults[suffix("display")] = MediaStorageUnavailable("timeout")
    with pytest.raises(MediaStorageUnavailable):
        await env.service().upload(req(env, path, upload_id=upload_id))
    assert await status_of(env.db, uuid.UUID(upload_id)) is P
    assert kinds(await integrity(env)) == [FindingKind.PENDING_INCOMPLETE]


async def test_ready_commit_failure_keeps_objects_and_resume_finalizes(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    asset = await pending_with_all_objects(env, monkeypatch, path, upload_id)
    assert env.storage.keys() == {key_of(asset, v) for v in VARIANTS}  # nothing deleted
    report = await integrity(env)
    assert kinds(report) == [FindingKind.PENDING_INCOMPLETE]  # detectable, never ORPHAN_CANDIDATE
    env.storage.puts.clear()
    result = await env.service().upload(req(env, path, upload_id=upload_id))
    assert result.outcome is PhotoUploadOutcome.RESUMED and env.storage.puts == []
    assert (await integrity(env)).findings == []


# ---------------------------------------------------------------------------
# Races (deterministic interleaving with a second session)
# ---------------------------------------------------------------------------


async def run_parallel(e, path, upload_id, *, processor=None):
    async with TestingSessionLocal() as other_db:
        return await e.service(other_db, processor=processor or e.processor).upload(
            req(e, path, upload_id=upload_id)
        )


async def test_parallel_finalize_wins_and_loser_reports_concurrent(env):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    parallel = {}

    async def hook(key, source):
        if key.endswith("/display.jpg"):
            parallel["result"] = await run_parallel(env, path, upload_id)
        else:
            env.storage.before_put = hook

    env.storage.before_put = hook
    result = await env.service().upload(req(env, path, upload_id=upload_id))
    assert parallel["result"].outcome is PhotoUploadOutcome.RESUMED
    assert result.outcome is PhotoUploadOutcome.CONCURRENTLY_FINALIZED and result.asset.status is R
    assert await counts(env.db) == (1, 1)
    assert (await integrity(env)).findings == []


async def test_ready_never_regresses_when_loser_hits_storage_error(env):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())

    async def hook(key, source):
        await run_parallel(env, path, upload_id)  # finalizes READY first
        env.storage.put_faults[suffix("original")] = MediaStorageUnavailable("timeout")

    env.storage.before_put = hook
    result = await env.service().upload(req(env, path, upload_id=upload_id))
    assert result.outcome is PhotoUploadOutcome.CONCURRENTLY_FINALIZED
    assert await status_of(env.db, uuid.UUID(upload_id)) is R


async def test_primary_key_race_on_insert_returns_replay(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    original_add = PhotoAssetService.add_pending
    state = {"raced": False}

    async def racing_add(self, **kw):
        if not state["raced"]:
            state["raced"] = True
            await run_parallel(env, path, upload_id, processor=make_processor())  # other process, own slot
            original_get = self.db.get

            async def blind_get(*a, **k):  # bypass the pre-check: the PK must catch it
                return None

            self.db.get = blind_get
            try:
                return await original_add(self, **kw)
            finally:
                self.db.get = original_get
        return await original_add(self, **kw)

    monkeypatch.setattr(PhotoAssetService, "add_pending", racing_add)
    result = await env.service().upload(req(env, path, upload_id=upload_id))
    assert result.outcome is PhotoUploadOutcome.REPLAYED
    assert await counts(env.db) == (1, 1)


async def test_failed_to_pending_cas_lost_race_reidentifies(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    env.storage.put_faults[suffix("thumbnail")] = MediaStorageUnavailable("timeout")
    with pytest.raises(MediaStorageUnavailable):
        await env.service().upload(req(env, path, upload_id=upload_id))
    env.storage.put_faults.clear()
    original_cas = PhotoAssetService.compare_and_set_status
    state = {"raced": False}

    async def racing_cas(self, asset_id, owner_id, *, expected, target):
        if expected is F and not state["raced"]:
            state["raced"] = True
            await run_parallel(env, path, upload_id)  # the other request resumes to READY first
        return await original_cas(self, asset_id, owner_id, expected=expected, target=target)

    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", racing_cas)
    result = await env.service().upload(req(env, path, upload_id=upload_id))
    assert result.outcome is PhotoUploadOutcome.REPLAYED
    assert await counts(env.db) == (1, 1)
