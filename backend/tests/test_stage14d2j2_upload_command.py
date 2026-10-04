"""Stage 14D.2J.2 — `python -m app.backup upload`: settings, guard, run selection, exit codes."""

import asyncio
import io
import json
import os
import signal
import stat
from pathlib import Path

import pytest

from app.backup import __main__ as cli
from app.backup import target as tg
from app.backup import upload_command as uc
from app.backup import workspace as ws
from app.backup.upload_run import PUBLISHED_FORMAT
from app.domain.exceptions import MediaStorageMisconfigured
from tests.test_stage14d2g_media_sync import World
from tests.test_stage14d2j2_upload_run import COMMIT, RUN_1, RUN_2, promote_run

SECRET_KEY, SECRET = "AKIAFAKEKEYID1234567", "fakeSecretNeverPrinted0123456789"
ENV = {
    "MEDIA_S3_ENDPOINT_URL": "https://0123456789abcdef0123456789abcdef.eu.r2.cloudflarestorage.com",
    "MEDIA_S3_BUCKET": "plan-estimate-media-drill",
    "MEDIA_S3_ACCESS_KEY_ID": SECRET_KEY,
    "MEDIA_S3_SECRET_ACCESS_KEY": SECRET,
    "BACKUP_OCI_NAMESPACE": "testnamespace",
    "BACKUP_OCI_BUCKET": "plan-estimate-backup-drill",
    "BACKUP_TOOL_COMMIT": COMMIT,
}
DRILL = ["--environment", "drill"]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "data"
    path.mkdir(mode=0o700)
    ws.BackupDataRoot(path).prepare()
    return path


@pytest.fixture
def scratch_parent(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


class Rig:
    def __init__(self, world: World, target: tg.InMemoryBackupTarget) -> None:
        self.world, self.target = world, target
        self.deps = uc.UploadDependencies(make_source=lambda s, e: world.source, make_target=lambda s: target)


def invoke(root: Path, rig: Rig, argv: list[str], env: dict[str, str] | None = None, scratch: Path | None = None, **kw):
    out = io.StringIO()
    args = [*argv] + (["--scratch-dir", str(scratch)] if scratch else [])
    code = uc.run_upload(ENV if env is None else env, args, out, data_root=root, deps=rig.deps, **kw)
    return code, out.getvalue()


# --- settings and guard ------------------------------------------------------------------------------------------------


def test_settings_are_read_from_the_environment():
    settings = uc.settings_from_env(ENV, "drill", allow_production=False)
    assert (settings.source_bucket, settings.target_bucket) == ("plan-estimate-media-drill", "plan-estimate-backup-drill")
    assert (settings.source_region, settings.source_name, settings.target_region) == ("auto", "r2-primary", "eu-frankfurt-1")
    assert repr(settings).count(SECRET) == 0


@pytest.mark.parametrize("name", sorted(ENV))
def test_every_required_setting_is_required(name):
    env = {key: value for key, value in ENV.items() if key != name}
    with pytest.raises(uc.UploadConfigError, match=name):
        uc.settings_from_env(env, "drill", allow_production=False)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MEDIA_S3_ENDPOINT_URL", "http://insecure.example"),
        ("MEDIA_S3_ENDPOINT_URL", "https://x/ y"),
        ("MEDIA_S3_BUCKET", "Bad_Bucket"),
        ("BACKUP_OCI_NAMESPACE", "bad namespace"),
        ("BACKUP_OCI_BUCKET", "x"),
        ("BACKUP_OCI_REGION", "Frankfurt"),
        ("MEDIA_STORAGE_NAME", "-bad"),
        ("BACKUP_TOOL_COMMIT", "abc123"),
        ("BACKUP_TOOL_COMMIT", "A" * 40),
    ],
)
def test_invalid_settings_are_refused_without_echoing_the_value(name, value):
    with pytest.raises(uc.UploadConfigError) as excinfo:
        uc.settings_from_env({**ENV, name: value}, "drill", allow_production=False)
    assert name in str(excinfo.value) and value not in str(excinfo.value)


@pytest.mark.parametrize(
    ("environment", "source", "target", "allow", "ok"),
    [
        ("drill", "media-drill", "backup-drill", False, True),
        ("drill", "media-prod", "backup-drill", False, False),
        ("drill", "media-drill", "backup-prod", False, False),
        ("production", "media-prod", "backup-prod", True, True),
        ("production", "media-prod", "backup-prod", False, False),  # production uploads are off by default
        ("production", "media-drill", "backup-prod", True, False),
        ("production", "media-prod", "backup-drill", True, False),
        ("drill", "same-drill", "same-drill", False, False),
        ("staging", "media-drill", "backup-drill", False, False),
    ],
)
def test_the_environment_guard(environment, source, target, allow, ok):
    if ok:
        uc.check_environment(environment, source, target, allow_production=allow)
    else:
        with pytest.raises(uc.UploadConfigError):
            uc.check_environment(environment, source, target, allow_production=allow)


# --- run selection --------------------------------------------------------------------------------------------------------


def test_the_newest_promoted_run_without_published_evidence_is_selected(root):
    data_root = ws.BackupDataRoot(root)
    world = World(1)
    assert uc.select_run(data_root, None) is None
    promote_run(data_root, RUN_1, world.assets)
    promote_run(data_root, RUN_2, world.assets)
    assert uc.select_run(data_root, None) == RUN_2
    data_root.write_upload_evidence(RUN_2, ws.PUBLISHED_EVIDENCE_SUFFIX, b"{}\n")
    assert uc.select_run(data_root, None) == RUN_1
    assert uc.select_run(data_root, RUN_2) == RUN_2  # an explicit choice is not second-guessed here


def test_junk_in_encrypted_and_evidence_is_ignored(root):
    data_root = ws.BackupDataRoot(root)
    (root / "encrypted" / "not-a-run").mkdir()
    (root / "encrypted" / "readme.txt").write_text("x")
    (root / "evidence" / "garbage.published.json").write_text("x")
    (root / "evidence" / f"{RUN_1}.failed.json").write_text("x")
    assert data_root.promoted_run_ids() == [] and data_root.published_run_ids() == []


# --- end to end -------------------------------------------------------------------------------------------------------------------


def test_a_successful_upload_exits_zero_and_prints_a_secret_free_summary(root, scratch_parent):
    world = World(2)
    rig = Rig(world, tg.InMemoryBackupTarget())
    promote_run(ws.BackupDataRoot(root), RUN_1, world.assets)
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_SUCCESS and f"upload complete: run_id={RUN_1} published objects=6 ready_assets=2 prior=-" in text
    for forbidden in (SECRET, SECRET_KEY, str(root), "photos/", COMMIT, "testnamespace"):
        assert forbidden not in text
    assert list(scratch_parent.iterdir()) == []  # the per-run scratch is removed
    evidence = root / "evidence" / f"{RUN_1}.published.json"
    assert json.loads(evidence.read_bytes())["format"] == PUBLISHED_FORMAT and stat.S_IMODE(evidence.stat().st_mode) == 0o600


def test_the_second_run_finds_its_prior_by_itself(root, scratch_parent):
    world = World(2)
    rig = Rig(world, tg.InMemoryBackupTarget())
    data_root = ws.BackupDataRoot(root)
    promote_run(data_root, RUN_1, world.assets)
    assert invoke(root, rig, DRILL, scratch=scratch_parent)[0] == 0
    promote_run(data_root, RUN_2, world.assets)
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == 0 and f"run_id={RUN_2}" in text and f"prior={RUN_1}" in text


def test_nothing_to_upload_exits_8(root, scratch_parent):
    rig = Rig(World(1), tg.InMemoryBackupTarget())
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_NOTHING_TO_UPLOAD and "nothing to upload" in text
    promote_run(ws.BackupDataRoot(root), RUN_1, rig.world.assets)
    assert invoke(root, rig, DRILL, scratch=scratch_parent)[0] == 0
    code, text = invoke(root, rig, [*DRILL, "--run-id", RUN_1], scratch=scratch_parent)
    assert code == uc.EXIT_NOTHING_TO_UPLOAD and "ALREADY_PUBLISHED" in text
    assert list((root / "evidence").glob("*.upload-failed-*")) == []  # not a failure worth a record


def test_an_unknown_explicit_run_exits_8(root, scratch_parent):
    rig = Rig(World(1), tg.InMemoryBackupTarget())
    code, text = invoke(root, rig, [*DRILL, "--run-id", RUN_1], scratch=scratch_parent)
    assert code == uc.EXIT_NOTHING_TO_UPLOAD and "RUN_MISSING" in text


def test_a_run_whose_files_disagree_exits_9(root, scratch_parent):
    world = World(1)
    rig = Rig(world, tg.InMemoryBackupTarget())
    promoted = promote_run(ws.BackupDataRoot(root), RUN_1, world.assets)
    (promoted / "recipients.txt").write_bytes(b"garbage\n")
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_RUN_UNUSABLE and "RUN_INVALID" in text and rig.target.objects == {}


def test_an_incomplete_sync_exits_1_and_leaves_a_failure_record(root, scratch_parent):
    world = World(2)
    rig = Rig(world, tg.InMemoryBackupTarget())
    promote_run(ws.BackupDataRoot(root), RUN_1, world.assets)
    del world.source.inner._objects[world.assets[1].key_thumbnail]
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_FAILED and "step=sync failure=SYNC_INCOMPLETE" in text
    (record,) = list((root / "evidence").glob(f"{RUN_1}.upload-failed-*.json"))
    assert ws.UPLOAD_FAILED_EVIDENCE.match(record.name.removeprefix(RUN_1))
    document = json.loads(record.read_bytes())
    assert document["failure"] == "SYNC_INCOMPLETE" and document["sync"]["failures"][0]["code"] == "MISSING_SOURCE"
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
    assert list((root / "evidence").glob("*.published.json")) == []


def test_sealed_without_local_evidence_exits_10_and_the_same_command_finishes_it(root, scratch_parent, monkeypatch):
    world = World(1)
    rig = Rig(world, tg.InMemoryBackupTarget())
    promote_run(ws.BackupDataRoot(root), RUN_1, world.assets)
    real = ws.BackupDataRoot.write_upload_evidence
    calls = []

    def flaky(self, run_id, suffix, data):
        calls.append(suffix)
        if suffix == ws.PUBLISHED_EVIDENCE_SUFFIX and len(calls) == 1:
            raise ws.EvidenceWriteError("disk full")
        return real(self, run_id, suffix, data)

    monkeypatch.setattr(ws.BackupDataRoot, "write_upload_evidence", flaky)
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_SEALED_WITHOUT_EVIDENCE and "IS sealed" in text
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == 0 and "adopted" in text


def test_a_held_lock_exits_3_and_touches_nothing(root, scratch_parent):
    rig = Rig(World(1), tg.InMemoryBackupTarget())
    promote_run(ws.BackupDataRoot(root), RUN_1, rig.world.assets)
    with ws.RunLock.acquire(ws.BackupDataRoot(root)):
        code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_LOCK_HELD and "run.lock" in text and rig.target.objects == {}


def test_configuration_failures_exit_5_before_anything_is_built(root, scratch_parent):
    built = []
    rig = Rig(World(1), tg.InMemoryBackupTarget())
    rig.deps = uc.UploadDependencies(make_source=lambda s, e: built.append("s"), make_target=lambda s: built.append("t"))
    code, text = invoke(root, rig, DRILL, env={k: v for k, v in ENV.items() if k != "BACKUP_OCI_NAMESPACE"})
    assert code == uc.EXIT_PREFLIGHT and "BACKUP_OCI_NAMESPACE" in text and built == []
    code, text = invoke(root, rig, ["--environment", "production", "--allow-production"])
    assert code == uc.EXIT_PREFLIGHT and "refuses drill buckets" in text and built == []
    prod = {**ENV, "MEDIA_S3_BUCKET": "plan-estimate-media", "BACKUP_OCI_BUCKET": "plan-estimate-backup"}
    code, text = invoke(root, rig, ["--environment", "production"], env=prod)
    assert code == uc.EXIT_PREFLIGHT and "not enabled" in text and built == []
    code, text = invoke(root, rig, [*DRILL, "--run-id", "bad id"])
    assert code == uc.EXIT_PREFLIGHT and built == []
    code, text = invoke(root, rig, [*DRILL, "--prior", "bad id"])
    assert code == uc.EXIT_PREFLIGHT and built == []


def test_an_unusable_data_root_exits_5(tmp_path, scratch_parent):
    rig = Rig(World(1), tg.InMemoryBackupTarget())
    code, text = invoke(tmp_path / "missing", rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_PREFLIGHT and "data root" in text


def test_storage_client_errors_exit_5_without_provider_text(root, scratch_parent):
    def broken(settings):
        raise MediaStorageMisconfigured("no instance principal is available here", error_code="NoPrincipalDetailsSecret")

    rig = Rig(World(1), tg.InMemoryBackupTarget())
    rig.deps = uc.UploadDependencies(make_source=lambda s, e: rig.world.source, make_target=broken)
    promote_run(ws.BackupDataRoot(root), RUN_1, rig.world.assets)
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_PREFLIGHT and "MediaStorageMisconfigured" in text and "NoPrincipalDetailsSecret" not in text


def test_an_unusable_scratch_directory_exits_5(root, tmp_path):
    rig = Rig(World(1), tg.InMemoryBackupTarget())
    promote_run(ws.BackupDataRoot(root), RUN_1, rig.world.assets)
    code, text = invoke(root, rig, DRILL, scratch=tmp_path / "nope")
    assert code == uc.EXIT_PREFLIGHT and "scratch" in text and rig.target.objects == {}


def test_prior_none_and_deep_are_passed_through(root, scratch_parent):
    world = World(1)
    rig = Rig(world, tg.InMemoryBackupTarget())
    data_root = ws.BackupDataRoot(root)
    promote_run(data_root, RUN_1, world.assets)
    assert invoke(root, rig, DRILL, scratch=scratch_parent)[0] == 0
    promote_run(data_root, RUN_2, world.assets)
    before = len(world.source.downloads())
    code, text = invoke(root, rig, [*DRILL, "--prior", "none", "--deep"], scratch=scratch_parent)
    assert code == 0 and "prior=-" in text and len(world.source.downloads()) == before + 3


def test_sigterm_interrupts_cleanly_and_seals_nothing(root, scratch_parent):
    world = World(1)
    rig = Rig(world, tg.InMemoryBackupTarget())
    promote_run(ws.BackupDataRoot(root), RUN_1, world.assets)

    class Blocking:
        async def download_to(self, key, path):
            async def send():
                await asyncio.sleep(0.05)
                os.kill(os.getpid(), signal.SIGTERM)

            asyncio.get_running_loop().create_task(send())
            await asyncio.sleep(3600)

        def iter_keys(self, prefix):
            raise AssertionError("not reached")

    rig.deps = uc.UploadDependencies(make_source=lambda s, e: Blocking(), make_target=lambda s: rig.target)
    previous = signal.getsignal(signal.SIGTERM)
    code, text = invoke(root, rig, DRILL, scratch=scratch_parent)
    assert code == uc.EXIT_INTERRUPTED and "interrupted" in text
    assert signal.getsignal(signal.SIGTERM) == previous
    assert tg_sealed(rig.target) is False and list(scratch_parent.iterdir()) == []


def tg_sealed(target: tg.InMemoryBackupTarget) -> bool:
    return any(key.endswith("COMPLETE.json") for key in target.objects)


def test_exit_codes_are_distinct_and_documented():
    codes = {uc.EXIT_SUCCESS, uc.EXIT_FAILED, uc.EXIT_LOCK_HELD, uc.EXIT_PREFLIGHT, uc.EXIT_INTERRUPTED,
             uc.EXIT_NOTHING_TO_UPLOAD, uc.EXIT_RUN_UNUSABLE, uc.EXIT_SEALED_WITHOUT_EVIDENCE}
    assert len(codes) == 8
    for code in codes:
        assert f"    {code}  " in uc.__doc__ or f"   {code}  " in uc.__doc__


def test_main_dispatches_upload_and_keeps_the_other_commands(root, monkeypatch, capsys):
    seen = {}

    def fake(env, argv, out, **kwargs):
        seen["argv"] = argv
        return 42

    monkeypatch.setattr(uc, "run_upload", fake)
    assert cli.main(["upload", "--environment", "drill"], env={}, out=io.StringIO()) == 42
    assert seen["argv"] == ["--environment", "drill"]
    with pytest.raises(SystemExit):
        cli.main(["nonsense"], env={}, out=io.StringIO())
