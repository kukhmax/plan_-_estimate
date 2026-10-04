"""Stage 14D.2G — media sync: READY set from the source store into the backup target."""

import asyncio
import dataclasses
import hashlib
import json
import os
import stat
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup import media_sync as ms
from app.backup import target as tg
from app.backup.run_id import RunIdError
from app.domain.exceptions import (
    MediaObjectNotFound,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from app.domain.services.media_backup_ready_set import ReadyAsset
from app.domain.services.media_storage import InMemoryMediaStorage, _StoredObject
from tests.test_stage14d2e_manifest import asset_id, make_header

RUN_1 = "20261004T120000Z-0123abcd"
RUN_2 = "20261005T120000Z-4567abcd"
RUN_3 = "20261006T120000Z-89abcdef"
BUCKET = "plan-estimate-backup-prod"  # the bucket make_header() records as the target
NOW = datetime(2026, 10, 4, 12, 5, tzinfo=UTC)
LATER = datetime(2026, 10, 4, 12, 10, tzinfo=UTC)
NO_RETRY = tg.RetryPolicy(max_attempts=1, base_delay=0.0)
RETRY_3 = tg.RetryPolicy(max_attempts=3, base_delay=0.5)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unavailable() -> MediaStorageUnavailable:
    return MediaStorageUnavailable("transient", error_code="ServiceUnavailable", http_status=503)


class Sleeps:
    def __init__(self) -> None:
        self.values: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.values.append(seconds)


# --- source double -----------------------------------------------------------------------------------


class Source:
    """In-memory source store with call log and fault injection (download_to / iter_keys)."""

    def __init__(self) -> None:
        self.inner = InMemoryMediaStorage()
        self.calls: list[tuple[str, str]] = []
        self.faults: dict[str, list[tuple[int, Exception]]] = {"download_to": [], "iter_keys": []}

    def add(self, key: str, data: bytes) -> None:
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

    async def download_to(self, key: str, path: Path) -> None:
        self.calls.append(("download_to", key))
        error = self._fault("download_to")
        if error is not None:
            raise error
        await self.inner.download_to(key, path)

    async def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        self.calls.append(("iter_keys", prefix))
        error = self._fault("iter_keys")
        if error is not None:
            raise error
        async for key in self.inner.iter_keys(prefix):
            yield key

    def downloads(self) -> list[str]:
        return [key for op, key in self.calls if op == "download_to"]


class World:
    def __init__(self, count: int = 2) -> None:
        self.source = Source()
        self.contents: dict[str, bytes] = {}
        self.assets: list[ReadyAsset] = []
        extensions = ("jpg", "png", "webp")
        for index in range(count):
            aid = asset_id(index)
            base = f"photos/v1/{aid}/"
            ext = extensions[index % 3]
            original = f"original-{index}-".encode() * (40 + index)
            display = f"display-{index}-".encode() * (20 + index)
            thumb = f"thumb-{index}-".encode() * (5 + index)
            keys = (f"{base}original.{ext}", f"{base}display.jpg", f"{base}thumb.jpg")
            for key, data in zip(keys, (original, display, thumb), strict=True):
                self.contents[key] = data
                self.source.add(key, data)
            self.assets.append(ReadyAsset(aid, *keys, len(original), len(display), len(thumb), sha(original)))

    def keys(self) -> list[str]:
        return sorted(self.contents)

    def key_of(self, index: int, role: str) -> str:
        asset = self.assets[index]
        return {"original": asset.key_original, "display": asset.key_display, "thumbnail": asset.key_thumbnail}[role]

    def ordered_keys(self) -> list[str]:
        """The order the engine must visit: assets by id text, then original, display, thumbnail."""
        ordered: list[str] = []
        for asset in sorted(self.assets, key=lambda item: str(item.asset_id)):
            ordered += [asset.key_original, asset.key_display, asset.key_thumbnail]
        return ordered


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


async def run_sync(
    world: World,
    target: tg.InMemoryBackupTarget,
    scratch: Path,
    *,
    run_id: str = RUN_1,
    prior: mf.VerifiedRun | None = None,
    deep: bool = False,
    retry: tg.RetryPolicy = NO_RETRY,
    sleeps: Sleeps | None = None,
    assets: list[ReadyAsset] | None = None,
    **kwargs: Any,
) -> ms.MediaSyncResult:
    return await ms.sync_media(
        world.source,
        target,
        assets=world.assets if assets is None else assets,
        run_id=run_id,
        target_bucket=kwargs.pop("target_bucket", BUCKET),
        scratch_dir=scratch,
        prior=prior,
        deep=deep,
        retry=retry,
        sleep=sleeps or Sleeps(),
        clock=lambda: NOW,
        **kwargs,
    )


async def publish(
    world: World, target: tg.InMemoryBackupTarget, result: ms.MediaSyncResult, scratch: Path, tmp_path: Path, run_id: str
) -> tg.PublishedRun:
    dump = tmp_path / f"dump-{run_id}"
    data = b"encrypted-dump-" * 50 + run_id.encode()
    dump.write_bytes(data)
    header = make_header(world.assets, run_id)
    header = dataclasses.replace(
        header, db_dump=dataclasses.replace(header.db_dump, encrypted_sha256=sha(data), encrypted_size=len(data))
    )
    return await tg.publish_run(
        target,
        header=header,
        objects=result.objects_for_publication(),
        dump_path=dump,
        source_keys=result.source_keys,
        orphan_candidates=result.orphan_candidates,
        scratch_dir=scratch,
        sleep=Sleeps(),
        clock=lambda: LATER,
    )


async def sealed(
    world: World, target: tg.InMemoryBackupTarget, scratch: Path, tmp_path: Path, run_id: str = RUN_1
) -> mf.VerifiedRun:
    result = await run_sync(world, target, scratch, run_id=run_id)
    await publish(world, target, result, scratch, tmp_path, run_id)
    return await ms.load_prior_run(target, run_id, scratch_dir=scratch, retry=NO_RETRY, sleep=Sleeps())


def assert_clean(scratch: Path) -> None:
    assert list(scratch.iterdir()) == [], "scratch files hold object bytes and must always be removed"


# --- first run: copy --------------------------------------------------------------------------------


async def test_first_run_copies_every_object_and_verifies_it(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    result = await run_sync(world, target, scratch)

    assert result.complete and not result.failures and result.aborted is None
    assert result.counts == ms.SyncCounts(
        copied=6, inherited=0, verified_present=0, failed=0, bytes_copied=sum(map(len, world.contents.values())), objects_required=6
    )
    assert [obj.key for obj in result.objects] == world.keys()
    for obj in result.objects:
        assert obj.action is mf.Action.COPIED and obj.sha_provenance == mf.DOWNLOADED
        assert obj.sha256 == sha(world.contents[obj.key]) and obj.size == len(world.contents[obj.key])
        assert target.objects[obj.key] == world.contents[obj.key]
        assert obj.verified_at == "2026-10-04T12:05:00Z"
        assert obj.target_etag is not None
    assert_clean(scratch)


async def test_content_types_follow_the_object_role_and_original_format(scratch: Path):
    world, target = World(3), tg.InMemoryBackupTarget()
    await run_sync(world, target, scratch)
    assert target.content_types[world.key_of(0, "original")] == "image/jpeg"
    assert target.content_types[world.key_of(1, "original")] == "image/png"
    assert target.content_types[world.key_of(2, "original")] == "image/webp"
    for index in range(3):
        assert target.content_types[world.key_of(index, "display")] == "image/jpeg"
        assert target.content_types[world.key_of(index, "thumbnail")] == "image/jpeg"


async def test_objects_are_handled_one_at_a_time_in_canonical_order(scratch: Path):
    world, target = World(3), tg.InMemoryBackupTarget()
    await run_sync(world, target, scratch)
    first_touch: list[str] = []
    for op, key in target.calls:
        if op == "head" and key in world.contents and key not in first_touch:
            first_touch.append(key)
    assert first_touch == world.ordered_keys()
    assert world.source.downloads() == world.ordered_keys()


async def test_a_complete_run_is_publishable_and_verifies(scratch: Path, tmp_path: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    result = await run_sync(world, target, scratch)
    published = await publish(world, target, result, scratch, tmp_path, RUN_1)
    verified = mf.verify_run(target.objects[published.complete_key], target.objects[published.manifest_key])
    assert verified.run_id == RUN_1 and verified.manifest.summary.objects == 6
    assert verified.manifest.summary.source_keys == 6 and verified.manifest.summary.orphan_candidates == 0
    assert_clean(scratch)


async def test_an_empty_ready_set_is_a_complete_run(scratch: Path, tmp_path: Path):
    world, target = World(0), tg.InMemoryBackupTarget()
    world.source.add("photos/v1/00000000-0000-4000-8000-000000000000/original.jpg", b"stray")
    result = await run_sync(world, target, scratch)
    assert result.complete and result.objects == () and result.counts.objects_required == 0
    assert (result.source_keys, result.orphan_candidates) == (1, 1)
    await publish(world, target, result, scratch, tmp_path, RUN_1)


# --- validation before any I/O ------------------------------------------------------------------------


async def test_invalid_input_is_refused_before_any_storage_call(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    duplicate = [world.assets[0], world.assets[0]]
    with pytest.raises(ms.MediaSyncError, match="asset twice"):
        await run_sync(world, target, scratch, assets=duplicate)
    shared_key = dataclasses.replace(world.assets[1], key_display=world.assets[0].key_display)
    with pytest.raises(ms.MediaSyncError, match="not valid for its role"):
        await run_sync(world, target, scratch, assets=[world.assets[0], shared_key])
    wrong_role = dataclasses.replace(world.assets[0], key_display=world.assets[0].key_display.replace("display.jpg", "display.png"))
    with pytest.raises(ms.MediaSyncError):
        await run_sync(world, target, scratch, assets=[wrong_role])
    with pytest.raises(RunIdError):
        await run_sync(world, target, scratch, run_id="not-a-run")
    with pytest.raises(ValueError):
        await run_sync(world, target, scratch, max_consecutive_unavailable=0)
    assert target.calls == [] and world.source.calls == []
    assert_clean(scratch)


async def test_error_messages_never_echo_keys(scratch: Path):
    world = World(1)
    wrong = dataclasses.replace(world.assets[0], key_display="photos/v1/secret-key-value/display.jpg")
    with pytest.raises(ms.MediaSyncError) as excinfo:
        await run_sync(world, tg.InMemoryBackupTarget(), scratch, assets=[wrong])
    assert "secret-key-value" not in str(excinfo.value)


# --- second run: inheritance (plan §8) -------------------------------------------------------------------


async def test_a_second_run_inherits_everything_without_downloading(scratch: Path, tmp_path: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path, RUN_1)
    world.source.calls.clear()
    target.calls.clear()

    result = await run_sync(world, target, scratch, run_id=RUN_2, prior=prior)

    assert result.complete
    assert result.counts.inherited == 6 and result.counts.copied == 0 and result.counts.verified_present == 0
    assert world.source.downloads() == [], "nothing may be read from the source for an inherited object"
    assert not [call for call in target.calls if call[0] in ("put_new", "download_to")]
    for obj in result.objects:
        assert obj.action is mf.Action.ALREADY_PRESENT
        assert obj.sha_provenance == f"inherited:{RUN_1}"
        assert obj.sha256 == sha(world.contents[obj.key])
    await publish(world, target, result, scratch, tmp_path, RUN_2)
    assert_clean(scratch)


async def test_an_object_missing_from_the_target_is_copied_even_with_a_prior_run(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path)
    lost = world.key_of(0, "display")
    del target.objects[lost]
    result = await run_sync(world, target, scratch, run_id=RUN_2, prior=prior)
    by_key = {obj.key: obj for obj in result.objects}
    assert by_key[lost].action is mf.Action.COPIED and by_key[lost].sha_provenance == mf.DOWNLOADED
    assert result.counts.copied == 1 and result.counts.inherited == 2


async def test_a_target_object_of_another_size_is_a_conflict_not_an_inheritance(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path)
    key = world.key_of(0, "thumbnail")
    original = target.objects[key]
    target.objects[key] = original + b"!"
    world.source.calls.clear()
    target.calls.clear()
    result = await run_sync(world, target, scratch, run_id=RUN_2, prior=prior)
    assert [f.code for f in result.failures] == [ms.FailureCode.TARGET_CONFLICT]
    assert not result.complete and target.objects[key] == original + b"!", "never overwritten"
    assert ("put_new", key) not in target.calls
    assert key not in world.source.downloads(), "a size mismatch needs no download to be refused"


async def test_when_the_source_changed_under_a_known_key_the_target_is_not_trusted(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path)
    key = world.key_of(0, "original")
    changed = bytes([world.contents[key][0] ^ 0xFF]) + world.contents[key][1:]
    world.source.add(key, changed)
    world.assets[0] = dataclasses.replace(world.assets[0], sha256=sha(changed))  # the database row follows the source
    target.calls.clear()
    result = await run_sync(world, target, scratch, run_id=RUN_2, prior=prior)
    assert [f.code for f in result.failures] == [ms.FailureCode.TARGET_CONFLICT]
    assert target.objects[key] == world.contents[key], "the earlier backup copy stays untouched"
    assert ("put_new", key) not in target.calls


async def test_deep_mode_verifies_by_download_and_compares_with_the_source(scratch: Path, tmp_path: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path)
    world.source.calls.clear()
    target.calls.clear()
    result = await run_sync(world, target, scratch, run_id=RUN_2, prior=prior, deep=True)
    assert result.complete and result.counts.verified_present == 6 and result.counts.inherited == 0
    assert sorted(world.source.downloads()) == world.keys()
    assert sorted(key for op, key in target.calls if op == "download_to") == world.keys()
    assert all(obj.sha_provenance == mf.DOWNLOADED and obj.action is mf.Action.ALREADY_PRESENT for obj in result.objects)


async def test_without_a_prior_run_existing_objects_are_verified_not_assumed(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    await run_sync(world, target, scratch)  # crashed run: objects exist, no seal
    world.source.calls.clear()
    result = await run_sync(world, target, scratch, run_id=RUN_2)
    assert result.complete and result.counts.verified_present == 3 and result.counts.copied == 0
    assert len(world.source.downloads()) == 3


async def test_a_same_size_but_different_target_object_is_never_locked_into_the_backup(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    key = world.key_of(0, "display")
    good = world.contents[key]
    target.objects[key] = bytes([good[0] ^ 0xFF]) + good[1:]
    target.content_types[key] = "image/jpeg"
    result = await run_sync(world, target, scratch)
    assert [f.code for f in result.failures] == [ms.FailureCode.TARGET_CONFLICT]
    assert target.objects[key] != good, "the tool has no overwrite path"
    assert ("put_new", key) not in target.calls, "an existing object is verified or refused, never put over"
    assert {obj.key for obj in result.objects} == set(world.keys()) - {key}


async def test_resume_after_a_partial_run_completes_without_a_prior(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    missing = world.key_of(1, "display")
    del world.source.inner._objects[missing]
    first = await run_sync(world, target, scratch)
    assert [f.code for f in first.failures] == [ms.FailureCode.MISSING_SOURCE] and first.counts.copied == 5
    world.source.add(missing, world.contents[missing])
    second = await run_sync(world, target, scratch, run_id=RUN_2)
    assert second.complete and second.counts.copied == 1 and second.counts.verified_present == 5


async def test_a_prior_run_must_be_earlier_and_for_the_same_bucket(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path, RUN_2)
    with pytest.raises(ms.PriorRunError):
        await run_sync(world, target, scratch, run_id=RUN_2, prior=prior)
    with pytest.raises(ms.PriorRunError):
        await run_sync(world, target, scratch, run_id=RUN_1, prior=prior)
    with pytest.raises(ms.PriorRunError):
        await run_sync(world, target, scratch, run_id=RUN_3, prior=prior, target_bucket="plan-estimate-backup-drill")
    assert_clean(scratch)


async def test_a_scratch_file_that_changes_after_hashing_is_never_uploaded(scratch: Path, monkeypatch: pytest.MonkeyPatch):
    """The bytes put into the target must be the bytes that were hashed and compared (defence in depth)."""
    world, target = World(1), tg.InMemoryBackupTarget()
    real = ms.file_facts
    calls = {"n": 0}

    def lying_file_facts(path: Path) -> tuple[int, str]:
        calls["n"] += 1
        size, digest = real(path)
        return (size, "0" * 64) if calls["n"] == 2 else (size, digest)  # object 1 is the original; 2 the display

    monkeypatch.setattr(ms, "file_facts", lying_file_facts)
    with pytest.raises(tg.SourceIntegrityError):
        await run_sync(world, target, scratch)
    assert world.key_of(0, "display") not in target.objects
    assert_clean(scratch)


# --- source failures --------------------------------------------------------------------------------


async def test_a_source_object_that_is_missing_is_reported_and_never_published(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    missing = world.key_of(0, "original")
    del world.source.inner._objects[missing]
    result = await run_sync(world, target, scratch)
    assert not result.complete and result.aborted is None
    assert result.failures == (ms.ObjectFailure(str(world.assets[0].asset_id), mf.Role.ORIGINAL, ms.FailureCode.MISSING_SOURCE),)
    assert missing not in target.objects and len(result.objects) == 5, "the run goes on for a complete report"
    with pytest.raises(ms.MediaSyncIncomplete):
        result.objects_for_publication()
    assert_clean(scratch)


@pytest.mark.parametrize("role", ["original", "display", "thumbnail"])
async def test_a_source_object_of_the_wrong_size_is_not_copied(scratch: Path, role: str):
    world, target = World(1), tg.InMemoryBackupTarget()
    key = world.key_of(0, role)
    world.source.add(key, world.contents[key] + b"x")
    result = await run_sync(world, target, scratch)
    assert [f.code for f in result.failures] == [ms.FailureCode.SOURCE_SIZE_MISMATCH]
    assert key not in target.objects and len(result.objects) == 2


async def test_an_original_that_differs_from_the_database_sha_is_not_copied(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    key = world.key_of(0, "original")
    data = world.contents[key]
    world.source.add(key, bytes([data[0] ^ 0xFF]) + data[1:])  # same size, different bytes
    result = await run_sync(world, target, scratch)
    assert [f.code for f in result.failures] == [ms.FailureCode.SOURCE_SHA_MISMATCH]
    assert key not in target.objects
    assert_clean(scratch)


async def test_a_derivative_has_no_database_hash_so_its_bytes_are_recorded_as_found(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    key = world.key_of(0, "display")
    data = world.contents[key]
    altered = bytes([data[0] ^ 0xFF]) + data[1:]
    world.source.add(key, altered)
    result = await run_sync(world, target, scratch)
    assert result.complete
    assert {obj.key: obj for obj in result.objects}[key].sha256 == sha(altered)


async def test_transient_source_errors_are_retried_with_backoff(scratch: Path):
    world, target, sleeps = World(1), tg.InMemoryBackupTarget(), Sleeps()
    world.source.inject("download_to", unavailable(), times=2)
    result = await run_sync(world, target, scratch, retry=RETRY_3, sleeps=sleeps)
    assert result.complete and sleeps.values == [0.5, 1.0]


async def test_a_source_that_stays_unavailable_fails_that_object_only(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    world.source.inject("download_to", unavailable(), times=1)
    result = await run_sync(world, target, scratch)
    assert [f.code for f in result.failures] == [ms.FailureCode.SOURCE_UNAVAILABLE]
    assert len(result.objects) == 2 and result.aborted is None


async def test_a_misconfigured_source_aborts_the_run_at_once(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    world.source.inject("download_to", MediaStorageMisconfigured("denied", error_code="AccessDenied", http_status=403))
    result = await run_sync(world, target, scratch)
    assert result.aborted is ms.AbortReason.SOURCE_MISCONFIGURED and not result.complete
    assert len(world.source.downloads()) == 1 and result.objects == ()
    assert not any(op == "iter_keys" for op, _ in world.source.calls)
    assert_clean(scratch)


# --- target failures --------------------------------------------------------------------------------


async def test_transient_target_errors_are_retried(scratch: Path):
    world, target, sleeps = World(1), tg.InMemoryBackupTarget(), Sleeps()
    target.inject("put_new", unavailable(), times=2)
    result = await run_sync(world, target, scratch, retry=RETRY_3, sleeps=sleeps)
    assert result.complete and result.counts.copied == 3 and sleeps.values == [0.5, 1.0]


async def test_a_put_whose_response_was_lost_is_resolved_by_verification(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    target.inject("put_new", unavailable(), apply_effect=True)  # stored, but the answer never arrived
    result = await run_sync(world, target, scratch, retry=RETRY_3)
    assert result.complete and result.counts.copied == 2 and result.counts.verified_present == 1
    (resolved,) = [obj for obj in result.objects if obj.action is mf.Action.ALREADY_PRESENT]
    assert resolved.sha_provenance == mf.DOWNLOADED and resolved.key == world.ordered_keys()[0]
    await publish(world, target, result, scratch, tmp_path, RUN_1)


async def test_an_object_corrupted_by_the_store_fails_verification(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    key = world.key_of(0, "thumbnail")
    target.corrupt_on_store.add(key)
    result = await run_sync(world, target, scratch)
    assert [f.code for f in result.failures] == [ms.FailureCode.TARGET_VERIFICATION_FAILED]
    assert key not in {obj.key for obj in result.objects}


async def test_an_object_that_is_not_visible_after_the_put_fails_verification(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    target.hide_after_put.add(world.key_of(0, "display"))
    result = await run_sync(world, target, scratch)
    assert [f.code for f in result.failures] == [ms.FailureCode.TARGET_VERIFICATION_FAILED]


async def test_a_target_that_stays_unavailable_aborts_after_a_streak(scratch: Path):
    world, target = World(3), tg.InMemoryBackupTarget()
    target.inject("head", unavailable(), times=100)
    result = await run_sync(world, target, scratch, max_consecutive_unavailable=3)
    assert result.aborted is ms.AbortReason.STORAGE_UNAVAILABLE
    assert [f.code for f in result.failures] == [ms.FailureCode.TARGET_UNAVAILABLE] * 3
    assert len([c for c in target.calls if c[0] == "head"]) == 3, "no attempt after the breaker opened"
    assert not any(op == "iter_keys" for op, _ in world.source.calls)


async def test_the_unavailable_streak_resets_after_a_success(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    target.inject("head", unavailable(), times=2)
    result = await run_sync(world, target, scratch, max_consecutive_unavailable=3)
    assert result.aborted is None and len(result.failures) == 2 and len(result.objects) == 4
    target2 = tg.InMemoryBackupTarget()
    target2.inject("head", unavailable(), times=1)
    # HEAD calls: 1 fails (object 1); 2 and 3 are object 2's pre-check and post-put check; 4 fails (object 3)
    target2.inject("head", unavailable(), times=1, after=2)
    result2 = await run_sync(world, target2, scratch, max_consecutive_unavailable=2)
    assert result2.aborted is None and len(result2.failures) == 2 and len(result2.objects) == 4, (
        "failures separated by a success are not a streak"
    )


async def test_a_misconfigured_target_aborts_the_run_at_once(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    target.inject("head", MediaStorageMisconfigured("denied", error_code="BucketNotFound", http_status=404))
    result = await run_sync(world, target, scratch)
    assert result.aborted is ms.AbortReason.TARGET_MISCONFIGURED and result.objects == ()
    assert len(target.calls) == 1 and world.source.calls == []


async def test_a_target_object_that_vanishes_during_verification_is_reported(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    await run_sync(world, target, scratch)
    target.inject("download_to", MediaObjectNotFound("gone"))
    result = await run_sync(world, target, scratch, run_id=RUN_2)
    assert [f.code for f in result.failures] == [ms.FailureCode.TARGET_VERIFICATION_FAILED]


# --- source listing (source_keys / orphan_candidates) --------------------------------------------------


async def test_orphan_candidates_are_counted_and_never_copied(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    world.source.add("photos/v1/00000000-0000-4000-8000-0000000000aa/original.jpg", b"pending-asset")
    world.source.add("photos/v1/00000000-0000-4000-8000-0000000000bb/display.jpg", b"orphan")
    world.source.add("other-prefix/not-counted.bin", b"ignored")
    result = await run_sync(world, target, scratch)
    assert result.complete and (result.source_keys, result.orphan_candidates) == (8, 2)
    assert not [key for key in target.objects if "0000000000aa" in key or "0000000000bb" in key or "other-prefix" in key]


async def test_a_failed_listing_makes_the_run_incomplete(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    world.source.inject("iter_keys", unavailable())
    result = await run_sync(world, target, scratch)
    assert [(f.asset_id, f.role, f.code) for f in result.failures] == [(None, None, ms.FailureCode.SOURCE_LISTING_FAILED)]
    assert len(result.objects) == 3 and not result.complete


async def test_the_listing_is_retried_from_the_start(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    world.source.inject("iter_keys", unavailable(), times=2)
    result = await run_sync(world, target, scratch, retry=RETRY_3)
    assert result.complete and result.source_keys == 3


async def test_a_misconfigured_listing_aborts(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    world.source.inject("iter_keys", MediaStorageMisconfigured("denied", http_status=403))
    result = await run_sync(world, target, scratch)
    assert result.aborted is ms.AbortReason.SOURCE_MISCONFIGURED and not result.complete


# --- scratch hygiene and unexpected errors ---------------------------------------------------------------


async def test_scratch_directories_are_private(scratch: Path):
    seen: list[int] = []

    class Spy(Source):
        async def download_to(self, key: str, path: Path) -> None:
            seen.append(stat.S_IMODE(os.stat(path.parent).st_mode))
            await super().download_to(key, path)

    world = World(1)
    spy = Spy()
    spy.inner = world.source.inner
    world.source = spy
    await run_sync(world, tg.InMemoryBackupTarget(), scratch)
    assert seen and set(seen) == {0o700}


@pytest.mark.parametrize("error", [RuntimeError("boom"), asyncio.CancelledError()])
async def test_unexpected_errors_and_cancellation_propagate_and_clean_up(scratch: Path, error: BaseException):
    world, target = World(1), tg.InMemoryBackupTarget()
    world.source.inject("download_to", error)  # type: ignore[arg-type]
    with pytest.raises(type(error)):
        await run_sync(world, target, scratch)
    assert_clean(scratch)


async def test_scratch_is_clean_after_every_failure_kind(scratch: Path):
    world, target = World(3), tg.InMemoryBackupTarget()
    del world.source.inner._objects[world.key_of(0, "original")]
    world.source.add(world.key_of(1, "display"), b"short")
    target.corrupt_on_store.add(world.key_of(2, "thumbnail"))
    result = await run_sync(world, target, scratch)
    assert len(result.failures) == 3
    assert_clean(scratch)


# --- report ----------------------------------------------------------------------------------------------


async def test_the_report_is_canonical_and_secret_free(scratch: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    del world.source.inner._objects[world.key_of(0, "original")]
    result = await run_sync(world, target, scratch)
    data = result.report_bytes()
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    document = json.loads(data)
    assert document["format"] == "plan-estimate/media-sync-report/v1" and document["complete"] is False
    assert document["failures"] == [
        {"asset_id": str(world.assets[0].asset_id), "role": "original", "code": "MISSING_SOURCE"}
    ]
    assert document["counts"]["copied"] == 5 and document["aborted"] is None
    text = data.decode()
    assert "photos/v1" not in text and all(sha(content) not in text for content in world.contents.values())
    assert data == mf.canonical_line(document), "canonical form: sorted keys, compact, ASCII"
    assert result.report_bytes() == data, "deterministic"


async def test_the_report_of_a_complete_run(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    document = json.loads((await run_sync(world, target, scratch)).report_bytes())
    assert document["complete"] is True and document["failures"] == [] and document["aborted"] is None


async def test_the_report_names_the_abort_reason(scratch: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    target.inject("head", MediaStorageMisconfigured("denied", http_status=403))
    document = json.loads((await run_sync(world, target, scratch)).report_bytes())
    assert document["aborted"] == "TARGET_MISCONFIGURED" and document["complete"] is False


# --- the real S3 adapter as the source ----------------------------------------------------------------------------


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def iter_chunks(self, chunk_size: int) -> Any:
        for start in range(0, len(self._data), chunk_size):
            yield self._data[start : start + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeS3Client:
    """Just enough of boto3's S3 client for S3MediaStorage.download_to / iter_keys."""

    def __init__(self, objects: dict[str, bytes], page_size: int = 4) -> None:
        self.objects, self.page_size = objects, page_size
        self.bodies: list[FakeBody] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        from botocore.exceptions import ClientError

        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "GetObject")
        body = FakeBody(self.objects[Key])
        self.bodies.append(body)
        return {"Body": body}

    def list_objects_v2(self, **params: Any) -> dict[str, Any]:
        keys = sorted(key for key in self.objects if key.startswith(params["Prefix"]))
        start = int(params.get("ContinuationToken", 0))
        page = keys[start : start + self.page_size]
        more = start + self.page_size < len(keys)
        response: dict[str, Any] = {"Contents": [{"Key": key} for key in page], "IsTruncated": more}
        if more:
            response["NextContinuationToken"] = str(start + self.page_size)
        return response


async def test_the_real_s3_adapter_works_as_the_source(scratch: Path, tmp_path: Path):
    from app.core.s3_media_storage import S3MediaStorage

    world, target = World(3), tg.InMemoryBackupTarget()
    client = FakeS3Client({**world.contents, "photos/v1/00000000-0000-4000-8000-0000000000cc/original.jpg": b"orphan"})
    storage = S3MediaStorage(
        endpoint_url="https://example.invalid", bucket="source-drill", region="auto", access_key_id="k", secret_access_key="s", client=client
    )
    result = await ms.sync_media(
        storage,
        target,
        assets=world.assets,
        run_id=RUN_1,
        target_bucket=BUCKET,
        scratch_dir=scratch,
        retry=NO_RETRY,
        sleep=Sleeps(),
        clock=lambda: NOW,
    )
    assert result.complete and result.counts.copied == 9
    assert (result.source_keys, result.orphan_candidates) == (10, 1), "pagination of the listing is followed"
    assert all(body.closed for body in client.bodies), "every response body is closed"
    for key, data in world.contents.items():
        assert target.objects[key] == data
    assert_clean(scratch)


async def test_the_real_s3_adapter_reports_a_missing_source_object(scratch: Path):
    from app.core.s3_media_storage import S3MediaStorage

    world, target = World(1), tg.InMemoryBackupTarget()
    objects = dict(world.contents)
    del objects[world.key_of(0, "thumbnail")]
    storage = S3MediaStorage(
        endpoint_url="https://example.invalid", bucket="source-drill", region="auto", access_key_id="k", secret_access_key="s", client=FakeS3Client(objects)
    )
    result = await ms.sync_media(
        storage, target, assets=world.assets, run_id=RUN_1, target_bucket=BUCKET, scratch_dir=scratch, retry=NO_RETRY, sleep=Sleeps(), clock=lambda: NOW
    )
    assert [f.code for f in result.failures] == [ms.FailureCode.MISSING_SOURCE]
    assert_clean(scratch)


# --- load_prior_run ---------------------------------------------------------------------------------------


async def test_load_prior_run_returns_the_verified_run(scratch: Path, tmp_path: Path):
    world, target = World(2), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path)
    assert prior.run_id == RUN_1 and prior.manifest.summary.objects == 6
    assert prior.object_for(world.key_of(0, "original")) is not None
    assert_clean(scratch)


async def test_load_prior_run_refuses_a_missing_run(scratch: Path):
    with pytest.raises(ms.PriorRunError):
        await ms.load_prior_run(tg.InMemoryBackupTarget(), RUN_1, scratch_dir=scratch, retry=NO_RETRY, sleep=Sleeps())
    assert_clean(scratch)


async def test_load_prior_run_refuses_an_unsealed_run(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    await sealed(world, target, scratch, tmp_path)
    del target.objects[mf.complete_key(RUN_1)]
    with pytest.raises(ms.PriorRunError):
        await ms.load_prior_run(target, RUN_1, scratch_dir=scratch, retry=NO_RETRY, sleep=Sleeps())


async def test_load_prior_run_refuses_a_manifest_the_seal_does_not_match(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    await sealed(world, target, scratch, tmp_path)
    target.objects[mf.manifest_key(RUN_1)] += b" "
    with pytest.raises(ms.PriorRunError):
        await ms.load_prior_run(target, RUN_1, scratch_dir=scratch, retry=NO_RETRY, sleep=Sleeps())
    assert_clean(scratch)


async def test_load_prior_run_retries_transient_errors_but_does_not_hide_an_outage(scratch: Path, tmp_path: Path):
    world, target = World(1), tg.InMemoryBackupTarget()
    await sealed(world, target, scratch, tmp_path)
    target.inject("download_to", unavailable(), times=2)
    assert (await ms.load_prior_run(target, RUN_1, scratch_dir=scratch, retry=RETRY_3, sleep=Sleeps())).run_id == RUN_1
    target.inject("download_to", unavailable(), times=5)
    with pytest.raises(MediaStorageUnavailable):
        await ms.load_prior_run(target, RUN_1, scratch_dir=scratch, retry=RETRY_3, sleep=Sleeps())
    assert_clean(scratch)


async def test_load_prior_run_validates_the_run_id(scratch: Path):
    with pytest.raises(RunIdError):
        await ms.load_prior_run(tg.InMemoryBackupTarget(), "../x", scratch_dir=scratch)


# --- expected_content_type (manifest helper added for this stage) ---------------------------------------------


def test_expected_content_type_follows_the_key_layout():
    aid = str(asset_id(7))
    base = f"photos/v1/{aid}/"
    assert mf.expected_content_type(mf.Role.ORIGINAL, aid, f"{base}original.jpg") == "image/jpeg"
    assert mf.expected_content_type(mf.Role.ORIGINAL, aid, f"{base}original.png") == "image/png"
    assert mf.expected_content_type(mf.Role.ORIGINAL, aid, f"{base}original.webp") == "image/webp"
    assert mf.expected_content_type(mf.Role.DISPLAY, aid, f"{base}display.jpg") == "image/jpeg"
    assert mf.expected_content_type(mf.Role.THUMBNAIL, aid, f"{base}thumb.jpg") == "image/jpeg"


@pytest.mark.parametrize(
    ("role", "suffix"),
    [
        (mf.Role.ORIGINAL, "original.gif"),
        (mf.Role.ORIGINAL, "display.jpg"),
        (mf.Role.DISPLAY, "thumb.jpg"),
        (mf.Role.THUMBNAIL, "display.jpg"),
        (mf.Role.DISPLAY, "display.png"),
    ],
)
def test_expected_content_type_refuses_a_key_that_is_not_the_roles_key(role: mf.Role, suffix: str):
    aid = str(asset_id(7))
    with pytest.raises(mf.ManifestFormatError):
        mf.expected_content_type(role, aid, f"photos/v1/{aid}/{suffix}")


def test_expected_content_type_refuses_another_assets_key():
    with pytest.raises(mf.ManifestFormatError):
        mf.expected_content_type(mf.Role.DISPLAY, str(asset_id(1)), f"photos/v1/{asset_id(2)}/display.jpg")
