"""Stage 14C.6B — PostgreSQL 16 concurrency verification (OPT-IN).

Runs only with TEST_PG_URL pointing at a disposable loopback scratch
database whose name contains `pe_scratch_test` (see pg_scratch_guard.py);
otherwise the whole module is skipped. The scratch schema is created with
`alembic upgrade head`. Every case uses real, separate asyncpg connections
(one AsyncSession each) driven concurrently with asyncio.gather, so the
database -- not SQLite or a shared test session -- arbitrates the races.
Each test creates its own owner / project data and deletes it afterwards.
"""

import asyncio
import io
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.domain.exceptions import (
    PhotoAssetTransitionConflictError,
    PhotoAttachmentDuplicateError,
    PhotoStorageQuotaExceededError,
    PhotoUploadIdConflictError,
)
from app.domain.photos.image_processing import ImagePipelineConfig, ImageProcessor, process_image_file
from app.domain.services import photo_upload_service as ups
from app.domain.services.media_storage import InMemoryMediaStorage
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import AttachmentTarget, PhotoAttachmentService
from app.domain.services.photo_query_service import PhotoListFilters, PhotoQueryService
from app.domain.services.photo_upload_service import (
    PhotoUploadConfig,
    PhotoUploadOutcome,
    PhotoUploadRequest,
    PhotoUploadService,
)
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.project import Project
from app.models.room import Room
from app.models.user import User
from tests.pg_scratch_guard import scratch_url

URL = scratch_url()
pytestmark = pytest.mark.skipif(URL is None, reason="opt-in: set TEST_PG_URL to a pe_scratch_test database")

BACKEND = Path(__file__).resolve().parents[1]
C = PhotoAttachmentContext
P, R, F = PhotoAssetStatus.PENDING, PhotoAssetStatus.READY, PhotoAssetStatus.FAILED
ROUNDS = int(os.environ.get("PG_RACE_ROUNDS", "10"))


@pytest.fixture(scope="module", autouse=True)
def migrated_schema():
    env = dict(os.environ, DATABASE_URL=URL.render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
                   capture_output=True)


@pytest.fixture
async def pg(tmp_path):
    engine = create_async_engine(URL, poolclass=NullPool, hide_parameters=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner_ids: list[uuid.UUID] = []
    harness = SimpleNamespace(engine=engine, sessions=sessions, owners=owner_ids, tmp=tmp_path)
    yield harness
    async with sessions() as s:  # cleanup: FK-safe order, only this test's owners
        projects = select(Project.id).where(Project.owner_id.in_(owner_ids))
        await s.execute(delete(PhotoAttachment).where(PhotoAttachment.project_id.in_(projects)))
        await s.execute(delete(PhotoAsset).where(PhotoAsset.owner_id.in_(owner_ids)))
        await s.execute(delete(Room).where(Room.project_id.in_(projects)))
        await s.execute(delete(Project).where(Project.owner_id.in_(owner_ids)))
        await s.execute(delete(User).where(User.id.in_(owner_ids)))
        await s.commit()
    await engine.dispose()


async def world(pg) -> SimpleNamespace:
    async with pg.sessions() as s:
        user = User(telegram_user_id=int(uuid.uuid4().int % 10**12))
        s.add(user)
        await s.flush()
        project = Project(owner_id=user.id, name="PG scratch", address="ul. Testowa 1", city="Warszawa",
                          postal_code="00-001")
        s.add(project)
        await s.flush()
        room = Room(project_id=project.id, name="Salon")
        room2 = Room(project_id=project.id, name="Kuchnia")
        s.add_all([room, room2])
        await s.commit()
        pg.owners.append(user.id)
        return SimpleNamespace(owner=user.id, project=project.id, room=room.id, room2=room2.id)


def jpeg(path: Path, color=(200, 30, 30), size=(64, 48)) -> Path:
    buf = io.BytesIO()
    image = Image.new("RGB", size, color)
    image.putpixel((1, 1), (0, 0, 0))
    image.save(buf, format="JPEG")
    path.write_bytes(buf.getvalue())
    return path


def config(pg, **kw) -> PhotoUploadConfig:
    values = dict(uploads_enabled=True, storage_backend="s3", storage_name="r2-primary",
                  max_upload_bytes=25_000_000, warning_bytes=8_000_000_000, soft_cap_bytes=10_000_000_000,
                  temp_dir=str(pg.tmp / "photo-temp"))
    values.update(kw)
    return PhotoUploadConfig(**values)


def request(w, path: Path, upload_id: str, room=None) -> PhotoUploadRequest:
    return PhotoUploadRequest(owner_id=w.owner, project_id=w.project, upload_id=upload_id, original_path=path,
                              target=AttachmentTarget(context=C.ROOM, room_id=room or w.room))


async def upload(pg, w, path, upload_id, *, storage, processor, cfg=None, room=None):
    async with pg.sessions() as s:
        return await PhotoUploadService(s, storage, processor, cfg or config(pg)).upload(
            request(w, path, upload_id, room=room))


def processor() -> ImageProcessor:
    return ImageProcessor(ImagePipelineConfig(), wait_seconds=30)


async def counts(pg, asset_id) -> tuple[int, int, PhotoAssetStatus | None]:
    async with pg.sessions() as s:
        n_assets = (await s.execute(select(func.count()).select_from(PhotoAsset)
                                    .where(PhotoAsset.id == asset_id))).scalar_one()
        n_atts = (await s.execute(select(func.count()).select_from(PhotoAttachment)
                                  .where(PhotoAttachment.asset_id == asset_id,
                                         PhotoAttachment.archived_at.is_(None)))).scalar_one()
        status = (await s.execute(select(PhotoAsset.status).where(PhotoAsset.id == asset_id))).scalar_one_or_none()
    return n_assets, n_atts, status


async def ready_asset(pg, w, color=(10, 20, 30)) -> tuple[uuid.UUID, uuid.UUID]:
    result = await upload(pg, w, jpeg(pg.tmp / f"{uuid.uuid4()}.jpg", color), str(uuid.uuid4()),
                          storage=InMemoryMediaStorage(), processor=processor())
    return result.asset.id, result.attachment.id


def settled(results) -> tuple[list, list]:
    ok = [r for r in results if not isinstance(r, BaseException)]
    errors = [r for r in results if isinstance(r, BaseException)]
    return ok, errors


# ---------------------------------------------------------------------------
# A–C: same upload_id races, CAS
# ---------------------------------------------------------------------------


async def test_a_same_upload_id_same_content_two_independent_slots(pg):
    w = await world(pg)
    for i in range(ROUNDS):
        path = jpeg(pg.tmp / f"a{i}.jpg")
        upload_id = str(uuid.uuid4())
        storage = InMemoryMediaStorage()
        results = await asyncio.gather(
            upload(pg, w, path, upload_id, storage=storage, processor=processor()),
            upload(pg, w, path, upload_id, storage=storage, processor=processor()),
            return_exceptions=True,
        )
        ok, errors = settled(results)
        assert errors == [], errors
        assert {r.outcome for r in ok} <= {PhotoUploadOutcome.CREATED, PhotoUploadOutcome.RESUMED,
                                          PhotoUploadOutcome.REPLAYED, PhotoUploadOutcome.CONCURRENTLY_FINALIZED}
        assert sum(r.outcome.created for r in ok) == 1  # exactly one request reports the creation
        assert await counts(pg, uuid.UUID(upload_id)) == (1, 1, R)
        assert len([k async for k in storage.iter_keys("photos/v1/")]) == 3


async def test_b_same_upload_id_conflicting_content(pg):
    w = await world(pg)
    for i in range(ROUNDS):
        first, second = jpeg(pg.tmp / f"b{i}x.jpg", (1, 2, 3)), jpeg(pg.tmp / f"b{i}y.jpg", (200, 100, 50))
        upload_id = str(uuid.uuid4())
        storage = InMemoryMediaStorage()
        results = await asyncio.gather(
            upload(pg, w, first, upload_id, storage=storage, processor=processor()),
            upload(pg, w, second, upload_id, storage=storage, processor=processor()),
            return_exceptions=True,
        )
        ok, errors = settled(results)
        assert len(ok) == 1 and len(errors) == 1 and isinstance(errors[0], PhotoUploadIdConflictError)
        assert await counts(pg, uuid.UUID(upload_id)) == (1, 1, R)
        winner = first if results[0] is ok[0] else second
        stored = storage.get_bytes(ok[0].asset.storage_key_original)
        assert stored == winner.read_bytes()  # never overwritten by the loser


async def test_c_cas_ready_race_never_regresses(pg):
    w = await world(pg)
    for _ in range(ROUNDS):
        async with pg.sessions() as s:
            asset_id, _ = await ready_asset(pg, w)
            await s.execute(PhotoAsset.__table__.update().where(PhotoAsset.id == asset_id).values(status=P))
            await s.commit()

        async def cas(target, asset_id=asset_id):
            async with pg.sessions() as s:
                return await PhotoAssetService(s).compare_and_set_status(asset_id, w.owner, expected=P, target=target)

        results = await asyncio.gather(cas(R), cas(R), cas(F), return_exceptions=True)
        ok, errors = settled(results)
        assert len(ok) == 1 and len(errors) == 2
        assert all(isinstance(e, PhotoAssetTransitionConflictError) for e in errors)
        final = ok[0].status
        assert all(e.current_status is final for e in errors)  # losers observe the committed winner
        assert (await counts(pg, asset_id))[2] is final


# ---------------------------------------------------------------------------
# D–K: attachment / asset races
# ---------------------------------------------------------------------------


async def archived_attachment(pg, w) -> tuple[uuid.UUID, uuid.UUID]:
    asset_id, att_id = await ready_asset(pg, w, color=(uuid.uuid4().int % 255, 1, 1))
    async with pg.sessions() as s:
        await PhotoAttachmentService(s).archive_attachment(w.owner, w.project, att_id)
    return asset_id, att_id


async def test_d_restore_vs_create_equivalent_unique_index_decides(pg):
    w = await world(pg)
    for _ in range(ROUNDS):
        asset_id, att_id = await archived_attachment(pg, w)

        async def restore(att_id=att_id):
            async with pg.sessions() as s:
                return await PhotoAttachmentService(s).restore_attachment(w.owner, w.project, att_id)

        async def create(asset_id=asset_id):
            async with pg.sessions() as s:
                return await PhotoAttachmentService(s).create_attachment(
                    owner_id=w.owner, project_id=w.project, asset_id=asset_id,
                    target=AttachmentTarget(context=C.ROOM, room_id=w.room))

        results = await asyncio.gather(restore(), create(), return_exceptions=True)
        ok, errors = settled(results)
        assert len(ok) == 1 and len(errors) == 1 and isinstance(errors[0], PhotoAttachmentDuplicateError)
        assert (await counts(pg, asset_id))[1] == 1  # exactly one active equivalent attachment


async def test_e_restore_races(pg):
    w = await world(pg)
    for _ in range(ROUNDS):
        asset_id, att_id = await archived_attachment(pg, w)

        async def restore(target):
            async with pg.sessions() as s:
                return await PhotoAttachmentService(s).restore_attachment(w.owner, w.project, target)

        ok, errors = settled(await asyncio.gather(restore(att_id), restore(att_id), return_exceptions=True))
        assert errors == [] and len(ok) == 2  # same row restored twice: idempotent
        assert (await counts(pg, asset_id))[1] == 1
        # two DIFFERENT archived equivalent rows restored at once: exactly one wins
        async with pg.sessions() as s:
            await PhotoAttachmentService(s).archive_attachment(w.owner, w.project, att_id)
            twin = PhotoAttachment(asset_id=asset_id, project_id=w.project, context=C.ROOM, room_id=w.room,
                                   category=PhotoCategory.GENERAL, archived_at=func.now())
            s.add(twin)
            await s.commit()
            twin_id = twin.id
        ok, errors = settled(await asyncio.gather(restore(att_id), restore(twin_id), return_exceptions=True))
        assert len(ok) == 1 and len(errors) == 1 and isinstance(errors[0], PhotoAttachmentDuplicateError)
        assert (await counts(pg, asset_id))[1] == 1


async def attachment_state(pg, att_id) -> PhotoAttachment:
    async with pg.sessions() as s:
        return (await s.execute(select(PhotoAttachment).where(PhotoAttachment.id == att_id))).scalar_one()


async def test_f_g_h_patch_and_archive_races(pg):
    w = await world(pg)
    for _ in range(ROUNDS):
        _, att_id = await ready_asset(pg, w)

        async def patch(att_id=att_id, **kw):
            async with pg.sessions() as s:
                return await PhotoAttachmentService(s).update_attachment(w.owner, w.project, att_id, **kw)

        async def archive(att_id=att_id):
            async with pg.sessions() as s:
                return await PhotoAttachmentService(s).archive_attachment(w.owner, w.project, att_id)

        # F: PATCH x archive -> both effects survive (per-column UPDATEs)
        assert settled(await asyncio.gather(patch(caption="F"), archive(), return_exceptions=True))[1] == []
        row = await attachment_state(pg, att_id)
        assert row.caption == "F" and row.archived_at is not None
        # G: different fields -> both survive
        assert settled(await asyncio.gather(patch(caption="G"), patch(position=7), return_exceptions=True))[1] == []
        row = await attachment_state(pg, att_id)
        assert (row.caption, row.position) == ("G", 7)
        # H: same field -> last write wins (one of the two values, never a mix)
        assert settled(await asyncio.gather(patch(caption="H1"), patch(caption="H2"), return_exceptions=True))[1] == []
        assert (await attachment_state(pg, att_id)).caption in {"H1", "H2"}


async def test_i_j_k_asset_archive_races(pg):
    w = await world(pg)
    for i in range(ROUNDS):
        path = jpeg(pg.tmp / f"k{i}.jpg", (i, 9, 9))
        upload_id = str(uuid.uuid4())
        storage = InMemoryMediaStorage()
        first = await upload(pg, w, path, upload_id, storage=storage, processor=processor())
        asset_id, att_id = first.asset.id, first.attachment.id

        async def asset_op(archive: bool, asset_id=asset_id):
            async with pg.sessions() as s:
                service = PhotoAssetService(s)
                return await (service.archive if archive else service.restore)(asset_id, w.owner, w.project)

        # I: archive x restore -> one of the committed states; attachments untouched
        assert settled(await asyncio.gather(asset_op(True), asset_op(False), return_exceptions=True))[1] == []
        assert (await attachment_state(pg, att_id)).archived_at is None
        # J: archive x attach-existing -> both succeed
        async def attach(asset_id=asset_id):
            async with pg.sessions() as s:
                return await PhotoAttachmentService(s).create_attachment(
                    owner_id=w.owner, project_id=w.project, asset_id=asset_id,
                    target=AttachmentTarget(context=C.ROOM, room_id=w.room2))

        ok, errors = settled(await asyncio.gather(asset_op(True), attach(), return_exceptions=True))
        assert errors == [] and len(ok) == 2
        # K: archive x upload replay -> replay never restores
        replay_and_archive = await asyncio.gather(
            upload(pg, w, path, upload_id, storage=storage, processor=processor()), asset_op(True),
            return_exceptions=True)
        ok, errors = settled(replay_and_archive)
        assert errors == [] and ok[0].outcome is PhotoUploadOutcome.REPLAYED
        async with pg.sessions() as s:
            archived_at = (await s.execute(select(PhotoAsset.archived_at)
                                           .where(PhotoAsset.id == asset_id))).scalar_one()
        assert archived_at is not None
        assert len([k async for k in storage.iter_keys("photos/v1/")]) == 3  # replay wrote nothing new


# ---------------------------------------------------------------------------
# Quota: strict through ONE shared slot; not global across independent slots
# ---------------------------------------------------------------------------


def upload_size(pg, path: Path) -> int:
    ws = pg.tmp / f"measure-{uuid.uuid4()}"
    ws.mkdir()
    p = process_image_file(path, ws, ImagePipelineConfig())
    return p.byte_size + p.display.byte_size + p.thumbnail.byte_size


async def test_quota_is_strict_through_the_single_process_slot(pg):
    w = await world(pg)
    for i in range(ROUNDS):
        a, b = jpeg(pg.tmp / f"qa{i}.jpg", (i, 1, 2)), jpeg(pg.tmp / f"qb{i}.jpg", (i, 3, 4))
        async with pg.sessions() as s:
            used = await ups.logical_usage_bytes(s, w.owner)
        cap = used + max(upload_size(pg, a), upload_size(pg, b))  # room for exactly one more
        shared = processor()  # one process = one slot
        cfg = config(pg, soft_cap_bytes=cap, warning_bytes=1)
        results = await asyncio.gather(
            upload(pg, w, a, str(uuid.uuid4()), storage=InMemoryMediaStorage(), processor=shared, cfg=cfg),
            upload(pg, w, b, str(uuid.uuid4()), storage=InMemoryMediaStorage(), processor=shared, cfg=cfg),
            return_exceptions=True,
        )
        ok, errors = settled(results)
        assert len(ok) == 1 and len(errors) == 1 and isinstance(errors[0], PhotoStorageQuotaExceededError)
        async with pg.sessions() as s:
            assert await ups.logical_usage_bytes(s, w.owner) <= cap


async def test_quota_is_not_global_across_independent_slots_documented_constraint(pg, monkeypatch):
    """Two independent slots (= two worker processes) can both pass the check
    before either commits: this is the accepted F6 constraint (single Uvicorn
    process required), demonstrated deterministically with a barrier."""
    w = await world(pg)
    a, b = jpeg(pg.tmp / "oa.jpg", (5, 6, 7)), jpeg(pg.tmp / "ob.jpg", (8, 9, 10))
    async with pg.sessions() as s:
        used = await ups.logical_usage_bytes(s, w.owner)
    cap = used + max(upload_size(pg, a), upload_size(pg, b))
    barrier = asyncio.Barrier(2)
    real_usage = ups.logical_usage_bytes

    async def usage_then_wait(db, owner_id):
        value = await real_usage(db, owner_id)
        await barrier.wait()  # both requests have read the usage before either inserts
        return value

    monkeypatch.setattr(ups, "logical_usage_bytes", usage_then_wait)
    cfg = config(pg, soft_cap_bytes=cap, warning_bytes=1)
    results = await asyncio.gather(
        upload(pg, w, a, str(uuid.uuid4()), storage=InMemoryMediaStorage(), processor=processor(), cfg=cfg),
        upload(pg, w, b, str(uuid.uuid4()), storage=InMemoryMediaStorage(), processor=processor(), cfg=cfg),
        return_exceptions=True,
    )
    ok, errors = settled(results)
    assert len(ok) == 2 and errors == []  # both accepted
    monkeypatch.setattr(ups, "logical_usage_bytes", real_usage)
    async with pg.sessions() as s:
        assert await ups.logical_usage_bytes(s, w.owner) > cap  # overshoot -> single-worker constraint


# ---------------------------------------------------------------------------
# Keyset ordering with PostgreSQL timestamptz precision
# ---------------------------------------------------------------------------


async def test_keyset_traversal_with_identical_timestamps_on_postgres(pg):
    w = await world(pg)
    async with pg.sessions() as s:
        when = (await s.execute(select(func.now()))).scalar_one()
        for i in range(17):
            asset = PhotoAsset(
                id=uuid.uuid4(), owner_id=w.owner, project_id=w.project, status=R, storage_name="r2-primary",
                storage_key_original=f"k/{uuid.uuid4()}/o", storage_key_display=f"k/{uuid.uuid4()}/d",
                storage_key_thumbnail=f"k/{uuid.uuid4()}/t", content_type=PhotoContentType.JPEG, byte_size=10,
                display_byte_size=5, thumbnail_byte_size=2, width=1, height=1, sha256="ab" * 32,
                uploaded_at=when)
            s.add(asset)
            await s.flush()
            s.add(PhotoAttachment(asset_id=asset.id, project_id=w.project, context=C.PROJECT,
                                  category=PhotoCategory.GENERAL, position=i % 2))
        await s.commit()
    async with pg.sessions() as s:
        service = PhotoQueryService(s)
        full = [a.id for a, _ in (await service.list_photos(w.owner, w.project, PhotoListFilters(),
                                                            limit=100)).items]
        seen, cursor = [], None
        while True:
            page = await service.list_photos(w.owner, w.project, PhotoListFilters(), limit=4, cursor=cursor)
            seen += [a.id for a, _ in page.items]
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
    assert seen == full and len(set(seen)) == 17
