"""Stage 14D.2J.3 — `python -m app.backup restore`: configuration, guards, report file, exit codes."""

import asyncio
import io
import json
import os
import signal
import stat
from pathlib import Path
from typing import Any

import pytest

from app.backup import __main__ as cli
from app.backup import restore_command as rc
from app.backup import restore_db as rd
from app.backup import restore_media as rm
from app.backup import restore_run as rr
from app.domain.exceptions import MediaStorageMisconfigured

RUN = "20261004T120000Z-0123abcd"
KEY_LINE = "AGE-SECRET-KEY-1" + "Q" * 58
SECRET_KEY, SECRET = "AKIAFAKERESTOREKEY123", "fakeRestoreSecretNeverPrinted01"
FORBIDDEN_PROD = "plan-estimate-media"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    base = tmp_path / "home"
    base.mkdir(mode=0o700)
    (base / "scratch").mkdir(mode=0o700)
    (base / "age.key").write_text(f"# created\n{KEY_LINE}\n")
    (base / "age.key").chmod(0o600)
    (base / "pgpass").write_text("localhost:5432:pe_restore_scratch_1:pe_restore:fakePw\n")
    (base / "pgpass").chmod(0o600)
    return base


def env_for(home: Path, **overrides: str) -> dict[str, str]:
    env = {
        "PGHOST": "localhost",
        "PGPORT": "5432",
        "PGDATABASE": "pe_restore_scratch_1",
        "PGUSER": "pe_restore",
        "PGPASSFILE": str(home / "pgpass"),
        "PGSSLMODE": "disable",
        "BACKUP_OCI_NAMESPACE": "testnamespace",
        "BACKUP_OCI_BUCKET": "plan-estimate-backup-drill",
        "RESTORE_S3_ENDPOINT_URL": "https://0123456789abcdef0123456789abcdef.eu.r2.cloudflarestorage.com",
        "RESTORE_S3_BUCKET": "plan-estimate-restore-drill",
        "RESTORE_S3_ACCESS_KEY_ID": SECRET_KEY,
        "RESTORE_S3_SECRET_ACCESS_KEY": SECRET,
    }
    env.update(overrides)
    return env


def argv_for(home: Path, **replace: Any) -> list[str]:
    args = {
        "--run-id": RUN,
        "--identity-file": str(home / "age.key"),
        "--scratch-dir": str(home / "scratch"),
        "--report-file": str(home / "report.json"),
        "--forbidden-bucket": FORBIDDEN_PROD,
    }
    args.update(replace)
    out: list[str] = []
    for name, value in args.items():
        if value is not None:
            out += [name, value]
    return out


def good_report(run_id: str = RUN) -> rr.RestoreRunReport:
    database = rd.DbRestoreReport(run_id, rd.RestoreStep.DONE, None, ready_count=2, alembic_revision="0032_x")
    media = rm.MediaRestoreReport(run_id, None, (), None, rm.RestoreCounts(objects_total=6, restored=4, already_present=2))
    return rr.RestoreRunReport(run_id, rr.RunStep.DONE, None, database, media)


class Rig:
    def __init__(self, report: rr.RestoreRunReport | None = None, error: BaseException | None = None) -> None:
        self.report = report or good_report()
        self.error = error
        self.calls: list[tuple[Any, str, dict[str, Any]]] = []
        self.built: list[str] = []
        self.deps = rc.RestoreDependencies(make_reader=self._reader, make_destination=self._destination, restore=self._restore)

    def _reader(self, settings, args):
        self.built.append("reader")
        self.reader_args = args
        return object()

    def _destination(self, settings, env):
        self.built.append("destination")
        return object()

    async def _restore(self, reader, run_id, **kwargs):
        self.calls.append((reader, run_id, kwargs))
        if self.error is not None:
            raise self.error
        return self.report


def invoke(rig: Rig, env: dict[str, str], argv: list[str], **kw) -> tuple[int, str]:
    out = io.StringIO()
    code = rc.run_restore(env, argv, out, deps=rig.deps, **kw)
    return code, out.getvalue()


# --- success ------------------------------------------------------------------------------------------------------------------


def test_a_good_restore_exits_zero_prints_a_summary_and_writes_the_report(home):
    rig = Rig()
    code, text = invoke(rig, env_for(home), argv_for(home))
    assert code == rc.EXIT_SUCCESS
    assert f"restore ok: run_id={RUN} ready_count=2 restored=4 already_present=2 total=6" in text
    report = home / "report.json"
    assert report.read_bytes() == good_report().report_bytes() and stat.S_IMODE(report.stat().st_mode) == 0o600
    ((_, run_id, kwargs),) = rig.calls
    assert run_id == RUN and kwargs["destination_bucket"] == "plan-estimate-restore-drill"
    assert set(kwargs["forbidden_buckets"]) == {FORBIDDEN_PROD, "plan-estimate-backup-drill"}  # the backup bucket is added
    assert kwargs["allow_non_drill"] is False and kwargs["allow_foreign_objects"] is False
    assert kwargs["verify_destination"] is True and kwargs["identity_file"] == home / "age.key"
    assert kwargs["database"].database == "pe_restore_scratch_1"
    for forbidden in (SECRET, SECRET_KEY, KEY_LINE, str(home), "fakePw"):
        assert forbidden not in text and forbidden.encode() not in report.read_bytes()


def test_the_per_run_scratch_is_created_inside_the_given_directory_and_removed(home):
    rig = Rig()
    seen = {}

    async def spy(reader, run_id, **kwargs):
        seen["scratch"] = kwargs["scratch_dir"]
        seen["existed"] = kwargs["scratch_dir"].is_dir()
        seen["mode"] = stat.S_IMODE(kwargs["scratch_dir"].stat().st_mode)
        return good_report()

    rig.deps.restore = spy
    assert invoke(rig, env_for(home), argv_for(home))[0] == 0
    assert seen["scratch"].parent == home / "scratch" and seen["existed"] and seen["mode"] == 0o700
    assert not seen["scratch"].exists()


def test_the_options_are_passed_through(home):
    rig = Rig()
    argv = argv_for(home) + ["--allow-non-drill", "--allow-foreign-objects", "--no-verify-destination",
                             "--allowed-host", "scratch-db.internal", "--oci-config", "/abs/config", "--oci-profile", "restore",
                             "--forbidden-bucket", "second-forbidden"]
    assert invoke(rig, env_for(home, RESTORE_S3_BUCKET="plan-estimate-restore"), argv)[0] == 0
    ((_, _, kwargs),) = rig.calls
    assert kwargs["allow_non_drill"] and kwargs["allow_foreign_objects"] and not kwargs["verify_destination"]
    assert kwargs["allowed_hosts"] == ("scratch-db.internal",) and "second-forbidden" in kwargs["forbidden_buckets"]
    assert rig.reader_args.oci_config == "/abs/config" and rig.reader_args.oci_profile == "restore"


# --- failures of the restore ------------------------------------------------------------------------------------------------


def test_a_failed_database_step_exits_1_but_still_writes_the_report(home):
    database = rd.DbRestoreReport(RUN, rd.RestoreStep.LOAD, rd.RestoreFailure.DECRYPT_FAILED)
    failed = rr.RestoreRunReport(RUN, rr.RunStep.DATABASE, None, database, None)
    code, text = invoke(Rig(failed), env_for(home), argv_for(home))
    assert code == rc.EXIT_FAILED
    assert f"restore failed: run_id={RUN} step=database database_step=load database_failure=DECRYPT_FAILED" in text
    assert json.loads((home / "report.json").read_bytes())["database"]["failure"] == "DECRYPT_FAILED"


def test_a_failed_media_step_exits_1_and_names_the_counts_only(home):
    problem = rm.ObjectProblem("0" * 8 + "-0000-0000-0000-" + "0" * 12, rm.Role.ORIGINAL, rm.ObjectProblemCode.BACKUP_UNAVAILABLE)
    media = rm.MediaRestoreReport(RUN, None, (problem,), rm.AbortReason.STORAGE_UNAVAILABLE, rm.RestoreCounts(objects_total=6, failed=1))
    database = rd.DbRestoreReport(RUN, rd.RestoreStep.DONE, None, ready_count=2)
    failed = rr.RestoreRunReport(RUN, rr.RunStep.MEDIA, None, database, media)
    code, text = invoke(Rig(failed), env_for(home), argv_for(home))
    assert code == rc.EXIT_FAILED and "media_aborted=STORAGE_UNAVAILABLE media_problems=1" in text


def test_a_chain_failure_exits_1(home):
    failed = rr.RestoreRunReport(RUN, rr.RunStep.SEAL, rr.ChainFailure.SEAL_MISSING, None, None)
    code, text = invoke(Rig(failed), env_for(home), argv_for(home))
    assert code == rc.EXIT_FAILED and "step=seal failure=SEAL_MISSING" in text


def test_the_report_file_failing_after_the_restore_exits_7(home, monkeypatch):
    def broken(path, data):
        raise OSError(28, "No space left")

    monkeypatch.setattr(rc, "write_report_file", broken)
    code, text = invoke(Rig(), env_for(home), argv_for(home))
    assert code == rc.EXIT_REPORT_NOT_WRITTEN and "restore ok" in text and "could not be written" in text


def test_sigterm_interrupts_cleanly(home):
    rig = Rig()

    async def slow(reader, run_id, **kwargs):
        async def send():
            await asyncio.sleep(0.05)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.get_running_loop().create_task(send())
        await asyncio.sleep(3600)

    rig.deps.restore = slow
    previous = signal.getsignal(signal.SIGTERM)
    code, text = invoke(rig, env_for(home), argv_for(home))
    assert code == rc.EXIT_INTERRUPTED and "interrupted" in text and signal.getsignal(signal.SIGTERM) == previous
    assert not (home / "report.json").exists() and list((home / "scratch").iterdir()) == []


# --- preflight: nothing is built, read or written ----------------------------------------------------------------------------


def preflight_fails(home, env=None, argv=None, expect: str = "", *, report_absent: bool = True) -> None:
    rig = Rig()
    code, text = invoke(rig, env or env_for(home), argv or argv_for(home))
    assert code == rc.EXIT_PREFLIGHT, text
    assert expect in text, text
    assert rig.built == [] and rig.calls == []
    assert not report_absent or not (home / "report.json").exists()
    for secret in (SECRET, SECRET_KEY, KEY_LINE):
        assert secret not in text


@pytest.mark.parametrize(
    "name",
    ["PGHOST", "PGDATABASE", "BACKUP_OCI_NAMESPACE", "BACKUP_OCI_BUCKET", "RESTORE_S3_ENDPOINT_URL", "RESTORE_S3_BUCKET",
     "RESTORE_S3_ACCESS_KEY_ID", "RESTORE_S3_SECRET_ACCESS_KEY"],
)
def test_every_required_setting_is_required(home, name):
    env = {k: v for k, v in env_for(home).items() if k != name}
    preflight_fails(home, env=env, expect=name)


@pytest.mark.parametrize(
    ("name", "value"),
    [("RESTORE_S3_ENDPOINT_URL", "http://insecure.example"), ("RESTORE_S3_BUCKET", "Bad_Bucket"), ("BACKUP_OCI_BUCKET", "x"),
     ("BACKUP_OCI_NAMESPACE", "bad namespace"), ("BACKUP_OCI_REGION", "Frankfurt")],
)
def test_invalid_settings_are_refused_without_echoing_the_value(home, name, value):
    preflight_fails(home, env=env_for(home, **{name: value}), expect=name)


def test_a_password_in_the_environment_is_refused(home):
    preflight_fails(home, env=env_for(home, PGPASSWORD="x"), expect="PGPASSWORD")


def test_a_database_that_is_not_a_scratch_database_is_refused(home):
    preflight_fails(home, env=env_for(home, PGDATABASE="plan_estimate"), expect="pe_restore_scratch")


def test_a_remote_database_host_needs_an_explicit_allowance(home):
    (home / "pgpass").write_text("db.example.com:5432:pe_restore_scratch_1:pe_restore:fakePw\n")
    env = env_for(home, PGHOST="db.example.com")
    preflight_fails(home, env=env, expect="explicitly allowed")
    code, _ = invoke(Rig(), env, [*argv_for(home), "--allowed-host", "db.example.com"])
    assert code == rc.EXIT_SUCCESS


def test_a_bad_passfile_is_refused(home):
    (home / "pgpass").chmod(0o644)
    preflight_fails(home)


def test_a_bad_identity_file_is_refused(home):
    (home / "age.key").chmod(0o644)
    preflight_fails(home)
    (home / "age.key").chmod(0o600)
    (home / "age.key").write_text("not a key\n")
    preflight_fails(home)


@pytest.mark.parametrize("name", ["--identity-file", "--scratch-dir", "--report-file"])
def test_relative_paths_are_refused(home, name):
    preflight_fails(home, argv=argv_for(home, **{name: "relative/path"}), expect="absolute")


def test_the_destination_guards_apply(home):
    preflight_fails(home, env=env_for(home, RESTORE_S3_BUCKET=FORBIDDEN_PROD), expect="forbidden")
    preflight_fails(home, env=env_for(home, RESTORE_S3_BUCKET="plan-estimate-restore"), expect="drill bucket")
    preflight_fails(home, env=env_for(home, RESTORE_S3_BUCKET="plan-estimate-backup-drill"), expect="forbidden")  # the backup bucket
    preflight_fails(home, argv=argv_for(home, **{"--forbidden-bucket": None}), expect="--forbidden-bucket")
    preflight_fails(home, argv=argv_for(home, **{"--forbidden-bucket": "Bad Name"}), expect="--forbidden-bucket")


def test_an_existing_report_file_is_never_overwritten(home):
    (home / "report.json").write_text("precious")
    preflight_fails(home, expect="already exists", report_absent=False)
    assert (home / "report.json").read_text() == "precious"


def test_a_missing_report_directory_or_scratch_directory_fails_before_the_restore(home):
    preflight_fails(home, argv=argv_for(home, **{"--report-file": str(home / "nope" / "r.json")}), expect="directory")
    preflight_fails(home, argv=argv_for(home, **{"--scratch-dir": str(home / "nope")}), expect="scratch")


def test_a_bad_run_id_is_refused(home):
    preflight_fails(home, argv=argv_for(home, **{"--run-id": "../evil"}))


def test_storage_client_errors_exit_5_without_provider_text(home):
    rig = Rig()

    def broken(settings, args):
        raise MediaStorageMisconfigured("config", error_code="ProviderDetailSecret")

    rig.deps.make_reader = broken
    code, text = invoke(rig, env_for(home), argv_for(home))
    assert code == rc.EXIT_PREFLIGHT and "MediaStorageMisconfigured" in text and "ProviderDetailSecret" not in text
    assert rig.calls == [] and not (home / "report.json").exists()


def test_a_symlinked_report_target_is_not_followed(home):
    victim = home / "victim"
    victim.write_text("keep")
    os.symlink(victim, home / "report.json")
    preflight_fails(home, expect="already exists", report_absent=False)
    assert victim.read_text() == "keep"


def test_write_report_file_is_exclusive_and_private(tmp_path):
    path = tmp_path / "r.json"
    rc.write_report_file(path, b"x\n")
    assert path.read_bytes() == b"x\n" and stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        rc.write_report_file(path, b"y")


def test_exit_codes_are_distinct_and_documented():
    codes = {rc.EXIT_SUCCESS, rc.EXIT_FAILED, rc.EXIT_PREFLIGHT, rc.EXIT_INTERRUPTED, rc.EXIT_REPORT_NOT_WRITTEN}
    assert len(codes) == 5
    for code in codes:
        assert f"    {code}  " in rc.__doc__


def test_main_dispatches_restore(monkeypatch):
    seen = {}

    def fake(env, argv, out, **kwargs):
        seen["argv"] = argv
        return 43

    monkeypatch.setattr(rc, "run_restore", fake)
    assert cli.main(["restore", "--run-id", RUN], env={}, out=io.StringIO()) == 43
    assert seen["argv"] == ["--run-id", RUN]
