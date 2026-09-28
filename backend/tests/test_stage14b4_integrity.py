"""Stage 14B.4 — read-only media integrity check (engine + CLI)."""

import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.domain.exceptions import MediaStorageMisconfigured, MediaStorageUnavailable
from app.domain.photos.keys import PhotoFormat, build_photo_object_keys
from app.domain.services.media_integrity import FindingKind, Severity, run_integrity_check
from app.domain.services.media_storage import InMemoryMediaStorage
from app.domain.services.photo_asset_service import PhotoAssetSnapshot
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType
from scripts import media_integrity_check as cli
from tests.conftest import TestingSessionLocal
from tests.test_estimates import _make_project, _make_user

ORIGINAL = b"original-bytes" * 100
DISPLAY = b"display" * 50
THUMB = b"thumb" * 10
FAKE_SECRET = "fake-secret-must-not-print"


class SpyStorage(InMemoryMediaStorage):
    """In-memory store that records every call; writes are forbidden."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.allow_writes = True

    async def put_object(self, key, source, content_type):
        if not self.allow_writes:
            raise AssertionError("integrity check must never write")
        self.calls.append("put_object")
        return await super().put_object(key, source, content_type)

    async def head_object(self, key):
        self.calls.append("head_object")
        return await super().head_object(key)

    async def presign_get(self, key, ttl_seconds):
        raise AssertionError("integrity check must never presign")

    async def download_to(self, key, path):
        self.calls.append("download_to")
        return await super().download_to(key, path)

    async def iter_keys(self, prefix):
        self.calls.append("iter_keys")
        async for key in super().iter_keys(prefix):
            yield key


async def put(storage, tmp_path, key, data):
    src = tmp_path / f"src-{uuid.uuid4()}"
    src.write_bytes(data)
    await storage.put_object(key, src, "image/jpeg")


def snapshot(status=PhotoAssetStatus.READY, storage_name="r2-primary", created_at=None, **sizes):
    asset_id = uuid.uuid4()
    keys = build_photo_object_keys(asset_id, PhotoFormat.JPEG)
    return PhotoAssetSnapshot(
        id=asset_id,
        status=status,
        storage_name=storage_name,
        storage_key_original=keys.original,
        storage_key_display=keys.display,
        storage_key_thumbnail=keys.thumbnail,
        byte_size=sizes.get("byte_size", len(ORIGINAL)),
        display_byte_size=sizes.get("display_byte_size", len(DISPLAY)),
        thumbnail_byte_size=sizes.get("thumbnail_byte_size", len(THUMB)),
        sha256=hashlib.sha256(ORIGINAL).hexdigest(),
        created_at=created_at or datetime.now(timezone.utc),
    )


async def store_all(storage, tmp_path, snap, skip=(), original=ORIGINAL):
    for variant, key, data in (
        ("original", snap.storage_key_original, original),
        ("display", snap.storage_key_display, DISPLAY),
        ("thumbnail", snap.storage_key_thumbnail, THUMB),
    ):
        if variant not in skip:
            await put(storage, tmp_path, key, data)


async def check(assets, storage, tmp_path, **kw):
    storage.allow_writes = False
    storage.calls.clear()
    return await run_integrity_check(assets, storage, storage_name="r2-primary", temp_dir=str(tmp_path / "tmp"), **kw)


def kinds(report):
    return [f.kind for f in report.findings]


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------


async def test_empty_db_and_empty_storage(tmp_path):
    report = await check([], SpyStorage(), tmp_path)
    assert report.findings == [] and report.exit_code() == 0


async def test_ready_asset_all_objects_present(tmp_path):
    storage, snap = SpyStorage(), snapshot()
    await store_all(storage, tmp_path, snap)
    report = await check([snap], storage, tmp_path)
    assert report.findings == [] and report.expected_present == 3 and report.exit_code() == 0
    assert set(storage.calls) == {"head_object", "iter_keys"}  # no download without opt-in


@pytest.mark.parametrize(
    "missing, kind",
    [("original", FindingKind.MISSING_ORIGINAL), ("display", FindingKind.MISSING_DERIVATIVE),
     ("thumbnail", FindingKind.MISSING_DERIVATIVE)],
)
async def test_ready_asset_missing_object(tmp_path, missing, kind):
    storage, snap = SpyStorage(), snapshot()
    await store_all(storage, tmp_path, snap, skip={missing})
    report = await check([snap], storage, tmp_path)
    assert kinds(report) == [kind]
    assert report.findings[0].severity is Severity.ERROR and report.exit_code() == 1


async def test_size_mismatch(tmp_path):
    storage, snap = SpyStorage(), snapshot(display_byte_size=len(DISPLAY) + 1)
    await store_all(storage, tmp_path, snap)
    report = await check([snap], storage, tmp_path)
    assert kinds(report) == [FindingKind.SIZE_MISMATCH] and report.exit_code() == 1
    assert "expected" in report.findings[0].detail


async def test_checksum_verified_and_mismatch_only_with_opt_in(tmp_path):
    storage, good, bad = SpyStorage(), snapshot(), snapshot()
    await store_all(storage, tmp_path, good)
    tampered = bytearray(ORIGINAL)
    tampered[0] ^= 0xFF  # same size, different bytes
    await store_all(storage, tmp_path, bad, original=bytes(tampered))
    plain = await check([good, bad], storage, tmp_path)
    assert plain.findings == []  # sizes match; checksum not compared without opt-in
    verified = await check([good, bad], storage, tmp_path, verify_sha256=True)
    assert kinds(verified) == [FindingKind.CHECKSUM_MISMATCH]
    assert verified.findings[0].asset_id == str(bad.id) and verified.checksum_verified == 1
    assert list((tmp_path / "tmp").iterdir()) == []  # downloads removed


async def test_unexpected_and_unknown_keys_are_candidates_only(tmp_path):
    storage, snap = SpyStorage(), snapshot()
    await store_all(storage, tmp_path, snap)
    orphan = f"photos/v1/{uuid.uuid4()}/original.png"
    await put(storage, tmp_path, orphan, b"x")
    await put(storage, tmp_path, "photos/v1/not-a-uuid/random.bin", b"y")
    await put(storage, tmp_path, "photos/other/outside-v1.bin", b"w")  # outside the checked prefix
    await put(storage, tmp_path, "unrelated/outside-prefix.bin", b"z")
    report = await check([snap], storage, tmp_path)
    by_kind = {f.kind: f for f in report.findings}
    assert set(by_kind) == {FindingKind.ORPHAN_CANDIDATE, FindingKind.UNKNOWN_KEY}
    assert by_kind[FindingKind.ORPHAN_CANDIDATE].key == orphan
    assert all(f.severity is Severity.WARNING for f in report.findings)
    assert report.exit_code() == 0 and report.exit_code(strict=True) == 1
    text = " ".join(f.detail for f in report.findings).lower()
    assert "safe to delete" not in text


async def test_pending_asset_fresh_and_stale(tmp_path):
    storage = SpyStorage()
    fresh = snapshot(PhotoAssetStatus.PENDING)
    stale = snapshot(PhotoAssetStatus.PENDING, created_at=datetime.now(timezone.utc) - timedelta(days=2))
    await store_all(storage, tmp_path, fresh, skip={"thumbnail"})
    report = await check([fresh, stale], storage, tmp_path)
    found = {f.asset_id: f for f in report.findings}
    assert found[str(fresh.id)].kind is FindingKind.PENDING_INCOMPLETE
    assert found[str(fresh.id)].severity is Severity.INFO and "2/3" in found[str(fresh.id)].detail
    assert found[str(stale.id)].severity is Severity.WARNING and "stale" in found[str(stale.id)].detail
    assert report.exit_code() == 0  # PENDING objects are not orphans and not errors


async def test_failed_asset_objects_classified_not_orphan(tmp_path):
    storage, snap = SpyStorage(), snapshot(PhotoAssetStatus.FAILED)
    await store_all(storage, tmp_path, snap, skip={"display", "thumbnail"})
    report = await check([snap], storage, tmp_path)
    assert kinds(report) == [FindingKind.FAILED_RELATED]
    assert "1/3" in report.findings[0].detail and report.exit_code() == 0


async def test_other_storage_rows_not_checked_and_not_orphans(tmp_path):
    storage, mine, theirs = SpyStorage(), snapshot(), snapshot(storage_name="backup-oci")
    await store_all(storage, tmp_path, mine)
    await store_all(storage, tmp_path, theirs)
    report = await check([mine, theirs], storage, tmp_path)
    assert kinds(report) == [FindingKind.OTHER_STORAGE]
    assert report.checked_assets == {"READY": 1}


async def test_storage_unavailable_propagates(tmp_path):
    class Down(SpyStorage):
        async def head_object(self, key):
            raise MediaStorageUnavailable("down", error_code="SlowDown", http_status=503)

    with pytest.raises(MediaStorageUnavailable):
        await check([snapshot()], Down(), tmp_path)


async def test_no_mutation_of_storage(tmp_path):
    storage, snap = SpyStorage(), snapshot()
    await store_all(storage, tmp_path, snap, skip={"display"})
    before = {k: storage.get_bytes(k) async for k in storage.iter_keys("")}
    await check([snap], storage, tmp_path, verify_sha256=True)
    after = {k: storage.get_bytes(k) async for k in storage.iter_keys("")}
    assert before == after
    assert "put_object" not in storage.calls
    assert not hasattr(storage, "delete_object")


# --------------------------------------------------------------------------
# CLI (database + storage)
# --------------------------------------------------------------------------


def s3_settings(**kw) -> Settings:
    return Settings(
        _env_file=None,
        MEDIA_STORAGE_BACKEND="s3",
        MEDIA_STORAGE_NAME="r2-primary",
        MEDIA_S3_ENDPOINT_URL="https://example-account.eu.r2.cloudflarestorage.com",
        MEDIA_S3_BUCKET="bucket",
        MEDIA_S3_ACCESS_KEY_ID="FAKEKEYID",
        MEDIA_S3_SECRET_ACCESS_KEY=FAKE_SECRET,
        **kw,
    )


async def make_row(db, user, project, status=PhotoAssetStatus.READY):
    asset_id = uuid.uuid4()
    keys = build_photo_object_keys(asset_id, PhotoFormat.JPEG)
    row = PhotoAsset(
        id=asset_id, owner_id=user.id, project_id=project.id, status=status, storage_name="r2-primary",
        storage_key_original=keys.original, storage_key_display=keys.display, storage_key_thumbnail=keys.thumbnail,
        content_type=PhotoContentType.JPEG, byte_size=len(ORIGINAL), display_byte_size=len(DISPLAY),
        thumbnail_byte_size=len(THUMB), width=10, height=10, sha256=hashlib.sha256(ORIGINAL).hexdigest(),
    )
    db.add(row)
    await db.commit()
    return row


async def run_cli(argv, settings, storage):
    out = io.StringIO()
    code = await cli.run(argv, settings=settings, session_factory=TestingSessionLocal,
                         storage_factory=lambda _s: storage, out=out)
    return code, out.getvalue()


async def test_cli_disabled_storage_fails_safely(db_session):
    called = []
    out = io.StringIO()
    code = await cli.run([], settings=Settings(_env_file=None), session_factory=TestingSessionLocal,
                         storage_factory=lambda s: called.append(s), out=out)
    assert code == cli.EXIT_CANNOT_RUN and called == []
    assert "disabled" in out.getvalue() and "not assumed empty" in out.getvalue()


async def test_cli_clean_and_error_exit_codes_without_mutation(db_session, tmp_path):
    user = await _make_user(db_session, 6001)
    project = await _make_project(db_session, user.id)
    row = await make_row(db_session, user, project)
    storage = SpyStorage()
    await put(storage, tmp_path, row.storage_key_original, ORIGINAL)
    await put(storage, tmp_path, row.storage_key_display, DISPLAY)
    await put(storage, tmp_path, row.storage_key_thumbnail, THUMB)
    storage.allow_writes = False
    settings = s3_settings(PHOTO_TEMP_DIR=str(tmp_path / "t"))
    before = (row.id, row.status, row.updated_at.replace(tzinfo=None))

    code, out = await run_cli([], settings, storage)
    assert code == cli.EXIT_CLEAN and "0 error(s)" in out

    missing = SpyStorage()
    await put(missing, tmp_path, row.storage_key_original, ORIGINAL)
    missing.allow_writes = False
    code, out = await run_cli(["--json"], settings, missing)
    assert code == cli.EXIT_INTEGRITY_ERRORS
    payload = json.loads(out)
    assert payload["errors"] == 2 and {f["kind"] for f in payload["findings"]} == {"MISSING_DERIVATIVE"}

    db_session.expire_all()
    fresh = (await db_session.execute(select(PhotoAsset).where(PhotoAsset.id == before[0]))).scalar_one()
    assert (fresh.id, fresh.status, fresh.updated_at.replace(tzinfo=None)) == before  # DB unchanged
    for text in (out,):
        assert FAKE_SECRET not in text and "FAKEKEYID" not in text
        assert "X-Amz" not in text and "http" not in text


async def test_cli_storage_errors_exit_2(db_session, tmp_path):
    class Broken(SpyStorage):
        async def iter_keys(self, prefix):
            raise MediaStorageMisconfigured("denied", error_code="AccessDenied", http_status=403)
            yield  # pragma: no cover

    code, out = await run_cli([], s3_settings(PHOTO_TEMP_DIR=str(tmp_path)), Broken())
    assert code == cli.EXIT_CANNOT_RUN
    assert "incomplete" in out and "AccessDenied" in out and FAKE_SECRET not in out
