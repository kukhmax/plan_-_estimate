"""Stage 14D.2I.3 — the whole restore of a sealed run: seal -> database -> READY set -> media (fake tools)."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup import restore_db as rd
from app.backup import restore_media as rm
from app.backup import restore_run as rr
from app.backup.run_id import RunIdError
from app.domain.exceptions import MediaStorageMisconfigured, MediaStorageUnavailable
from tests.test_stage14d2g_media_sync import NO_RETRY, RUN_1, RUN_2, Sleeps, World
from tests.test_stage14d2i1_restore_db import KEY_LINE, Rig, flip_byte
from tests.test_stage14d2i2_restore_media import DESTINATION, FORBIDDEN, Destination


class Chain:
    """The DB rig of 14D.2I.1 plus the destination of 14D.2I.2, wired into `restore_run`."""

    def __init__(self, tmp_path: Path) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.rig = Rig(tmp_path, World(2))
        self.destination = Destination()

    async def restore(self, run_id: str = RUN_1, **overrides: Any) -> rr.RestoreRunReport:
        await self.rig.seal()
        rig = self.rig
        options: dict[str, Any] = {
            "database": rig.database,
            "identity_file": rig.identity,
            "destination": self.destination,
            "destination_bucket": DESTINATION,
            "forbidden_buckets": FORBIDDEN,
            "scratch_dir": rig.scratch,
            "age_path": str(rig.tools / "age"),
            "age_keygen_path": str(rig.tools / "age-keygen"),
            "psql_path": str(rig.tools / "psql"),
            "connect": rig.connect,
            "retry": NO_RETRY,
            "sleep": Sleeps(),
            "db_timeout_seconds": 60.0,
            "repository_head": lambda: "0032_photo_attachments",
        }
        options.update(overrides)
        return await rr.restore_run(rig.target, run_id, **options)


@pytest.fixture
def chain(tmp_path: Path) -> Chain:
    return Chain(tmp_path)


def untouched(chain: Chain) -> bool:
    return chain.destination.calls == []


# --- the whole chain --------------------------------------------------------------------------------------------------------


async def test_a_good_run_is_restored_end_to_end(chain: Chain):
    report = await chain.restore()
    assert report.ok and report.step is rr.RunStep.DONE and report.failure is None
    assert report.database is not None and report.database.ok
    assert report.media is not None and report.media.ok and report.media.counts.restored == 6
    assert {key: obj.data for key, obj in chain.destination.inner._objects.items()} == chain.rig.world.contents
    assert chain.rig.psql_got_eof(), "the database was committed"
    assert len(chain.rig.connects) == 3, "preflight, checks, and the READY set read back from the restored database"
    assert list(chain.rig.scratch.iterdir()) == []


async def test_the_report_embeds_the_step_reports_canonically_and_secret_free(chain: Chain):
    report = await chain.restore()
    data = report.report_bytes()
    document = json.loads(data)
    assert data == mf.canonical_line(document) and data.count(b"\n") == 1
    assert document["format"] == "plan-estimate/restore-run-report/v1" and document["ok"] is True
    assert document["database"]["format"] == "plan-estimate/db-restore-report/v1"
    assert document["media"]["format"] == "plan-estimate/media-restore-report/v1"
    text = data.decode()
    for secret in (str(chain.rig.identity), "s3cretpassword", "127.0.0.1", DESTINATION, KEY_LINE, "photos/v1"):
        assert secret not in text
    assert report.report_bytes() == data


async def test_the_media_step_gets_the_ready_set_of_the_restored_database(chain: Chain):
    """If the database no longer agrees with the manifest at the moment the media step starts, media is refused."""
    await chain.rig.seal()
    original = chain.rig.connect

    async def connect(dsn: str, **kwargs: Any) -> Any:
        if len(chain.rig.connects) == 2:  # the third connection reads the READY set back
            chain.rig.ready_rows = chain.rig.ready_rows[:-1]
        return await original(dsn, **kwargs)

    report = await chain.restore(connect=connect)
    assert report.database is not None and report.database.ok
    assert report.media is not None and report.media.preflight is rm.Preflight.MANIFEST_DB_MISMATCH
    assert not report.ok and report.step is rr.RunStep.MEDIA
    assert untouched(chain), "the association guard fires before the destination is even listed"


async def test_an_invalid_run_id_is_refused(chain: Chain):
    with pytest.raises(RunIdError):
        await chain.restore(run_id="../x")


# --- each step stops the chain ----------------------------------------------------------------------------------------------------


async def test_a_run_without_a_seal_stops_at_the_first_step(chain: Chain):
    await chain.rig.seal()
    del chain.rig.target.objects[mf.complete_key(RUN_1)]
    report = await chain.restore()
    assert (report.step, report.failure) == (rr.RunStep.SEAL, rr.ChainFailure.SEAL_MISSING) and not report.ok
    assert report.database is None and report.media is None
    assert chain.rig.connects == [] and chain.rig.seen("age.argv") is None and untouched(chain)


async def test_an_unknown_run_is_a_missing_seal(chain: Chain):
    report = await chain.restore(run_id=RUN_2)
    assert report.failure is rr.ChainFailure.SEAL_MISSING and chain.rig.connects == []


async def test_a_seal_that_does_not_match_the_manifest_stops_the_chain(chain: Chain):
    await chain.rig.seal()
    chain.rig.target.objects[mf.manifest_key(RUN_1)] += b" "
    report = await chain.restore()
    assert (report.step, report.failure) == (rr.RunStep.SEAL, rr.ChainFailure.SEAL_INVALID)
    assert chain.rig.connects == [] and untouched(chain)


async def test_storage_failures_while_reading_the_seal(chain: Chain):
    await chain.rig.seal()
    chain.rig.target.inject("download_to", MediaStorageUnavailable("x", error_code="Throttled", http_status=503))
    assert (await chain.restore()).failure is rr.ChainFailure.STORAGE_UNAVAILABLE
    chain.rig.target.inject("download_to", MediaStorageMisconfigured("x", error_code="AccessDenied", http_status=403))
    assert (await chain.restore()).failure is rr.ChainFailure.STORAGE_MISCONFIGURED
    assert untouched(chain)


async def test_a_database_failure_stops_before_any_media_is_touched(chain: Chain):
    chain.rig.age(exit=1, stderr="age: error: boom\n")
    report = await chain.restore()
    assert (report.step, report.failure) == (rr.RunStep.DATABASE, None) and not report.ok
    assert report.database is not None and report.database.failure is rd.RestoreFailure.DECRYPT_FAILED
    assert report.media is None and untouched(chain)
    assert not chain.rig.psql_got_eof(), "nothing was committed either"


async def test_an_unsafe_database_target_stops_the_chain_at_its_guard(chain: Chain):
    chain.rig.relations = 4
    report = await chain.restore()
    assert report.database is not None and report.database.failure is rd.RestoreFailure.DATABASE_NOT_EMPTY
    assert report.media is None and untouched(chain)


async def test_a_database_that_cannot_give_its_ready_set_back_stops_before_media(chain: Chain):
    await chain.rig.seal()
    original = chain.rig.connect

    async def connect(dsn: str, **kwargs: Any) -> Any:
        if len(chain.rig.connects) == 2:
            raise OSError("connection reset")
        return await original(dsn, **kwargs)

    report = await chain.restore(connect=connect)
    assert (report.step, report.failure) == (rr.RunStep.READY_SET, rr.ChainFailure.READY_SET_UNREADABLE)
    assert report.database is not None and report.database.ok and report.media is None and untouched(chain)


async def test_a_media_preflight_failure_leaves_the_database_restored_and_says_so(chain: Chain):
    report = await chain.restore(destination_bucket="plan-estimate-media-prod")
    assert (report.step, report.failure) == (rr.RunStep.MEDIA, None) and not report.ok
    assert report.database is not None and report.database.ok and chain.rig.psql_got_eof()
    assert report.media is not None and report.media.preflight is rm.Preflight.DESTINATION_UNSAFE
    assert untouched(chain)


async def test_media_problems_are_reported_in_the_combined_report(chain: Chain):
    await chain.rig.seal()
    key = min(chain.rig.world.contents)
    chain.rig.target.objects[key] = flip_byte(chain.rig.target.objects[key], 0)
    report = await chain.restore()
    assert report.step is rr.RunStep.MEDIA and not report.ok
    assert report.media is not None and [p.code for p in report.media.object_problems] == [rm.ObjectProblemCode.BACKUP_SHA_MISMATCH]
    document = json.loads(report.report_bytes())
    assert document["media"]["object_problem_totals"] == {"BACKUP_SHA_MISMATCH": 1} and document["ok"] is False


async def test_options_reach_the_steps(tmp_path: Path):
    foreign = "photos/v1/00000000-0000-4000-8000-0000000000aa/original.jpg"
    blocked = Chain(tmp_path / "a")
    blocked.destination.seed(foreign, b"newer upload")
    report = await blocked.restore()
    assert report.media is not None and report.media.preflight is rm.Preflight.FOREIGN_OBJECTS_PRESENT and not report.ok

    allowed = Chain(tmp_path / "b")
    allowed.destination.seed(foreign, b"newer upload")
    report = await allowed.restore(allow_foreign_objects=True)
    assert report.ok and report.media is not None and report.media.counts.foreign_objects == 1

    new_bucket = Chain(tmp_path / "c")
    assert (await new_bucket.restore(destination_bucket="plan-estimate-media-new", allow_non_drill=True)).ok


async def test_the_callers_forbidden_buckets_reach_the_media_guard(chain: Chain):
    report = await chain.restore(
        destination_bucket="plan-estimate-media-drill-extra", forbidden_buckets=(*FORBIDDEN, "plan-estimate-media-drill-extra")
    )
    assert report.media is not None and report.media.preflight is rm.Preflight.DESTINATION_UNSAFE and untouched(chain)


def test_ok_needs_every_step_to_have_succeeded():
    db_ok = rd.DbRestoreReport(RUN_1, rd.RestoreStep.DONE, None)
    media_ok = rm.MediaRestoreReport(RUN_1, None, (), None, rm.RestoreCounts(objects_total=1, restored=1))
    assert rr.RestoreRunReport(RUN_1, rr.RunStep.DONE, None, db_ok, media_ok).ok
    assert not rr.RestoreRunReport(RUN_1, rr.RunStep.MEDIA, None, db_ok, media_ok).ok
    assert not rr.RestoreRunReport(RUN_1, rr.RunStep.DONE, rr.ChainFailure.SEAL_INVALID, db_ok, media_ok).ok
    assert not rr.RestoreRunReport(RUN_1, rr.RunStep.DONE, None, None, media_ok).ok
    assert not rr.RestoreRunReport(RUN_1, rr.RunStep.DONE, None, db_ok, None).ok
    db_bad = rd.DbRestoreReport(RUN_1, rd.RestoreStep.LOAD, rd.RestoreFailure.PSQL_FAILED)
    assert not rr.RestoreRunReport(RUN_1, rr.RunStep.DONE, None, db_bad, media_ok).ok


# --- phases (14D.5: the integrity checker runs between the two halves) ---------------------------------------------------------------


async def test_the_database_phase_restores_the_database_and_touches_no_media(chain: Chain):
    report = await chain.restore(phase=rr.RestorePhase.DATABASE)
    assert report.ok and report.step is rr.RunStep.DONE and report.phase is rr.RestorePhase.DATABASE
    assert report.database is not None and report.database.ok and report.media is None
    assert chain.rig.psql_got_eof() and untouched(chain)
    assert len(chain.rig.connects) == 2, "preflight and checks only: the READY set is not read back in this phase"
    document = json.loads(report.report_bytes())
    assert document["phase"] == "database" and document["ok"] is True and document["media"] is None


async def test_the_media_phase_restores_into_an_already_restored_database(chain: Chain):
    report = await chain.restore(phase=rr.RestorePhase.MEDIA)
    assert report.ok and report.phase is rr.RestorePhase.MEDIA and report.database is None
    assert report.media is not None and report.media.counts.restored == 6
    assert {key: obj.data for key, obj in chain.destination.inner._objects.items()} == chain.rig.world.contents
    assert not chain.rig.psql_got_eof(), "no database restore ran in the media phase"
    assert len(chain.rig.connects) == 1, "only the READY set is read from the existing database"
    assert json.loads(report.report_bytes())["database"] is None


async def test_the_two_phases_in_sequence_equal_the_whole_chain(chain: Chain):
    first = await chain.restore(phase=rr.RestorePhase.DATABASE)
    assert first.ok and untouched(chain)
    second = await chain.restore(phase=rr.RestorePhase.MEDIA)
    assert second.ok and second.media is not None and second.media.counts.restored == 6
    assert {key: obj.data for key, obj in chain.destination.inner._objects.items()} == chain.rig.world.contents


async def test_the_media_phase_refuses_a_database_that_is_not_a_scratch_database(chain: Chain):
    import dataclasses

    report = await chain.restore(phase=rr.RestorePhase.MEDIA, database=dataclasses.replace(chain.rig.database, database="plan_estimate"))
    assert (report.step, report.failure) == (rr.RunStep.DATABASE, rr.ChainFailure.DATABASE_UNSAFE) and not report.ok
    assert chain.rig.connects == [] and untouched(chain)


async def test_the_media_phase_refuses_a_database_that_does_not_match_the_manifest(chain: Chain):
    await chain.rig.seal()
    chain.rig.ready_rows = chain.rig.ready_rows[:-1]
    report = await chain.restore(phase=rr.RestorePhase.MEDIA)
    assert report.media is not None and report.media.preflight is rm.Preflight.MANIFEST_DB_MISMATCH
    assert not report.ok and report.step is rr.RunStep.MEDIA and untouched(chain)


async def test_a_failing_database_phase_is_not_ok_and_stops(chain: Chain):
    chain.rig.age(exit=1, stderr="age: error: boom\n")
    report = await chain.restore(phase=rr.RestorePhase.DATABASE)
    assert (report.step, report.failure) == (rr.RunStep.DATABASE, None) and not report.ok and untouched(chain)
    assert report.phase is rr.RestorePhase.DATABASE and json.loads(report.report_bytes())["phase"] == "database"


async def test_the_media_phase_needs_a_seal_like_every_other(chain: Chain):
    report = await chain.restore(phase=rr.RestorePhase.MEDIA, run_id=RUN_2)
    assert (report.step, report.failure) == (rr.RunStep.SEAL, rr.ChainFailure.SEAL_MISSING)
    assert report.phase is rr.RestorePhase.MEDIA and untouched(chain)


def test_ok_follows_the_phase():
    db_ok = rd.DbRestoreReport(RUN_1, rd.RestoreStep.DONE, None)
    db_bad = rd.DbRestoreReport(RUN_1, rd.RestoreStep.LOAD, rd.RestoreFailure.DECRYPT_FAILED)
    media_ok = rm.MediaRestoreReport(RUN_1, None, (), None, rm.RestoreCounts(objects_total=1, restored=1))
    media_bad = rm.MediaRestoreReport(RUN_1, rm.Preflight.DESTINATION_UNSAFE, (), None, rm.RestoreCounts())
    phase = rr.RestorePhase
    done = rr.RunStep.DONE

    def report(p, database, media, step=done, failure=None):
        return rr.RestoreRunReport(RUN_1, step, failure, database, media, p)

    assert report(phase.DATABASE, db_ok, None).ok and report(phase.MEDIA, None, media_ok).ok and report(phase.ALL, db_ok, media_ok).ok
    assert not report(phase.DATABASE, db_bad, None).ok and not report(phase.DATABASE, None, None).ok
    assert not report(phase.MEDIA, None, media_bad).ok and not report(phase.MEDIA, None, None).ok
    assert not report(phase.DATABASE, db_ok, media_ok).ok, "a phase that skips media must not carry a media report"
    assert not report(phase.MEDIA, db_ok, media_ok).ok, "a phase that skips the database must not carry a database report"
    assert not report(phase.ALL, db_ok, None).ok and not report(phase.ALL, None, media_ok).ok
    assert not report(phase.DATABASE, db_ok, None, step=rr.RunStep.DATABASE).ok
    assert not report(phase.DATABASE, db_ok, None, failure=rr.ChainFailure.SEAL_INVALID).ok
