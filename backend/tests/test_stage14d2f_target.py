"""Stage 14D.2F — backup target port, verified create-only puts and run publication."""

import dataclasses
import hashlib
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup import target as tg
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from tests.test_stage14d2e_manifest import RUN, make_asset, make_header

DATA = b"backup-object-" * 500
OTHER_SAME_SIZE = b"BACKUP-OBJECT-" * 500
KEY = "smoke/14d2f/object.bin"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Sleeps:
    def __init__(self) -> None:
        self.values: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.values.append(seconds)


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.bin"
    path.write_bytes(DATA)
    return path


def unavailable(code: str = "ServiceUnavailable") -> MediaStorageUnavailable:
    return MediaStorageUnavailable("transient", error_code=code, http_status=503)


async def put(target: Any, source: Path, scratch: Path, sleeps: Sleeps | None = None, **kwargs: Any) -> tg.VerifiedPut:
    return await tg.put_verified(
        target,
        key=kwargs.pop("key", KEY),
        source=source,
        content_type="application/octet-stream",
        scratch_dir=scratch,
        sleep=sleeps or Sleeps(),
        **kwargs,
    )


def assert_no_leftovers(scratch: Path) -> None:
    assert list(scratch.iterdir()) == [], "temporary verification files must always be removed"


# --- the port ---------------------------------------------------------------------------------


def test_port_has_no_way_to_delete_overwrite_list_or_upload_in_parts():
    members = {name for name in dir(tg.BackupTarget) if not name.startswith("_")}
    assert members == {"put_new", "head", "download_to"}
    memory = tg.InMemoryBackupTarget()
    assert isinstance(memory, tg.BackupTarget)
    for forbidden in ("delete", "delete_object", "overwrite", "put_object", "multipart", "iter_keys", "list"):
        assert not hasattr(memory, forbidden)


async def test_in_memory_target_is_create_only(tmp_path: Path, source: Path):
    target = tg.InMemoryBackupTarget()
    assert await target.put_new(KEY, source, "text/plain") is tg.PutOutcome.CREATED
    other = tmp_path / "other.bin"
    other.write_bytes(b"different")
    assert await target.put_new(KEY, other, "text/plain") is tg.PutOutcome.EXISTS
    assert target.objects[KEY] == DATA  # never overwritten
    assert await target.head("missing/key") is None
    facts = await target.head(KEY)
    assert facts is not None and facts.size == len(DATA)
    destination = tmp_path / "download"
    await target.download_to(KEY, destination)
    assert destination.read_bytes() == DATA
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        await target.download_to(KEY, destination)  # downloads never replace a file
    with pytest.raises(MediaObjectNotFound):
        await target.download_to("missing/key", tmp_path / "x")
    for bad in ("", "/abs", "a/../b", "a//b", "a\\b"):
        with pytest.raises(ValueError):
            await target.head(bad)


# --- put_verified -----------------------------------------------------------------------------


async def test_create_verifies_by_full_redownload(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    result = await put(target, source, scratch, expected_sha256=sha(DATA), expected_size=len(DATA))
    assert result == tg.VerifiedPut(KEY, len(DATA), sha(DATA), created=True, etag=result.etag)
    assert result.etag is not None
    assert target.objects[KEY] == DATA and target.content_types[KEY] == "application/octet-stream"
    assert [call[0] for call in target.calls] == ["put_new", "head", "download_to"]
    assert_no_leftovers(scratch)


async def test_identical_object_already_present_is_an_idempotent_success(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    await put(target, source, scratch)
    again = await put(target, source, scratch)
    assert again.created is False and again.sha256 == sha(DATA)
    assert target.objects[KEY] == DATA
    assert_no_leftovers(scratch)


@pytest.mark.parametrize("existing", [OTHER_SAME_SIZE, b"short"], ids=["same-size", "different-size"])
async def test_a_different_object_is_a_conflict_and_is_never_overwritten(
    tmp_path: Path, source: Path, scratch: Path, existing: bytes
):
    target = tg.InMemoryBackupTarget()
    target.objects[KEY] = existing
    with pytest.raises(MediaObjectConflict):
        await put(target, source, scratch)
    assert target.objects[KEY] == existing
    assert_no_leftovers(scratch)


async def test_a_size_conflict_is_detected_without_downloading(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.objects[KEY] = b"short"
    with pytest.raises(MediaObjectConflict):
        await put(target, source, scratch)
    assert "download_to" not in [call[0] for call in target.calls]


@pytest.mark.parametrize(
    "kwargs",
    [{"expected_sha256": "0" * 64}, {"expected_size": 1}],
    ids=["sha256", "size"],
)
async def test_local_source_must_match_what_the_caller_expects_before_any_target_call(
    source: Path, scratch: Path, kwargs: dict[str, Any]
):
    target = tg.InMemoryBackupTarget()
    with pytest.raises(tg.SourceIntegrityError):
        await put(target, source, scratch, **kwargs)
    assert target.calls == [] and target.objects == {}


async def test_empty_source_and_invalid_keys_are_refused_before_any_target_call(tmp_path: Path, source: Path, scratch: Path):
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    target = tg.InMemoryBackupTarget()
    with pytest.raises(tg.SourceIntegrityError):
        await put(target, empty, scratch)
    for bad in ("", "/abs", "a/../b", "a//b"):
        with pytest.raises(ValueError):
            await put(target, source, scratch, key=bad)
    assert target.calls == []


async def test_transient_failures_are_retried_with_bounded_backoff(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.inject("put_new", unavailable(), times=2)
    target.inject("head", unavailable(), times=1)
    target.inject("download_to", unavailable(), times=1)
    sleeps = Sleeps()
    result = await put(target, source, scratch, sleeps)
    assert result.created is True
    assert sleeps.values == [1.0, 2.0, 1.0, 1.0]  # put x2, head, download: each attempt counter restarts per call
    assert_no_leftovers(scratch)


async def test_retries_are_exhausted_after_the_configured_attempts(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.inject("put_new", unavailable(), times=10)
    sleeps = Sleeps()
    with pytest.raises(MediaStorageUnavailable):
        await put(target, source, scratch, sleeps)
    assert [c for c in target.calls if c[0] == "put_new"].__len__() == tg.DEFAULT_RETRY.max_attempts
    assert sleeps.values == [1.0, 2.0, 4.0]
    assert target.objects == {}


async def test_permanent_failures_are_not_retried(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.inject("put_new", MediaStorageMisconfigured("denied", http_status=404))
    sleeps = Sleeps()
    with pytest.raises(MediaStorageMisconfigured):
        await put(target, source, scratch, sleeps)
    assert len(target.calls) == 1 and sleeps.values == []


async def test_an_ambiguous_put_is_resolved_by_verifying_the_existing_object(source: Path, scratch: Path):
    """The object was stored but the response was lost: the retry sees EXISTS and proves the bytes are ours."""
    target = tg.InMemoryBackupTarget()
    target.inject("put_new", unavailable("RequestTimeout"), apply_effect=True)
    result = await put(target, source, scratch)
    assert result.created is False
    assert target.objects == {KEY: DATA}
    assert_no_leftovers(scratch)


async def test_an_ambiguous_put_of_different_bytes_is_still_a_conflict(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.objects[KEY] = OTHER_SAME_SIZE
    target.inject("put_new", unavailable())
    with pytest.raises(MediaObjectConflict):
        await put(target, source, scratch)
    assert target.objects[KEY] == OTHER_SAME_SIZE


async def test_corruption_in_the_provider_is_caught_by_the_full_redownload(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.corrupt_on_store.add(KEY)
    with pytest.raises(tg.TargetVerificationError, match="differ"):
        await put(target, source, scratch)
    assert_no_leftovers(scratch)


async def test_an_object_that_is_not_visible_after_the_put_is_an_error(source: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.hide_after_put.add(KEY)
    with pytest.raises(tg.TargetVerificationError, match="not visible"):
        await put(target, source, scratch)


class ShortHeadTarget(tg.InMemoryBackupTarget):
    async def head(self, key: str) -> tg.TargetObject | None:
        real = await super().head(key)
        return None if real is None else tg.TargetObject(size=real.size - 1)


class TruncatingTarget(tg.InMemoryBackupTarget):
    async def download_to(self, key: str, path: Path) -> None:
        await super().download_to(key, path)
        path.write_bytes(path.read_bytes()[:-1])


class PartialThenCompleteTarget(tg.InMemoryBackupTarget):
    """First download leaves a partial file and fails, as a dropped connection would."""

    failed_once = False

    async def download_to(self, key: str, path: Path) -> None:
        if not self.failed_once:
            self.failed_once = True
            path.write_bytes(b"partial")
            raise unavailable("ConnectionError")
        await super().download_to(key, path)


class InspectingTarget(tg.InMemoryBackupTarget):
    def __init__(self) -> None:
        super().__init__()
        self.modes: dict[str, int] = {}

    async def download_to(self, key: str, path: Path) -> None:
        await super().download_to(key, path)
        self.modes = {"dir": stat.S_IMODE(path.parent.stat().st_mode), "file": stat.S_IMODE(path.stat().st_mode)}


async def test_a_size_mismatch_after_create_is_a_verification_error(source: Path, scratch: Path):
    with pytest.raises(tg.TargetVerificationError, match="size"):
        await put(ShortHeadTarget(), source, scratch)


async def test_a_truncated_download_is_a_verification_error(source: Path, scratch: Path):
    with pytest.raises(tg.TargetVerificationError, match="size"):
        await put(TruncatingTarget(), source, scratch)
    assert_no_leftovers(scratch)


async def test_a_partial_download_is_replaced_on_retry(source: Path, scratch: Path):
    result = await put(PartialThenCompleteTarget(), source, scratch)
    assert result.created is True and result.sha256 == sha(DATA)
    assert_no_leftovers(scratch)


async def test_verification_files_live_in_a_private_directory(source: Path, scratch: Path):
    target = InspectingTarget()
    await put(target, source, scratch)
    assert target.modes == {"dir": 0o700, "file": 0o600}


async def test_put_bytes_verified_stores_documents_and_removes_its_temporary_source(scratch: Path):
    target = tg.InMemoryBackupTarget()
    result = await tg.put_bytes_verified(
        target, key="runs/x/doc.json", data=b'{"a":1}\n', content_type="application/json", scratch_dir=scratch, sleep=Sleeps()
    )
    assert result.created is True and target.objects["runs/x/doc.json"] == b'{"a":1}\n'
    assert_no_leftovers(scratch)


def test_retry_policy_validation_and_delays():
    policy = tg.RetryPolicy(max_attempts=5, base_delay=2.0, factor=3.0, max_delay=10.0)
    assert [policy.delay(n) for n in (1, 2, 3, 4)] == [2.0, 6.0, 10.0, 10.0]
    for bad in ({"max_attempts": 0}, {"base_delay": -1}, {"factor": 0.5}, {"max_delay": -1}):
        with pytest.raises(ValueError):
            tg.RetryPolicy(**bad)


# --- publish_run --------------------------------------------------------------------------------


def dump_for(tmp_path: Path, data: bytes = b"encrypted-dump-" * 1000) -> Path:
    path = tmp_path / "plan-estimate.sql.gz.age"
    path.write_bytes(data)
    return path


def header_for(dump: Path, readies: list[Any], run_id: str = RUN) -> mf.ManifestHeader:
    base = make_header(readies, run_id)
    data = dump.read_bytes()
    return dataclasses.replace(
        base, db_dump=dataclasses.replace(base.db_dump, encrypted_sha256=sha(data), encrypted_size=len(data))
    )


def media(count: int) -> tuple[list[Any], list[mf.ManifestObject]]:
    readies, objects = [], []
    for index in range(count):
        ready, objs = make_asset(index)
        readies.append(ready)
        objects.extend(objs)
    return readies, objects


def seed_media(target: tg.InMemoryBackupTarget, objects: list[mf.ManifestObject]) -> None:
    for obj in objects:
        target.objects[obj.key] = b"x" * obj.size


async def publish(target: Any, dump: Path, scratch: Path, count: int = 0, **kwargs: Any) -> tg.PublishedRun:
    readies, objects = media(count)
    if isinstance(target, tg.InMemoryBackupTarget):
        seed_media(target, objects)
    return await tg.publish_run(
        target,
        header=header_for(dump, readies),
        objects=kwargs.pop("objects", objects),
        dump_path=dump,
        source_keys=3 * count,
        orphan_candidates=0,
        scratch_dir=scratch,
        sleep=Sleeps(),
        clock=kwargs.pop("clock", lambda: datetime(2026, 10, 4, 12, 10, tzinfo=UTC)),
        **kwargs,
    )


def puts(target: tg.InMemoryBackupTarget) -> list[str]:
    return [key for op, key in target.calls if op == "put_new"]


async def test_a_run_is_published_dump_then_manifest_then_complete_last(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    dump = dump_for(tmp_path)
    run = await publish(target, dump, scratch, count=2)
    assert puts(target) == [f"db/{RUN}/plan-estimate.sql.gz.age", f"runs/{RUN}/manifest.jsonl", f"runs/{RUN}/COMPLETE.json"]
    assert target.objects[f"db/{RUN}/plan-estimate.sql.gz.age"] == dump.read_bytes()
    sealed = mf.verify_run(target.objects[f"runs/{RUN}/COMPLETE.json"], target.objects[f"runs/{RUN}/manifest.jsonl"])
    assert (run.run_id, run.objects, run.ready_assets) == (RUN, 6, 2)
    assert run.manifest_sha256 == sealed.complete.manifest_sha256 == sha(target.objects[f"runs/{RUN}/manifest.jsonl"])
    assert run.complete_sha256 == sha(target.objects[f"runs/{RUN}/COMPLETE.json"])
    assert target.content_types[f"runs/{RUN}/manifest.jsonl"] == "application/x-ndjson"
    assert_no_leftovers(scratch)


async def test_every_listed_object_is_checked_before_the_seal(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    await publish(target, dump_for(tmp_path), scratch, count=1)
    calls = target.calls
    last_head_of_media = max(i for i, (op, key) in enumerate(calls) if op == "head" and key.startswith("photos/"))
    complete_put = next(i for i, (op, key) in enumerate(calls) if op == "put_new" and key.endswith("COMPLETE.json"))
    assert last_head_of_media < complete_put
    assert sum(1 for op, key in calls if op == "head" and key.startswith("photos/")) == 3


async def test_an_empty_ready_set_publishes_a_valid_zero_asset_run(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    run = await publish(target, dump_for(tmp_path), scratch, count=0)
    assert run.objects == 0 and run.ready_assets == 0
    assert sorted(target.objects) == [
        f"db/{RUN}/plan-estimate.sql.gz.age",
        f"runs/{RUN}/COMPLETE.json",
        f"runs/{RUN}/manifest.jsonl",
    ]


async def test_nothing_is_written_when_the_dump_does_not_match_the_header(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    dump = dump_for(tmp_path)
    readies, objects = media(0)
    header = header_for(dump, readies)
    dump.write_bytes(dump.read_bytes() + b"x")
    with pytest.raises(tg.SourceIntegrityError):
        await tg.publish_run(
            target, header=header, objects=objects, dump_path=dump, source_keys=0, orphan_candidates=0, scratch_dir=scratch
        )
    assert target.calls == []


async def test_nothing_is_written_when_the_manifest_is_inconsistent(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    dump = dump_for(tmp_path)
    readies, objects = media(2)
    with pytest.raises(mf.ManifestInvariantError):
        await tg.publish_run(
            target,
            header=header_for(dump, readies),
            objects=objects[:-1],  # one asset with two lines
            dump_path=dump,
            source_keys=0,
            orphan_candidates=0,
            scratch_dir=scratch,
        )
    assert target.calls == []


async def test_a_failing_manifest_upload_leaves_no_complete_marker(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.inject("put_new", MediaStorageMisconfigured("denied"), after=1)  # dump ok, manifest refused
    with pytest.raises(MediaStorageMisconfigured):
        await publish(target, dump_for(tmp_path), scratch)
    assert sorted(target.objects) == [f"db/{RUN}/plan-estimate.sql.gz.age"]


async def test_a_failing_seal_upload_leaves_a_manifest_without_complete(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.inject("put_new", unavailable(), times=10, after=2)
    with pytest.raises(MediaStorageUnavailable):
        await publish(target, dump_for(tmp_path), scratch)
    assert f"runs/{RUN}/manifest.jsonl" in target.objects
    assert f"runs/{RUN}/COMPLETE.json" not in target.objects  # incomplete by definition; nothing is deleted
    assert_no_leftovers(scratch)


async def test_a_missing_media_object_prevents_the_seal(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    readies, objects = media(1)
    seed_media(target, objects[:-1])  # the thumbnail was never admitted
    with pytest.raises(tg.TargetVerificationError, match="missing"):
        await tg.publish_run(
            target,
            header=header_for(dump_for(tmp_path), readies),
            objects=objects,
            dump_path=dump_for(tmp_path),
            source_keys=3,
            orphan_candidates=0,
            scratch_dir=scratch,
            sleep=Sleeps(),
        )
    assert f"runs/{RUN}/COMPLETE.json" not in target.objects


async def test_a_media_object_with_the_wrong_size_prevents_the_seal(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    readies, objects = media(1)
    seed_media(target, objects)
    target.objects[objects[0].key] = b"x" * (objects[0].size + 1)
    dump = dump_for(tmp_path)
    with pytest.raises(tg.TargetVerificationError, match="different size"):
        await tg.publish_run(
            target, header=header_for(dump, readies), objects=objects, dump_path=dump, source_keys=3,
            orphan_candidates=0, scratch_dir=scratch, sleep=Sleeps(),
        )
    assert f"runs/{RUN}/COMPLETE.json" not in target.objects


async def test_a_lost_seal_response_is_resolved_by_verification(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    target.inject("put_new", unavailable("RequestTimeout"), apply_effect=True, after=2)
    run = await publish(target, dump_for(tmp_path), scratch)
    sealed = mf.verify_run(target.objects[f"runs/{RUN}/COMPLETE.json"], target.objects[f"runs/{RUN}/manifest.jsonl"])
    assert sealed.run_id == RUN and run.complete_sha256 == sha(target.objects[f"runs/{RUN}/COMPLETE.json"])
    assert puts(target).count(f"runs/{RUN}/COMPLETE.json") == 2  # the timed-out put and the verified retry


async def test_publishing_the_same_run_again_never_overwrites_the_seal(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    dump = dump_for(tmp_path)
    await publish(target, dump, scratch)
    seal = target.objects[f"runs/{RUN}/COMPLETE.json"]
    with pytest.raises(MediaObjectConflict):  # same run id, later completed_at -> different seal bytes
        await publish(target, dump, scratch, clock=lambda: datetime(2026, 10, 4, 13, 0, tzinfo=UTC))
    assert target.objects[f"runs/{RUN}/COMPLETE.json"] == seal
    await publish(target, dump, scratch)  # an identical publication is an idempotent success
    assert target.objects[f"runs/{RUN}/COMPLETE.json"] == seal


async def test_a_clock_before_the_run_leaves_an_incomplete_run(tmp_path: Path, scratch: Path):
    target = tg.InMemoryBackupTarget()
    with pytest.raises(mf.ManifestInvariantError):
        await publish(target, dump_for(tmp_path), scratch, clock=lambda: datetime(2026, 10, 4, 11, 0, tzinfo=UTC))
    assert f"runs/{RUN}/COMPLETE.json" not in target.objects


def test_scratch_helper_modes(scratch: Path):
    assert stat.S_IMODE(os.stat(scratch).st_mode) == 0o700
