"""Stage 14D.2H — verification of a sealed run in the backup target."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup import target as tg
from app.backup import verify as vf
from app.backup.run_id import RunIdError
from app.core.db_dump_encryption import AgeRecipientError
from app.domain.exceptions import (
    MediaObjectNotFound,
    MediaStorageMisconfigured,
)
from tests.test_stage14d2e_manifest import RECIPIENT_A, RECIPIENT_B
from tests.test_stage14d2g_media_sync import (
    NO_RETRY,
    RETRY_3,
    RUN_1,
    RUN_2,
    Sleeps,
    World,
    assert_clean,
    publish,
    run_sync,
    sealed,
    unavailable,
)

NOW_TEXT = "2026-10-04T13:00:00Z"
OTHER_RECIPIENT = "age1" + "z" * 58


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def published(world: World, scratch: Path, tmp_path: Path, *, runs: int = 1) -> tg.InMemoryBackupTarget:
    target = tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path, RUN_1)
    if runs == 2:
        result = await run_sync(world, target, scratch, run_id=RUN_2, prior=prior)
        await publish(world, target, result, scratch, tmp_path, RUN_2)
    target.calls.clear()
    return target


async def verify(
    target: Any, scratch: Path, *, run_id: str = RUN_1, mode: vf.VerifyMode = vf.VerifyMode.FULL, **kwargs: Any
) -> vf.VerifyReport:
    kwargs.setdefault("retry", NO_RETRY)
    return await vf.verify_run_in_target(
        target,
        run_id,
        scratch_dir=scratch,
        mode=mode,
        sleep=Sleeps(),
        clock=lambda: datetime(2026, 10, 4, 13, 0, tzinfo=UTC),
        **kwargs,
    )


def flip(data: bytes) -> bytes:
    return bytes([data[0] ^ 0xFF]) + data[1:]


# --- a good run ----------------------------------------------------------------------------------------


async def test_a_good_run_passes_in_full_mode(scratch: Path, tmp_path: Path):
    world = World(3)
    target = await published(world, scratch, tmp_path)
    report = await verify(target, scratch)
    assert report.ok and report.run_problems == () and report.object_problems == () and report.aborted is None
    assert report.dump_checked == "sha256" and report.mode is vf.VerifyMode.FULL and report.verified_at == NOW_TEXT
    total = sum(len(data) for data in world.contents.values())
    assert report.counts == vf.VerifyCounts(
        objects_total=9, size_checked=9, sha_checked=9, bytes_hashed=total, inherited_lines=0, downloaded_lines=9
    )
    assert_clean(scratch)


async def test_quick_mode_reads_documents_and_heads_only(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path)
    report = await verify(target, scratch, mode=vf.VerifyMode.QUICK)
    assert report.ok and report.dump_checked == "size"
    assert report.counts.size_checked == 6 and report.counts.sha_checked == 0 and report.counts.bytes_hashed == 0
    downloads = [key for op, key in target.calls if op == "download_to"]
    assert sorted(downloads) == sorted([mf.complete_key(RUN_1), mf.manifest_key(RUN_1)])
    assert sum(1 for op, _ in target.calls if op == "head") == 7, "the dump and six objects"


async def test_full_mode_does_not_trust_inherited_provenance(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path, runs=2)
    target.objects[world.key_of(0, "display")] = flip(world.contents[world.key_of(0, "display")])
    report = await verify(target, scratch, run_id=RUN_2)
    assert report.counts.inherited_lines == 6 and report.counts.downloaded_lines == 0
    assert [(p.role, p.code) for p in report.object_problems] == [(mf.Role.DISPLAY, vf.ObjectProblemCode.SHA_MISMATCH)]
    quick = await verify(target, scratch, run_id=RUN_2, mode=vf.VerifyMode.QUICK)
    assert quick.ok, "quick mode cannot see a same-size change: it is documented to rely on the seal"


async def test_the_reader_port_and_the_run_never_write(scratch: Path, tmp_path: Path):
    assert {name for name in dir(vf.BackupReader) if not name.startswith("_")} == {"head", "download_to"}
    target = await published(World(1), scratch, tmp_path)
    await verify(target, scratch)
    assert {op for op, _ in target.calls} <= {"head", "download_to"}


# --- the seal ----------------------------------------------------------------------------------------------


async def test_a_run_without_complete_json_is_incomplete(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    del target.objects[mf.complete_key(RUN_1)]
    report = await verify(target, scratch)
    assert not report.ok and report.run_problems == (vf.RunProblem.SEAL_MISSING,) and report.counts.objects_total == 0
    assert_clean(scratch)


async def test_an_unknown_run_reports_a_missing_seal(scratch: Path):
    report = await verify(tg.InMemoryBackupTarget(), scratch, run_id=RUN_2)
    assert report.run_problems == (vf.RunProblem.SEAL_MISSING,) and not report.ok


async def test_a_missing_manifest_is_reported(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    del target.objects[mf.manifest_key(RUN_1)]
    assert (await verify(target, scratch)).run_problems == (vf.RunProblem.MANIFEST_MISSING,)


@pytest.mark.parametrize("which", ["manifest_appended", "manifest_flipped", "complete_garbage", "complete_count_changed"])
async def test_a_seal_that_does_not_match_the_manifest_is_invalid(scratch: Path, tmp_path: Path, which: str):
    target = await published(World(2), scratch, tmp_path)
    if which == "manifest_appended":
        target.objects[mf.manifest_key(RUN_1)] += b" "
    elif which == "manifest_flipped":
        target.objects[mf.manifest_key(RUN_1)] = flip(target.objects[mf.manifest_key(RUN_1)])
    elif which == "complete_garbage":
        target.objects[mf.complete_key(RUN_1)] = b"not json\n"
    else:
        document = json.loads(target.objects[mf.complete_key(RUN_1)])
        document["objects"] += 1
        target.objects[mf.complete_key(RUN_1)] = mf.canonical_line(document)
    report = await verify(target, scratch)
    assert report.run_problems == (vf.RunProblem.SEAL_INVALID,) and not report.ok
    assert report.counts.objects_total == 0, "nothing in an unproven manifest is trusted"


async def test_documents_stored_under_another_run_id_are_invalid(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    target.objects[mf.complete_key(RUN_2)] = target.objects[mf.complete_key(RUN_1)]
    target.objects[mf.manifest_key(RUN_2)] = target.objects[mf.manifest_key(RUN_1)]
    assert (await verify(target, scratch, run_id=RUN_2)).run_problems == (vf.RunProblem.SEAL_INVALID,)


# --- recipients ------------------------------------------------------------------------------------------------


async def test_expected_recipients_must_all_be_in_the_manifest(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    assert (await verify(target, scratch, expected_recipients=[RECIPIENT_A, RECIPIENT_B])).ok
    assert (await verify(target, scratch, expected_recipients=[RECIPIENT_B])).ok, "a subset is fine"
    report = await verify(target, scratch, expected_recipients=[RECIPIENT_A, OTHER_RECIPIENT])
    assert report.run_problems == (vf.RunProblem.RECIPIENTS_MISMATCH,)
    assert report.counts.objects_total == 3, "the other checks still run"


async def test_a_private_key_is_never_accepted_as_an_expected_recipient(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    secret = "AGE-SECRET-KEY-1" + "Q" * 50
    with pytest.raises(AgeRecipientError) as excinfo:
        await verify(target, scratch, expected_recipients=[secret])
    assert secret not in str(excinfo.value)
    assert target.calls == [], "refused before anything is read"


# --- the dump ---------------------------------------------------------------------------------------------------


async def test_a_missing_dump_is_reported_and_objects_are_still_checked(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    del target.objects[mf.db_dump_key(RUN_1)]
    report = await verify(target, scratch)
    assert report.run_problems == (vf.RunProblem.DUMP_MISSING,) and report.dump_checked == "none"
    assert report.counts.sha_checked == 3


async def test_a_dump_of_another_size_is_reported_in_both_modes(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    target.objects[mf.db_dump_key(RUN_1)] += b"x"
    for mode in vf.VerifyMode:
        assert (await verify(target, scratch, mode=mode)).run_problems == (vf.RunProblem.DUMP_SIZE_MISMATCH,)


async def test_a_dump_with_changed_bytes_is_found_by_the_full_mode_only(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    target.objects[mf.db_dump_key(RUN_1)] = flip(target.objects[mf.db_dump_key(RUN_1)])
    assert (await verify(target, scratch, mode=vf.VerifyMode.QUICK)).ok
    full = await verify(target, scratch)
    assert full.run_problems == (vf.RunProblem.DUMP_SHA_MISMATCH,) and full.dump_checked == "sha256"


# --- objects ----------------------------------------------------------------------------------------------------


async def test_a_missing_object_is_reported_with_its_asset_and_role(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path)
    key = world.key_of(1, "thumbnail")
    del target.objects[key]
    for mode in vf.VerifyMode:
        report = await verify(target, scratch, mode=mode)
        assert report.object_problems == (
            vf.ObjectProblem(str(world.assets[1].asset_id), mf.Role.THUMBNAIL, vf.ObjectProblemCode.MISSING_OBJECT),
        )
        assert report.counts.size_checked == 5 and not report.ok


async def test_an_object_of_another_size_is_reported_in_both_modes(scratch: Path, tmp_path: Path):
    world = World(1)
    target = await published(world, scratch, tmp_path)
    target.objects[world.key_of(0, "original")] += b"!"
    for mode in vf.VerifyMode:
        report = await verify(target, scratch, mode=mode)
        assert [p.code for p in report.object_problems] == [vf.ObjectProblemCode.SIZE_MISMATCH]


async def test_changed_bytes_of_the_same_size_are_found_by_the_full_mode(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path)
    key = world.key_of(0, "original")
    target.objects[key] = flip(world.contents[key])
    assert (await verify(target, scratch, mode=vf.VerifyMode.QUICK)).ok
    report = await verify(target, scratch)
    assert [(p.asset_id, p.role, p.code) for p in report.object_problems] == [
        (str(world.assets[0].asset_id), mf.Role.ORIGINAL, vf.ObjectProblemCode.SHA_MISMATCH)
    ]
    assert report.counts.sha_checked == 6, "a mismatching object was hashed too"


async def test_every_problem_is_listed_not_only_the_first(scratch: Path, tmp_path: Path):
    world = World(3)
    target = await published(world, scratch, tmp_path)
    del target.objects[world.key_of(0, "display")]
    target.objects[world.key_of(1, "thumbnail")] += b"x"
    target.objects[world.key_of(2, "original")] = flip(world.contents[world.key_of(2, "original")])
    report = await verify(target, scratch)
    assert sorted(p.code.value for p in report.object_problems) == ["MISSING_OBJECT", "SHA_MISMATCH", "SIZE_MISMATCH"]


async def test_an_object_that_vanishes_between_head_and_download_is_missing(scratch: Path, tmp_path: Path):
    world = World(1)
    target = await published(world, scratch, tmp_path)
    target.inject("download_to", MediaObjectNotFound("gone"), after=3)  # two documents and the dump come first
    report = await verify(target, scratch)
    assert [p.code for p in report.object_problems] == [vf.ObjectProblemCode.MISSING_OBJECT]


async def test_other_assets_are_unaffected_by_one_bad_object(scratch: Path, tmp_path: Path):
    world = World(3)
    target = await published(world, scratch, tmp_path)
    del target.objects[world.key_of(0, "original")]
    report = await verify(target, scratch)
    assert len(report.object_problems) == 1 and report.counts.sha_checked == 8


# --- storage failures -------------------------------------------------------------------------------------------


async def test_transient_errors_are_retried(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    target.inject("head", unavailable(), times=2)
    target.inject("download_to", unavailable(), times=2, after=1)
    sleeps = Sleeps()
    report = await vf.verify_run_in_target(target, RUN_1, scratch_dir=scratch, retry=RETRY_3, sleep=sleeps)
    assert report.ok and sleeps.values


async def test_an_object_that_stays_unavailable_is_a_problem_of_that_object(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path)
    target.inject("head", unavailable(), after=1)  # the dump's HEAD succeeds, the first object's fails
    report = await verify(target, scratch)
    assert [p.code for p in report.object_problems] == [vf.ObjectProblemCode.UNAVAILABLE]
    assert report.aborted is None and report.counts.size_checked == 5


async def test_a_streak_of_unavailable_objects_aborts(scratch: Path, tmp_path: Path):
    target = await published(World(3), scratch, tmp_path)
    target.inject("head", unavailable(), times=100, after=1)
    report = await verify(target, scratch, max_consecutive_unavailable=3)
    assert report.aborted is vf.AbortReason.STORAGE_UNAVAILABLE and len(report.object_problems) == 3 and not report.ok
    assert sum(1 for op, _ in target.calls if op == "head") == 4, "the dump and three objects, then nothing"


async def test_the_streak_resets_after_a_success(scratch: Path, tmp_path: Path):
    target = await published(World(2), scratch, tmp_path)
    target.inject("head", unavailable(), after=1)
    target.inject("head", unavailable(), after=2)
    report = await verify(target, scratch, max_consecutive_unavailable=2)
    assert report.aborted is None and len(report.object_problems) == 2


async def test_a_misconfigured_store_aborts_at_once(scratch: Path, tmp_path: Path):
    target = await published(World(2), scratch, tmp_path)
    target.inject("head", MediaStorageMisconfigured("denied", error_code="BucketNotFound", http_status=404))
    report = await verify(target, scratch)
    assert report.aborted is vf.AbortReason.STORAGE_MISCONFIGURED and report.object_problems == () and not report.ok
    target2 = await published(World(2), scratch, tmp_path)
    target2.inject("download_to", MediaStorageMisconfigured("denied", http_status=403))
    report2 = await verify(target2, scratch)
    assert report2.aborted is vf.AbortReason.STORAGE_MISCONFIGURED and report2.counts.objects_total == 0
    assert_clean(scratch)


async def test_an_unavailable_store_while_reading_the_seal_aborts(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    target.inject("download_to", unavailable())
    report = await verify(target, scratch)
    assert report.aborted is vf.AbortReason.STORAGE_UNAVAILABLE and report.run_problems == ()


async def test_an_unavailable_store_while_checking_the_dump_aborts(scratch: Path, tmp_path: Path):
    target = await published(World(1), scratch, tmp_path)
    target.inject("head", unavailable())
    report = await verify(target, scratch)
    assert report.aborted is vf.AbortReason.STORAGE_UNAVAILABLE and report.counts.sha_checked == 0


# --- hygiene --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("error", [RuntimeError("boom"), asyncio.CancelledError()])
async def test_unexpected_errors_and_cancellation_propagate_and_clean_up(scratch: Path, tmp_path: Path, error: BaseException):
    target = await published(World(1), scratch, tmp_path)
    target.inject("download_to", error, after=3)  # type: ignore[arg-type]  # fails on the first object
    with pytest.raises(type(error)):
        await verify(target, scratch)
    assert_clean(scratch)


async def test_scratch_is_clean_after_every_outcome(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path)
    await verify(target, scratch)
    target.objects[world.key_of(0, "original")] = flip(world.contents[world.key_of(0, "original")])
    await verify(target, scratch)
    del target.objects[mf.db_dump_key(RUN_1)]
    await verify(target, scratch)
    assert_clean(scratch)


def test_input_validation(scratch: Path):
    with pytest.raises(RunIdError):
        asyncio.run(vf.verify_run_in_target(tg.InMemoryBackupTarget(), "../x", scratch_dir=scratch))
    with pytest.raises(ValueError):
        asyncio.run(vf.verify_run_in_target(tg.InMemoryBackupTarget(), RUN_1, scratch_dir=scratch, max_consecutive_unavailable=0))


# --- report ----------------------------------------------------------------------------------------------------------


async def test_the_report_is_canonical_deterministic_and_secret_free(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path)
    key = world.key_of(0, "original")
    target.objects[key] = flip(world.contents[key])
    report = await verify(target, scratch)
    data = report.report_bytes()
    document = json.loads(data)
    assert data.endswith(b"\n") and data.count(b"\n") == 1 and data == mf.canonical_line(document)
    assert document["format"] == "plan-estimate/verify-report/v1" and document["ok"] is False
    assert document["object_problems"] == [
        {"asset_id": str(world.assets[0].asset_id), "role": "original", "code": "SHA_MISMATCH"}
    ]
    assert document["object_problem_totals"] == {"SHA_MISMATCH": 1} and document["object_problems_omitted"] == 0
    text = data.decode()
    assert "photos/v1" not in text and all(sha(content) not in text for content in world.contents.values())
    assert RECIPIENT_A not in text
    assert report.report_bytes() == data


def test_the_report_lists_a_bounded_number_of_problems():
    problems = tuple(
        vf.ObjectProblem(f"00000000-0000-4000-8000-{n:012d}", mf.Role.ORIGINAL, vf.ObjectProblemCode.MISSING_OBJECT)
        for n in range(vf.MAX_LISTED_PROBLEMS + 50)
    )
    report = vf.VerifyReport(RUN_1, vf.VerifyMode.QUICK, NOW_TEXT, (), problems, None, vf.VerifyCounts(), "size")
    document = json.loads(report.report_bytes())
    assert len(document["object_problems"]) == vf.MAX_LISTED_PROBLEMS and document["object_problems_omitted"] == 50
    assert document["object_problem_totals"] == {"MISSING_OBJECT": vf.MAX_LISTED_PROBLEMS + 50}


def test_ok_requires_no_problem_of_any_kind():
    base: dict[str, Any] = {
        "run_id": RUN_1, "mode": vf.VerifyMode.FULL, "verified_at": NOW_TEXT, "run_problems": (), "object_problems": (),
        "aborted": None, "counts": vf.VerifyCounts(), "dump_checked": "sha256",
    }
    assert vf.VerifyReport(**base).ok
    assert not vf.VerifyReport(**{**base, "run_problems": (vf.RunProblem.DUMP_MISSING,)}).ok
    assert not vf.VerifyReport(**{**base, "aborted": vf.AbortReason.STORAGE_UNAVAILABLE}).ok
    problem = vf.ObjectProblem(str(World(1).assets[0].asset_id), mf.Role.DISPLAY, vf.ObjectProblemCode.SIZE_MISMATCH)
    assert not vf.VerifyReport(**{**base, "object_problems": (problem,)}).ok
