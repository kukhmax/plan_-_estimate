"""Stage 14D.2I.2 — media restore: sealed run (backup target) -> destination bucket."""

import asyncio
import dataclasses
import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup import restore_guards as rg
from app.backup import restore_media as rm
from app.backup import target as tg
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageMisconfigured,
)
from app.domain.services.media_backup_ready_set import ReadyAsset
from app.domain.services.media_storage import (
    InMemoryMediaStorage,
    ObjectInfo,
    _StoredObject,
)
from tests.test_stage14d2g_media_sync import (
    NO_RETRY,
    RETRY_3,
    RUN_1,
    FakeS3Client,
    Sleeps,
    World,
    sealed,
    unavailable,
)

DESTINATION = "plan-estimate-media-drill-restore"
PRODUCTION = "plan-estimate-media-prod"  # also the manifest's source bucket (make_header)
BACKUP = "plan-estimate-backup-prod"  # the manifest's target bucket (make_header)
FORBIDDEN = (PRODUCTION,)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def flip(data: bytes) -> bytes:
    return bytes([data[0] ^ 0xFF]) + data[1:]


class Destination:
    """In-memory destination store (the MediaStorageAdmin contract) with a call log and fault injection."""

    def __init__(self) -> None:
        self.inner = InMemoryMediaStorage()
        self.calls: list[tuple[str, str]] = []
        self.faults: dict[str, list[tuple[int, Exception]]] = {
            "put_object": [], "head_object": [], "download_to": [], "iter_keys": [],
        }  # fmt: skip
        self.corrupt_on_store: set[str] = set()
        self.truncate_on_store: set[str] = set()
        self.hide: set[str] = set()

    def seed(self, key: str, data: bytes) -> None:
        self.inner._objects[key] = _StoredObject(data=data, content_type="image/jpeg")

    def inject(self, operation: str, error: Exception, *, times: int = 1, after: int = 0) -> None:
        self.faults[operation].extend((after if n == 0 else 0, error) for n in range(times))

    def _fault(self, operation: str) -> Exception | None:
        queue = self.faults[operation]
        if not queue:
            return None
        skip, error = queue[0]
        if skip > 0:
            queue[0] = (skip - 1, error)
            return None
        queue.pop(0)
        return error

    async def put_object(self, key: str, source: Path, content_type: str) -> None:
        self.calls.append(("put_object", key))
        error = self._fault("put_object")
        if error is not None:
            raise error
        data = Path(source).read_bytes()
        existing = self.inner._objects.get(key)
        if existing is not None:
            if existing.data != data:
                raise MediaObjectConflict("object key already holds different content")
            return
        if key in self.corrupt_on_store:
            data = flip(data)
        if key in self.truncate_on_store:
            data = data[:-1]
        self.inner._objects[key] = _StoredObject(data=data, content_type=content_type)

    async def head_object(self, key: str) -> ObjectInfo | None:
        self.calls.append(("head_object", key))
        error = self._fault("head_object")
        if error is not None:
            raise error
        if key in self.hide and key in self.inner._objects and self._puts(key) > 0:
            return None
        return await self.inner.head_object(key)

    def _puts(self, key: str) -> int:
        return sum(1 for call in self.calls if call == ("put_object", key))

    async def download_to(self, key: str, path: Path) -> None:
        self.calls.append(("download_to", key))
        error = self._fault("download_to")
        if error is not None:
            raise error
        await self.inner.download_to(key, path)

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        return await self.inner.presign_get(key, ttl_seconds)

    async def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        self.calls.append(("iter_keys", prefix))
        error = self._fault("iter_keys")
        if error is not None:
            raise error
        async for key in self.inner.iter_keys(prefix):
            yield key

    def ops(self, name: str) -> list[str]:
        return [key for op, key in self.calls if op == name]


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


class Rig:
    def __init__(self, tmp_path: Path, scratch: Path, count: int = 2) -> None:
        self.tmp, self.scratch = tmp_path, scratch
        self.world = World(count)
        self.backup = tg.InMemoryBackupTarget()
        self.destination = Destination()
        self.run: mf.VerifiedRun | None = None
        self.ready_assets: list[ReadyAsset] = list(self.world.assets)

    async def seal(self) -> mf.VerifiedRun:
        if self.run is None:
            self.run = await sealed(self.world, self.backup, self.scratch, self.tmp, RUN_1)
            self.backup.calls.clear()
        return self.run

    async def restore(self, **overrides: Any) -> rm.MediaRestoreReport:
        run = await self.seal()
        options: dict[str, Any] = {
            "destination_bucket": DESTINATION,
            "forbidden_buckets": FORBIDDEN,
            "ready_assets": self.ready_assets,
            "scratch_dir": self.scratch,
            "retry": NO_RETRY,
            "sleep": Sleeps(),
        }
        options.update(overrides)
        return await rm.restore_media(self.backup, run, self.destination, **options)


@pytest.fixture
def rig(tmp_path: Path, scratch: Path) -> Rig:
    return Rig(tmp_path, scratch)


def assert_clean(rig: Rig) -> None:
    assert list(rig.scratch.iterdir()) == [], "scratch files hold object bytes and must always be removed"


def stored(rig: Rig) -> dict[str, bytes]:
    return {key: obj.data for key, obj in rig.destination.inner._objects.items()}


# --- the happy path -------------------------------------------------------------------------------------------------


async def test_every_object_is_restored_and_verified(rig: Rig):
    report = await rig.restore()
    contents = rig.world.contents
    assert report.ok and report.preflight is None and report.aborted is None and report.object_problems == ()
    assert report.counts == rm.RestoreCounts(
        objects_total=6, restored=6, already_present=0, failed=0, bytes_restored=sum(map(len, contents.values()))
    )
    assert stored(rig) == contents
    for obj in (await rig.seal()).manifest.objects:
        assert rig.destination.inner.get_content_type(obj.key) == obj.content_type
    assert_clean(rig)


async def test_objects_are_handled_one_at_a_time_in_key_order(rig: Rig):
    await rig.restore()
    puts = rig.destination.ops("put_object")
    assert puts == sorted(rig.world.contents), "canonical (key) order"
    assert rig.backup.calls and {op for op, _ in rig.backup.calls} == {"download_to"}, "the backup is only read"
    assert [key for op, key in rig.backup.calls] == sorted(rig.world.contents)


async def test_a_second_run_finds_everything_present_and_writes_nothing(rig: Rig):
    await rig.restore()
    rig.destination.calls.clear()
    rig.backup.calls.clear()
    report = await rig.restore()
    assert report.ok and report.counts.restored == 0 and report.counts.already_present == 6 and report.counts.bytes_restored == 0
    assert rig.destination.ops("put_object") == [] and rig.backup.calls == [], "nothing is read from the backup either"
    assert sorted(rig.destination.ops("download_to")) == sorted(rig.world.contents), "present objects are verified by SHA-256"


async def test_a_half_restored_destination_is_completed(rig: Rig):
    keys = sorted(rig.world.contents)
    for key in keys[:2]:
        rig.destination.seed(key, rig.world.contents[key])
    report = await rig.restore()
    assert report.ok and (report.counts.restored, report.counts.already_present) == (4, 2)
    assert stored(rig) == rig.world.contents


async def test_destination_verification_can_be_reduced_to_a_size_check(rig: Rig):
    report = await rig.restore(verify_destination=False)
    assert report.ok and rig.destination.ops("download_to") == [], "no re-download after the put"
    full = Rig(rig.tmp / "other", rig.scratch)
    (rig.tmp / "other").mkdir()
    assert (await full.restore()).ok and len(full.destination.ops("download_to")) == 6


async def test_the_destination_is_never_asked_to_do_anything_but_create_and_read(rig: Rig):
    await rig.restore()
    assert {op for op, _ in rig.destination.calls} <= {"put_object", "head_object", "download_to", "iter_keys"}
    assert {name for name in dir(rm.MediaStorageAdmin) if not name.startswith("_")} == {
        "put_object", "head_object", "presign_get", "download_to", "iter_keys",
    }  # fmt: skip


async def test_the_report_is_canonical_and_secret_free(rig: Rig):
    await rig.seal()
    key = min(rig.world.contents)
    rig.backup.objects[key] = flip(rig.backup.objects[key])
    report = await rig.restore()
    data = report.report_bytes()
    document = json.loads(data)
    assert data == mf.canonical_line(document) and data.count(b"\n") == 1
    assert document["format"] == "plan-estimate/media-restore-report/v1" and document["ok"] is False
    assert document["object_problem_totals"] == {"BACKUP_SHA_MISMATCH": 1}
    text = data.decode()
    assert "photos/v1" not in text and DESTINATION not in text and PRODUCTION not in text
    assert all(sha(content) not in text for content in rig.world.contents.values())
    assert report.report_bytes() == data


# --- guards ------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bucket", [PRODUCTION, BACKUP, "plan-estimate-media-drill-extra", "Not_A_Bucket", "", "x"]
)
async def test_a_forbidden_or_malformed_destination_is_refused_before_anything_is_touched(rig: Rig, bucket: str):
    forbidden = (*FORBIDDEN, "plan-estimate-media-drill-extra")
    report = await rig.restore(destination_bucket=bucket, forbidden_buckets=forbidden)
    assert report.preflight is rm.Preflight.DESTINATION_UNSAFE and not report.ok
    assert rig.destination.calls == [] and rig.backup.calls == []


async def test_the_runs_own_source_and_backup_buckets_are_always_forbidden(rig: Rig):
    run = await rig.seal()
    assert run.manifest.header.source.bucket == PRODUCTION and run.manifest.header.target.bucket == BACKUP
    for bucket in (PRODUCTION, BACKUP):
        report = await rig.restore(destination_bucket=bucket, forbidden_buckets=(), allow_non_drill=True)
        assert report.preflight is rm.Preflight.DESTINATION_UNSAFE, "even with an empty forbidden list"


async def test_a_bucket_that_is_not_a_drill_bucket_needs_an_explicit_real_restore(rig: Rig):
    assert (await rig.restore(destination_bucket="plan-estimate-media-new")).preflight is rm.Preflight.DESTINATION_UNSAFE
    assert rig.destination.calls == []
    report = await rig.restore(destination_bucket="plan-estimate-media-new", allow_non_drill=True)
    assert report.ok, "a deliberate disaster restore into a new bucket is possible"


@pytest.mark.parametrize("how", ["extra", "missing", "sha", "size", "key"])
async def test_a_manifest_that_does_not_describe_the_restored_database_is_refused(rig: Rig, how: str):
    rows = list(rig.ready_assets)
    if how == "extra":
        other = World(3).assets[2]
        rows.append(other)
    elif how == "missing":
        rows.pop()
    elif how == "sha":
        rows[0] = dataclasses.replace(rows[0], sha256="b" * 64)
    elif how == "size":
        rows[0] = dataclasses.replace(rows[0], byte_size=rows[0].byte_size + 1)
    else:
        rows[0] = dataclasses.replace(rows[0], key_display=rows[0].key_display.replace("display", "display2"))
    rig.ready_assets = rows
    report = await rig.restore()
    assert report.preflight is rm.Preflight.MANIFEST_DB_MISMATCH
    assert rig.destination.calls == [] and rig.backup.calls == [], "nothing is read or written"


async def test_objects_that_are_not_part_of_the_run_stop_the_restore(rig: Rig):
    rig.destination.seed("photos/v1/00000000-0000-4000-8000-0000000000aa/original.jpg", b"newer upload")
    rig.destination.seed("photos/v1/00000000-0000-4000-8000-0000000000bb/display.jpg", b"newer upload")
    rig.destination.seed("elsewhere/not-counted.bin", b"outside the photo prefix")
    report = await rig.restore()
    assert report.preflight is rm.Preflight.FOREIGN_OBJECTS_PRESENT and not report.ok
    assert report.counts.foreign_objects == 2 and report.counts.restored == 0
    assert rig.destination.ops("put_object") == [] and rig.backup.calls == []


async def test_objects_of_the_run_itself_are_not_foreign(rig: Rig):
    rig.destination.seed(min(rig.world.contents), rig.world.contents[min(rig.world.contents)])
    assert (await rig.restore()).ok


async def test_foreign_objects_can_be_allowed_explicitly_and_are_left_alone(rig: Rig):
    foreign = "photos/v1/00000000-0000-4000-8000-0000000000aa/original.jpg"
    rig.destination.seed(foreign, b"newer upload")
    report = await rig.restore(allow_foreign_objects=True)
    assert report.ok and report.counts.foreign_objects == 1
    assert stored(rig)[foreign] == b"newer upload"


async def test_listing_failures_are_reported_before_any_write(rig: Rig):
    rig.destination.inject("iter_keys", unavailable())
    assert (await rig.restore()).preflight is rm.Preflight.STORAGE_UNAVAILABLE
    rig.destination.inject("iter_keys", MediaStorageMisconfigured("denied", http_status=403))
    assert (await rig.restore()).preflight is rm.Preflight.STORAGE_MISCONFIGURED
    assert rig.destination.ops("put_object") == []


async def test_a_transient_listing_error_is_retried(rig: Rig):
    rig.destination.inject("iter_keys", unavailable(), times=2)
    sleeps = Sleeps()
    assert (await rig.restore(retry=RETRY_3, sleep=sleeps)).ok and sleeps.values


def test_invalid_arguments(tmp_path: Path):
    with pytest.raises(ValueError):
        asyncio.run(
            rm.restore_media(
                tg.InMemoryBackupTarget(), None, Destination(),  # type: ignore[arg-type]
                destination_bucket=DESTINATION, forbidden_buckets=(), ready_assets=[], scratch_dir=tmp_path,
                max_consecutive_unavailable=0,
            )
        )  # fmt: skip


# --- the backup side ------------------------------------------------------------------------------------------------------------


async def test_an_object_missing_from_the_backup_is_reported_and_the_rest_restored(rig: Rig):
    key = sorted(rig.world.contents)[2]
    await rig.seal()
    del rig.backup.objects[key]
    report = await rig.restore()
    assert not report.ok and report.aborted is None
    assert [(p.code, p.asset_id) for p in report.object_problems] == [
        (rm.ObjectProblemCode.MISSING_BACKUP_OBJECT, report.object_problems[0].asset_id)
    ]
    assert report.counts.restored == 5 and key not in stored(rig)
    assert_clean(rig)


async def test_a_backup_object_of_the_wrong_size_is_not_written(rig: Rig):
    await rig.seal()
    key = min(rig.world.contents)
    rig.backup.objects[key] += b"!"
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.BACKUP_SIZE_MISMATCH]
    assert key not in stored(rig)


async def test_a_backup_object_with_changed_bytes_is_not_written(rig: Rig):
    await rig.seal()
    key = min(rig.world.contents)
    rig.backup.objects[key] = flip(rig.backup.objects[key])
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.BACKUP_SHA_MISMATCH]
    assert key not in stored(rig) and report.counts.restored == 5
    assert_clean(rig)


async def test_transient_backup_errors_are_retried_and_a_persistent_one_is_that_objects_problem(rig: Rig):
    await rig.seal()
    rig.backup.inject("download_to", unavailable(), times=2)
    sleeps = Sleeps()
    assert (await rig.restore(retry=RETRY_3, sleep=sleeps)).ok and sleeps.values == [0.5, 1.0]
    other = Rig(rig.tmp / "o2", rig.scratch)
    (rig.tmp / "o2").mkdir()
    await other.seal()
    other.backup.inject("download_to", unavailable())
    report = await other.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.BACKUP_UNAVAILABLE]
    assert report.aborted is None and report.counts.restored == 5


async def test_a_misconfigured_backup_aborts_the_run(rig: Rig):
    await rig.seal()
    rig.backup.inject("download_to", MediaStorageMisconfigured("denied", error_code="AccessDenied", http_status=403))
    report = await rig.restore()
    assert report.aborted is rm.AbortReason.BACKUP_MISCONFIGURED and not report.ok
    assert report.counts.restored == 0 and rig.destination.ops("put_object") == []


# --- the destination side -------------------------------------------------------------------------------------------------------------


async def test_an_existing_object_of_another_size_is_a_conflict_and_is_not_downloaded(rig: Rig):
    key = min(rig.world.contents)
    rig.destination.seed(key, rig.world.contents[key] + b"!")
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_CONFLICT]
    assert key not in rig.destination.ops("download_to") and key not in rig.destination.ops("put_object")
    assert stored(rig)[key] == rig.world.contents[key] + b"!", "never overwritten"


async def test_an_existing_object_of_the_same_size_but_other_bytes_is_a_conflict(rig: Rig):
    key = sorted(rig.world.contents)[1]
    rig.destination.seed(key, flip(rig.world.contents[key]))
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_CONFLICT]
    assert key not in rig.destination.ops("put_object")
    assert stored(rig)[key] == flip(rig.world.contents[key]) and report.counts.restored == 5


async def test_a_put_that_loses_a_race_is_a_conflict(rig: Rig):
    rig.destination.inject("put_object", MediaObjectConflict("object key already holds different content"))
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_CONFLICT]


async def test_an_object_corrupted_by_the_destination_fails_verification(rig: Rig):
    key = sorted(rig.world.contents)[3]
    rig.destination.corrupt_on_store.add(key)
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_VERIFICATION_FAILED]
    reduced = Rig(rig.tmp / "o3", rig.scratch)
    (rig.tmp / "o3").mkdir()
    reduced.destination.corrupt_on_store.add(key)
    assert (await reduced.restore(verify_destination=False)).ok, "documented: a same-size change needs the SHA-256 check"


async def test_an_object_stored_with_the_wrong_size_fails_even_the_reduced_check(rig: Rig):
    key = min(rig.world.contents)
    rig.destination.truncate_on_store.add(key)
    for verify in (True, False):
        other = Rig(rig.tmp / f"v{verify}", rig.scratch)
        (rig.tmp / f"v{verify}").mkdir()
        other.destination.truncate_on_store.add(key)
        report = await other.restore(verify_destination=verify)
        assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_VERIFICATION_FAILED]


async def test_an_object_that_is_not_visible_after_the_put_fails_verification(rig: Rig):
    key = min(rig.world.contents)
    rig.destination.hide.add(key)
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_VERIFICATION_FAILED]


async def test_an_object_that_vanishes_before_the_check_fails_verification(rig: Rig):
    rig.destination.inject("download_to", MediaObjectNotFound("gone"))
    report = await rig.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_VERIFICATION_FAILED]


async def test_transient_destination_errors_are_retried_a_persistent_one_is_that_objects_problem(rig: Rig):
    rig.destination.inject("put_object", unavailable(), times=2, after=1)
    sleeps = Sleeps()
    assert (await rig.restore(retry=RETRY_3, sleep=sleeps)).ok and sleeps.values
    other = Rig(rig.tmp / "o4", rig.scratch)
    (rig.tmp / "o4").mkdir()
    other.destination.inject("put_object", unavailable(), after=2)
    report = await other.restore()
    assert [p.code for p in report.object_problems] == [rm.ObjectProblemCode.DESTINATION_UNAVAILABLE]
    assert report.aborted is None and report.counts.restored == 5


async def test_a_streak_of_unavailable_failures_aborts(rig: Rig):
    rig.destination.inject("put_object", unavailable(), times=100)
    report = await rig.restore(max_consecutive_unavailable=3)
    assert report.aborted is rm.AbortReason.STORAGE_UNAVAILABLE and len(report.object_problems) == 3 and not report.ok
    assert len(rig.destination.ops("put_object")) == 3, "nothing after the breaker opened"


async def test_the_streak_resets_after_a_success(rig: Rig):
    rig.destination.inject("put_object", unavailable())
    rig.destination.inject("put_object", unavailable(), after=2)
    report = await rig.restore(max_consecutive_unavailable=2)
    assert report.aborted is None and len(report.object_problems) == 2 and report.counts.restored == 4


async def test_a_misconfigured_destination_aborts_the_run(rig: Rig):
    rig.destination.inject("put_object", MediaStorageMisconfigured("denied", error_code="AccessDenied", http_status=403))
    report = await rig.restore()
    assert report.aborted is rm.AbortReason.DESTINATION_MISCONFIGURED and report.counts.restored == 0


@pytest.mark.parametrize("error", [RuntimeError("boom"), asyncio.CancelledError()])
async def test_unexpected_errors_and_cancellation_propagate_and_clean_up(rig: Rig, error: BaseException):
    await rig.seal()
    rig.backup.inject("download_to", error)  # type: ignore[arg-type]
    with pytest.raises(type(error)):
        await rig.restore()
    assert_clean(rig)


async def test_scratch_is_clean_after_every_outcome(rig: Rig):
    keys = sorted(rig.world.contents)
    await rig.seal()
    rig.backup.objects[keys[0]] = flip(rig.backup.objects[keys[0]])
    rig.destination.seed(keys[1], flip(rig.world.contents[keys[1]]))
    rig.destination.corrupt_on_store.add(keys[2])
    report = await rig.restore()
    assert len(report.object_problems) == 3
    assert_clean(rig)


def test_ok_requires_every_object_to_be_accounted_for():
    base = {"run_id": RUN_1, "preflight": None, "object_problems": (), "aborted": None}
    assert rm.MediaRestoreReport(counts=rm.RestoreCounts(objects_total=2, restored=1, already_present=1), **base).ok
    assert not rm.MediaRestoreReport(counts=rm.RestoreCounts(objects_total=2, restored=1), **base).ok
    assert not rm.MediaRestoreReport(counts=rm.RestoreCounts(objects_total=2, restored=2), **{**base, "aborted": rm.AbortReason.STORAGE_UNAVAILABLE}).ok
    assert not rm.MediaRestoreReport(counts=rm.RestoreCounts(objects_total=2, restored=2), **{**base, "preflight": rm.Preflight.DESTINATION_UNSAFE}).ok


def test_the_report_lists_a_bounded_number_of_problems():
    problems = tuple(
        rm.ObjectProblem(f"00000000-0000-4000-8000-{n:012d}", mf.Role.ORIGINAL, rm.ObjectProblemCode.MISSING_BACKUP_OBJECT)
        for n in range(rm.MAX_LISTED_PROBLEMS + 25)
    )
    report = rm.MediaRestoreReport(RUN_1, None, problems, None, rm.RestoreCounts(objects_total=len(problems)))
    document = json.loads(report.report_bytes())
    assert len(document["object_problems"]) == rm.MAX_LISTED_PROBLEMS and document["object_problems_omitted"] == 25
    assert document["object_problem_totals"] == {"MISSING_BACKUP_OBJECT": rm.MAX_LISTED_PROBLEMS + 25}


# --- guard function ---------------------------------------------------------------------------------------------------------------------


def test_the_guard_function_directly():
    rg.validate_restore_media_target(DESTINATION, forbidden_buckets=FORBIDDEN)
    rg.validate_restore_media_target("plan-estimate-media-new", forbidden_buckets=FORBIDDEN, allow_non_drill=True)
    for bucket in (PRODUCTION, "plan-estimate-media-new", "UPPER", "a", "-bad-", "", "drill bucket", "drill/../x", "drill\n", "Drill_X", "drill" * 20):
        with pytest.raises(rg.UnsafeRestoreMediaTargetError):
            rg.validate_restore_media_target(bucket, forbidden_buckets=FORBIDDEN)
    with pytest.raises(rg.UnsafeRestoreMediaTargetError) as excinfo:
        rg.validate_restore_media_target(PRODUCTION, forbidden_buckets=FORBIDDEN, allow_non_drill=True)
    assert PRODUCTION not in str(excinfo.value), "messages never echo the bucket"


# --- the production S3 adapter as the destination ------------------------------------------------------------------------------------------------------


class FakeS3Store(FakeS3Client):
    """FakeS3Client plus the write side S3MediaStorage uses (conditional put, HEAD)."""

    def put_object(self, **params: Any) -> dict[str, Any]:
        from botocore.exceptions import ClientError

        key = params["Key"]
        if params.get("IfNoneMatch") == "*" and key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}, "PutObject")
        self.objects[key] = params["Body"].read()
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        from botocore.exceptions import ClientError

        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key]), "ETag": f'"{hashlib.md5(self.objects[Key]).hexdigest()}"'}


async def test_the_real_s3_adapter_works_as_the_destination(rig: Rig):
    from app.core.s3_media_storage import S3MediaStorage

    client = FakeS3Store({})
    destination = S3MediaStorage(
        endpoint_url="https://example.invalid", bucket=DESTINATION, region="auto", access_key_id="k", secret_access_key="s", client=client
    )
    run = await rig.seal()
    options: dict[str, Any] = {
        "destination_bucket": DESTINATION, "forbidden_buckets": FORBIDDEN, "ready_assets": rig.ready_assets,
        "scratch_dir": rig.scratch, "retry": NO_RETRY, "sleep": Sleeps(),
    }  # fmt: skip
    report = await rm.restore_media(rig.backup, run, destination, **options)
    assert report.ok and report.counts.restored == 6 and client.objects == rig.world.contents
    assert all(body.closed for body in client.bodies), "every response body is closed"
    again = await rm.restore_media(rig.backup, run, destination, **options)
    assert again.ok and again.counts.already_present == 6, "a resumed run over the real adapter"
    client.objects[min(client.objects)] = flip(client.objects[min(client.objects)])
    conflict = await rm.restore_media(rig.backup, run, destination, **options)
    assert [p.code for p in conflict.object_problems] == [rm.ObjectProblemCode.DESTINATION_CONFLICT]
    client.objects["photos/v1/00000000-0000-4000-8000-0000000000cc/original.jpg"] = b"x"
    assert (await rm.restore_media(rig.backup, run, destination, **options)).preflight is rm.Preflight.FOREIGN_OBJECTS_PRESENT
