"""Stage 14D.2J.2 — `upload_run`: a promoted local run into the backup target, on real files and in-memory stores."""

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.backup import manifest as mf
from app.backup import run_sidecars as sc
from app.backup import target as tg
from app.backup import upload_run as up
from app.backup import workspace as ws
from app.backup.evidence import (
    ArtifactFacts,
    CompleteRunEvidence,
    DatabaseFacts,
    Diagnostics,
    DumpFacts,
    SnapshotFacts,
)
from app.backup.media_sync import load_prior_run
from app.core.db_dump_encryption import ENCRYPTED_DUMP_NAME
from app.domain.exceptions import MediaStorageUnavailable
from app.domain.services.media_backup_ready_set import ReadyAsset, ready_set_digest
from tests.test_stage14d2g_media_sync import Source, World

RUN_1 = "20261004T120000Z-0123abcd"
RUN_2 = "20261005T120000Z-4567abcd"
SOURCE_BUCKET, TARGET_BUCKET = "plan-estimate-media-drill", "plan-estimate-backup-drill"
COMMIT = "a" * 40
RECIPIENT = "age1" + "q" * 58
HEAD = "0032_photo_attachments"
T0 = datetime(2026, 10, 4, 11, 0, tzinfo=UTC)
NO_RETRY = tg.RetryPolicy(max_attempts=1, base_delay=0.0)
ARTIFACT = b"age-encryption.org/v1\nCIPHERTEXT-OF-THE-DUMP"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def data_root(tmp_path: Path) -> ws.BackupDataRoot:
    path = tmp_path / "data"
    path.mkdir(mode=0o700)
    root = ws.BackupDataRoot(path)
    root.prepare()
    return root


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


def promote_run(
    root: ws.BackupDataRoot,
    run_id: str,
    assets: list[ReadyAsset],
    *,
    artifact: bytes = ARTIFACT,
    recipients: tuple[str, ...] = (RECIPIENT,),
    pending: int = 1,
    failed: int = 2,
) -> Path:
    """What `db-dump` leaves behind: artifact, sidecars and local evidence, promoted."""
    run = root.create_run(run_id)
    (run.directory / ENCRYPTED_DUMP_NAME).write_bytes(artifact)
    (run.directory / ENCRYPTED_DUMP_NAME).chmod(0o600)
    digest = ready_set_digest(assets)
    root.write_run_file(run_id, sc.READY_ASSETS_NAME, sc.ready_assets_bytes(assets))
    root.write_run_file(run_id, sc.RECIPIENTS_NAME, sc.recipients_bytes(recipients))
    at = T0 + timedelta(minutes=int(run_id[9:11]) % 7)
    evidence = CompleteRunEvidence(
        run_id=run_id,
        started_at=at,
        snapshot_exported_at=at + timedelta(seconds=1),
        dump_completed_at=at + timedelta(seconds=2),
        completed_at=at + timedelta(seconds=3),
        database=DatabaseFacts(
            name="plan_estimate",
            server_version="16.15",
            server_version_num=160015,
            alembic_revision=HEAD,
            expected_alembic_head=HEAD,
            photo_asset_status_counts={"FAILED": failed, "PENDING": pending, "READY": digest.ready_count},
        ),
        snapshot=SnapshotFacts(ready_count=digest.ready_count, ready_set_sha256=digest.ready_set_sha256),
        dump=DumpFacts(pg_dump_version="pg_dump (PostgreSQL) 16.15", plaintext_sha256=sha(b"plain"), plaintext_size=5),
        artifact=ArtifactFacts(sha256=sha(artifact), size=len(artifact), age_version="v1.3.2", recipient_count=len(recipients)),
        diagnostics=Diagnostics(snapshot_id="00000003-0000001B-1", session_tag="pe-snapshot-0123456789ab"),
    )
    root.write_run_evidence(run_id, evidence.to_canonical_json())
    return root.promote(run_id)


async def do_upload(root, run_id, world, target, scratch, *, source=None, **kwargs) -> up.UploadReport:
    return await up.upload_run(
        root,
        run_id,
        source=source or world.source,
        target=target,
        reader=target,
        source_name="r2-drill",
        source_bucket=SOURCE_BUCKET,
        target_bucket=TARGET_BUCKET,
        tool_commit=COMMIT,
        scratch_dir=scratch,
        retry=NO_RETRY,
        sleep=_no_sleep,
        **kwargs,
    )


async def _no_sleep(seconds: float) -> None:
    return None


def sealed(target: tg.InMemoryBackupTarget, run_id: str) -> bool:
    return mf.complete_key(run_id) in target.objects


# --- success ----------------------------------------------------------------------------------------------------------


async def test_a_promoted_run_is_published_and_leaves_counts_only_evidence(data_root, scratch):
    world, target = World(3), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.ok and report.published and not report.adopted and report.step is up.UploadStep.DONE
    assert report.objects == 9 and report.ready_assets == 3 and report.prior_run_id is None
    verified = await load_prior_run(target, RUN_1, scratch_dir=scratch)
    header = verified.manifest.header
    assert header.db_dump.recipients == (RECIPIENT,) and header.db_dump.encrypted_sha256 == sha(ARTIFACT)
    assert header.db_dump.alembic_head == HEAD and header.tool_commit == COMMIT
    assert (header.source.storage_name, header.source.bucket, header.target.bucket) == ("r2-drill", SOURCE_BUCKET, TARGET_BUCKET)
    assert (verified.manifest.summary.skipped_pending, verified.manifest.summary.skipped_failed) == (1, 2)
    assert target.objects[mf.db_dump_key(RUN_1)] == ARTIFACT
    assert data_root.published_run_ids() == [RUN_1]
    evidence = json.loads((data_root.path / "evidence" / f"{RUN_1}.published.json").read_bytes())
    assert evidence["format"] == up.PUBLISHED_FORMAT and evidence["objects"] == 9 and evidence["ready_assets"] == 3
    assert oct((data_root.path / "evidence" / f"{RUN_1}.published.json").stat().st_mode & 0o777) == "0o600"


async def test_the_local_run_is_left_untouched(data_root, scratch):
    world, target = World(2), tg.InMemoryBackupTarget()
    promoted = promote_run(data_root, RUN_1, world.assets)
    before = {p.name: p.read_bytes() for p in promoted.iterdir()}
    await do_upload(data_root, RUN_1, world, target, scratch)
    assert {p.name: p.read_bytes() for p in promoted.iterdir()} == before
    assert list(scratch.iterdir()) == []  # no scratch left behind


async def test_the_next_run_inherits_from_the_newest_published_one(data_root, scratch):
    world, target = World(2), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    await do_upload(data_root, RUN_1, world, target, scratch)
    first_downloads = len(world.source.downloads())
    promote_run(data_root, RUN_2, world.assets)
    report = await do_upload(data_root, RUN_2, world, target, scratch)
    assert report.ok and report.prior_run_id == RUN_1
    assert len(world.source.downloads()) == first_downloads  # nothing downloaded again: provenance inherited
    verified = await load_prior_run(target, RUN_2, scratch_dir=scratch)
    assert {obj.sha_provenance for obj in verified.manifest.objects} == {mf.inherited_provenance(RUN_1)}


async def test_prior_none_downloads_and_compares_everything_again(data_root, scratch):
    world, target = World(2), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    await do_upload(data_root, RUN_1, world, target, scratch)
    before = len(world.source.downloads())
    promote_run(data_root, RUN_2, world.assets)
    report = await do_upload(data_root, RUN_2, world, target, scratch, prior=None)
    assert report.ok and report.prior_run_id is None and len(world.source.downloads()) == before + 6


async def test_an_empty_ready_set_is_a_valid_run(data_root, scratch):
    world, target = World(0), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, [])
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.ok and report.objects == 0 and report.ready_assets == 0 and sealed(target, RUN_1)


# --- repeating ------------------------------------------------------------------------------------------------------------


async def test_a_published_run_is_not_uploaded_twice(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    await do_upload(data_root, RUN_1, world, target, scratch)
    calls = len(target.calls)
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.ALREADY_PUBLISHED and not report.ok and len(target.calls) == calls


async def test_a_sealed_run_without_local_evidence_is_adopted_not_republished(data_root, scratch, monkeypatch):
    world, target = World(2), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    real = ws.BackupDataRoot.write_upload_evidence

    def broken(*args, **kwargs):
        raise ws.EvidenceWriteError("disk full")

    monkeypatch.setattr(ws.BackupDataRoot, "write_upload_evidence", broken)
    first = await do_upload(data_root, RUN_1, world, target, scratch)
    assert first.failure is up.UploadFailure.EVIDENCE_NOT_WRITTEN and first.published and not first.ok
    assert sealed(target, RUN_1) and data_root.published_run_ids() == []
    monkeypatch.setattr(ws.BackupDataRoot, "write_upload_evidence", real)
    snapshot = dict(target.objects)
    second = await do_upload(data_root, RUN_1, world, target, scratch)
    assert second.ok and second.adopted and second.objects == 6 and second.ready_assets == 2
    assert target.objects == snapshot and data_root.published_run_ids() == [RUN_1]


async def test_a_different_run_under_the_same_id_is_a_conflict_and_nothing_is_written(data_root, scratch):
    world, target = World(2), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    await do_upload(data_root, RUN_1, world, target, scratch)
    (data_root.path / "evidence" / f"{RUN_1}.published.json").unlink()
    other = World(1)
    shutil_run = data_root.path / "encrypted" / RUN_1
    for child in shutil_run.iterdir():
        child.unlink()
    shutil_run.rmdir()
    promote_run(data_root, RUN_1, other.assets, artifact=ARTIFACT + b"x")
    snapshot = dict(target.objects)
    report = await do_upload(data_root, RUN_1, other, target, scratch)
    assert report.failure is up.UploadFailure.TARGET_RUN_CONFLICT and report.step is up.UploadStep.TARGET
    assert target.objects == snapshot and data_root.published_run_ids() == []


# --- the local run ----------------------------------------------------------------------------------------------------------------


async def test_an_unknown_run_is_missing(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.RUN_MISSING and target.objects == {}


@pytest.mark.parametrize("name", [sc.READY_ASSETS_NAME, sc.RECIPIENTS_NAME, "local-run.json", ENCRYPTED_DUMP_NAME])
async def test_a_missing_file_of_the_run_stops_the_upload_before_any_write(data_root, scratch, name):
    world, target = World(1), tg.InMemoryBackupTarget()
    promoted = promote_run(data_root, RUN_1, world.assets)
    (promoted / name).unlink()
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.RUN_MISSING and report.step is up.UploadStep.LOCAL
    assert target.objects == {} and world.source.calls == []


@pytest.mark.parametrize("name", [sc.READY_ASSETS_NAME, sc.RECIPIENTS_NAME, "local-run.json", ENCRYPTED_DUMP_NAME])
async def test_a_symlinked_file_of_the_run_is_refused_not_followed(data_root, scratch, tmp_path, name):
    world, target = World(1), tg.InMemoryBackupTarget()
    promoted = promote_run(data_root, RUN_1, world.assets)
    outside = tmp_path / "outside"
    outside.write_bytes((promoted / name).read_bytes())
    outside.chmod(0o600)
    (promoted / name).unlink()
    os.symlink(outside, promoted / name)
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.RUN_UNSAFE and target.objects == {}


async def test_a_file_with_group_permissions_is_refused(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promoted = promote_run(data_root, RUN_1, world.assets)
    (promoted / sc.RECIPIENTS_NAME).chmod(0o644)
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.RUN_UNSAFE


def tamper(promoted: Path, name: str, mutate) -> None:
    path = promoted / name
    path.write_bytes(mutate(path.read_bytes()))


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        (sc.READY_ASSETS_NAME, lambda d: d + d.splitlines(keepends=True)[-1]),  # not canonical
        (sc.READY_ASSETS_NAME, lambda d: sc.ready_assets_bytes([ReadyAsset(uuid.UUID(int=99), "photos/v1/9/o.jpg", "photos/v1/9/d.jpg", "photos/v1/9/t.jpg", 1, 1, 1, "b" * 64)])),
        (sc.RECIPIENTS_NAME, lambda d: d + ("age1" + "p" * 58 + "\n").encode()),  # count differs from evidence
        (sc.RECIPIENTS_NAME, lambda d: b"garbage\n"),
        ("local-run.json", lambda d: d.replace(b'"status":"complete"', b'"status":"partial"')),
        ("local-run.json", lambda d: b"not json"),
        (ENCRYPTED_DUMP_NAME, lambda d: d + b"x"),  # artifact differs from the evidence
        (ENCRYPTED_DUMP_NAME, lambda d: b"X" + d[1:]),
    ],
)
async def test_a_file_that_disagrees_with_the_evidence_is_invalid_and_nothing_is_written(data_root, scratch, name, mutate):
    world, target = World(2), tg.InMemoryBackupTarget()
    promoted = promote_run(data_root, RUN_1, world.assets)
    tamper(promoted, name, mutate)
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.RUN_INVALID and report.step is up.UploadStep.LOCAL
    assert target.objects == {} and world.source.calls == [] and data_root.published_run_ids() == []


async def test_evidence_of_another_run_is_invalid(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promoted = promote_run(data_root, RUN_1, world.assets)
    tamper(promoted, "local-run.json", lambda d: d.replace(RUN_1.encode(), RUN_2.encode()))
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.RUN_INVALID


async def test_a_run_id_that_is_not_canonical_is_refused_outright(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    with pytest.raises(ValueError):
        await do_upload(data_root, "../evil", world, target, scratch)


# --- the prior run --------------------------------------------------------------------------------------------------------------------


async def test_an_explicit_prior_that_does_not_exist_is_unusable(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_2, world.assets)
    report = await do_upload(data_root, RUN_2, world, target, scratch, prior=RUN_1)
    assert report.failure is up.UploadFailure.PRIOR_UNUSABLE and report.prior_run_id == RUN_1 and target.objects == {}


async def test_a_published_prior_that_vanished_from_the_target_is_unusable_not_silently_ignored(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    await do_upload(data_root, RUN_1, world, tg.InMemoryBackupTarget(), scratch)  # evidence exists, target is another one
    promote_run(data_root, RUN_2, world.assets)
    report = await do_upload(data_root, RUN_2, world, target, scratch)
    assert report.failure is up.UploadFailure.PRIOR_UNUSABLE
    again = await do_upload(data_root, RUN_2, world, target, scratch, prior=None)  # the operator's explicit choice
    assert again.ok


async def test_an_unreadable_target_while_loading_the_prior_is_unavailable(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    await do_upload(data_root, RUN_1, world, target, scratch)
    promote_run(data_root, RUN_2, world.assets)
    target.inject("download_to", MediaStorageUnavailable("down", error_code="X", http_status=503), times=2, after=2)
    report = await do_upload(data_root, RUN_2, world, target, scratch)
    assert report.failure is up.UploadFailure.PRIOR_UNAVAILABLE and not sealed(target, RUN_2)


async def test_an_unreadable_target_while_looking_for_this_run_is_unavailable(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    target.inject("download_to", MediaStorageUnavailable("down", error_code="X", http_status=503))
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.TARGET_UNAVAILABLE and report.step is up.UploadStep.TARGET


# --- sync and publish failures --------------------------------------------------------------------------------------------------------------


async def test_a_missing_source_object_is_an_incomplete_sync_and_nothing_is_sealed(data_root, scratch):
    world, target = World(2), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    victim = world.assets[0].key_original
    del world.source.inner._objects[victim]
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.SYNC_INCOMPLETE and report.step is up.UploadStep.SYNC and not report.published
    document = json.loads(report.report_bytes())
    assert document["sync"]["failures"][0]["code"] == "MISSING_SOURCE" and document["sync"]["complete"] is False
    assert not sealed(target, RUN_1) and mf.manifest_key(RUN_1) not in target.objects and data_root.published_run_ids() == []
    world.source.add(victim, world.contents[victim])  # evidence recovered
    retry = await do_upload(data_root, RUN_1, world, target, scratch)
    assert retry.ok and sealed(target, RUN_1)


async def test_a_failed_publication_is_reported_and_never_sealed(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    target.inject("put_new", MediaStorageUnavailable("down", error_code="X", http_status=503), times=3, after=3)
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.PUBLISH_FAILED and report.step is up.UploadStep.PUBLISH
    assert not sealed(target, RUN_1) and data_root.published_run_ids() == []


# --- reports ---------------------------------------------------------------------------------------------------------------------------------------


async def test_reports_are_canonical_and_secret_free(data_root, scratch):
    world, target = World(2), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    ok = await do_upload(data_root, RUN_1, world, target, scratch)
    del world.source.inner._objects[world.assets[0].key_display]
    promote_run(data_root, RUN_2, world.assets)
    bad = await do_upload(data_root, RUN_2, world, target, scratch)
    for report in (ok, bad):
        raw = report.report_bytes()
        text = raw.decode()
        assert raw.endswith(b"\n") and raw.count(b"\n") == 1 and json.loads(raw)["format"] == up.REPORT_FORMAT
        for forbidden in (str(data_root.path), str(scratch), "photos/", RECIPIENT, SOURCE_BUCKET, TARGET_BUCKET, COMMIT, sha(ARTIFACT)):
            assert forbidden not in text
        for asset in world.assets:
            assert str(asset.asset_id) not in text or report is bad  # failures name the asset id (needed to act on)


def test_utc_compact_matches_the_evidence_name_pattern():
    name = up.utc_compact(datetime(2026, 10, 4, 12, 5, 9, tzinfo=UTC))
    assert name == "20261004T120509Z" and ws.UPLOAD_FAILED_EVIDENCE.match(f".upload-failed-{name}.json")


def test_unused_source_double_is_importable():
    assert Source  # the 2G double is reused as is


# --- the real db-dump output feeds the upload (no hand-made run) -----------------------------------------------------------------


async def test_a_run_produced_by_the_orchestrator_is_uploaded_unchanged(tmp_path, scratch):
    from tests.test_stage14d2d3_orchestrator import Harness, make

    root_dir = tmp_path / "dump-root"
    root_dir.mkdir(mode=0o700)
    world, target = World(3), tg.InMemoryBackupTarget()  # the harness metadata reports READY=3
    harness = Harness(root_dir)
    fake_dump = harness.snapshot_dump

    async def dump_with_world_assets(*args, **kwargs):
        result = await fake_dump(*args, **kwargs)
        digest = ready_set_digest(world.assets)
        return type(result)(**{**result.__dict__, "ready": digest, "ready_assets": tuple(world.assets)})

    produced = await make(root_dir, tmp_path, harness, snapshot_dump=dump_with_world_assets).run()
    data_root = ws.BackupDataRoot(root_dir)
    report = await do_upload(data_root, produced.run_id, world, target, scratch)
    assert report.ok and report.objects == 9 and report.ready_assets == 3
    verified = await load_prior_run(target, produced.run_id, scratch_dir=scratch)
    assert verified.manifest.header.snapshot.ready_set_sha256 == produced.evidence.snapshot.ready_set_sha256
    assert verified.manifest.header.db_dump.encrypted_sha256 == produced.evidence.artifact.sha256
    assert len(verified.manifest.header.db_dump.recipients) == produced.evidence.artifact.recipient_count
    assert data_root.published_run_ids() == [produced.run_id]


# --- gaps found by mutation testing ----------------------------------------------------------------------------------------------


async def test_an_inconsistent_seal_in_the_target_is_a_conflict_not_a_missing_run(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promote_run(data_root, RUN_1, world.assets)
    await do_upload(data_root, RUN_1, world, target, scratch)
    (data_root.path / "evidence" / f"{RUN_1}.published.json").unlink()
    target.objects[mf.complete_key(RUN_1)] = b'{"not":"a seal"}\n'
    snapshot = dict(target.objects)
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.TARGET_RUN_CONFLICT and report.step is up.UploadStep.TARGET
    assert target.objects == snapshot and data_root.published_run_ids() == []


async def test_a_run_taken_at_an_unexpected_schema_revision_is_invalid(data_root, scratch):
    world, target = World(1), tg.InMemoryBackupTarget()
    promoted = promote_run(data_root, RUN_1, world.assets)
    tamper(promoted, "local-run.json", lambda d: d.replace(f'"alembic_revision":"{HEAD}"'.encode(), b'"alembic_revision":"0031_old"'))
    assert b"0031_old" in (promoted / "local-run.json").read_bytes()
    report = await do_upload(data_root, RUN_1, world, target, scratch)
    assert report.failure is up.UploadFailure.RUN_INVALID and target.objects == {}


def test_a_file_larger_than_the_allowed_size_is_refused_not_truncated(data_root):
    promoted = promote_run(data_root, RUN_1, [])
    (promoted / "recipients.txt").write_bytes(b"x" * 100)
    assert len(data_root.read_promoted_file(RUN_1, "recipients.txt", max_bytes=100)) == 100
    with pytest.raises(ws.UnsafeBackupPathError, match="larger"):
        data_root.read_promoted_file(RUN_1, "recipients.txt", max_bytes=99)
    for bad in ("../x", "a/b", "", ".", ".."):
        with pytest.raises(ws.UnsafeBackupPathError):
            data_root.read_promoted_file(RUN_1, bad, max_bytes=10)
    with pytest.raises(ws.RunFileMissingError):
        data_root.read_promoted_file(RUN_2, "recipients.txt", max_bytes=10)


def test_upload_evidence_names_are_restricted(data_root):
    for suffix in (".json", ".published.json.bak", "x.published.json", ".upload-failed-2026.json", "/../x"):
        with pytest.raises(ws.EvidenceWriteError, match="not an upload evidence name"):
            data_root.write_upload_evidence(RUN_1, suffix, b"{}")
    path = data_root.write_upload_evidence(RUN_1, ".upload-failed-20261004T120509Z.json", b"{}\n")
    assert path.name == f"{RUN_1}.upload-failed-20261004T120509Z.json"
    with pytest.raises(ws.EvidenceWriteError, match="already exists"):
        data_root.write_upload_evidence(RUN_1, ".upload-failed-20261004T120509Z.json", b"{}\n")
