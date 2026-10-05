"""Stage 14D.6A — `python -m app.backup verify`: configuration, modes, report file, exit codes."""

import asyncio
import io
import json
import os
import signal
import stat
from pathlib import Path

import pytest

from app.backup import __main__ as cli
from app.backup import manifest as mf
from app.backup import target as tg
from app.backup import verify as vf
from app.backup import verify_command as vc
from app.domain.exceptions import MediaStorageMisconfigured
from tests.test_stage14d2e_manifest import RECIPIENT_A, RECIPIENT_B
from tests.test_stage14d2g_media_sync import RUN_1, RUN_2, World, sealed

ENV = {"BACKUP_OCI_NAMESPACE": "testnamespace", "BACKUP_OCI_BUCKET": "plan-estimate-backup-prod"}
RECIPIENT_OTHER = "age1" + "z" * 58


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


class Rig:
    def __init__(self, target: tg.InMemoryBackupTarget | None = None) -> None:
        self.target = target or tg.InMemoryBackupTarget()
        self.built: list[argparse_args] = []
        self.deps = vc.VerifyDependencies(make_reader=self._reader)

    def _reader(self, settings, args):
        self.built.append(args)
        self.settings = settings
        return self.target


argparse_args = object


def prepared(scratch: Path, tmp_path: Path, count: int = 2) -> tuple[Rig, World]:
    """A sealed run in an in-memory target (built before the command runs: the command itself owns the event loop)."""
    world, target = World(count), tg.InMemoryBackupTarget()
    asyncio.run(sealed(world, target, scratch, tmp_path, RUN_1))
    return Rig(target), world


def invoke(rig: Rig, argv: list[str], env: dict[str, str] | None = None, **kw) -> tuple[int, str]:
    out = io.StringIO()
    code = vc.run_verify(ENV if env is None else env, argv, out, deps=rig.deps, **kw)
    return code, out.getvalue()


def run_invoke(rig: Rig, argv: list[str], scratch: Path, **kw):
    return invoke(rig, [*argv, "--scratch-dir", str(scratch)], **kw)


# --- success ---------------------------------------------------------------------------------------------------------------


def test_a_sealed_run_verifies_in_both_modes(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    for mode, dump in (("full", "sha256"), ("quick", "size")):
        code, text = run_invoke(rig, ["--run-id", RUN_1, "--mode", mode], scratch)
        assert code == vc.EXIT_SUCCESS and f"verify ok: run_id={RUN_1} mode={mode} dump={dump}" in text
        assert "objects_total=6" in text


def test_the_default_mode_is_full(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    code, text = run_invoke(rig, ["--run-id", RUN_1], scratch)
    assert code == 0 and "mode=full" in text and "sha_checked=6" in text


def test_the_report_file_is_canonical_private_and_secret_free(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    report = tmp_path / "report.json"
    code, text = run_invoke(rig, ["--run-id", RUN_1, "--report-file", str(report)], scratch)
    assert code == 0
    raw = report.read_bytes()
    document = json.loads(raw)
    assert document["ok"] is True and document["run_id"] == RUN_1 and raw.endswith(b"\n") and raw.count(b"\n") == 1
    assert stat.S_IMODE(report.stat().st_mode) == 0o600
    for forbidden in (str(tmp_path), "photos/", ENV["BACKUP_OCI_BUCKET"], ENV["BACKUP_OCI_NAMESPACE"], RECIPIENT_A):
        assert forbidden not in text and forbidden not in raw.decode()
    assert list(scratch.iterdir()) == [], "the per-run scratch is removed"


def test_the_settings_reach_the_reader(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    argv = ["--run-id", RUN_1, "--oci-config", "/abs/config", "--oci-profile", "restore", "--expect-recipient", RECIPIENT_A]
    env = {**ENV, "BACKUP_OCI_REGION": "eu-amsterdam-1"}
    run_invoke(rig, argv, scratch, env=env)
    assert (rig.settings.namespace, rig.settings.bucket, rig.settings.region) == ("testnamespace", "plan-estimate-backup-prod", "eu-amsterdam-1")
    assert rig.built[0].oci_config == "/abs/config" and rig.built[0].oci_profile == "restore"


# --- recipients ------------------------------------------------------------------------------------------------------------


def test_expected_recipients_that_are_in_the_run_pass_and_missing_ones_fail(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    ok = run_invoke(rig, ["--run-id", RUN_1, "--expect-recipient", RECIPIENT_A, "--expect-recipient", RECIPIENT_B], scratch)
    assert ok[0] == 0
    code, text = run_invoke(rig, ["--run-id", RUN_1, "--expect-recipient", RECIPIENT_OTHER], scratch)
    assert code == vc.EXIT_FAILED and "run_problems=RECIPIENTS_MISMATCH" in text


def test_the_backup_recipients_of_the_environment_are_used_when_no_flag_is_given(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    env = {**ENV, "BACKUP_AGE_RECIPIENTS": f"{RECIPIENT_A}, {RECIPIENT_OTHER}"}
    code, text = run_invoke(rig, ["--run-id", RUN_1], scratch, env=env)
    assert code == 1 and "RECIPIENTS_MISMATCH" in text
    # an explicit flag wins over the environment
    code, _ = run_invoke(rig, ["--run-id", RUN_1, "--expect-recipient", RECIPIENT_A], scratch, env=env)
    assert code == 0


@pytest.mark.parametrize("bad", ["AGE-SECRET-KEY-1" + "Q" * 58, "ssh-ed25519 AAAA", "not-a-recipient"])
def test_a_private_ssh_or_malformed_recipient_is_refused_without_echo(scratch, bad):
    rig = Rig()
    code, text = run_invoke(rig, ["--run-id", RUN_1, "--expect-recipient", bad], scratch)
    assert code == vc.EXIT_PREFLIGHT and bad not in text and rig.built == []


# --- problems ----------------------------------------------------------------------------------------------------------------


def test_an_unknown_run_is_a_failure_with_a_code(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    code, text = run_invoke(rig, ["--run-id", RUN_2], scratch)
    assert code == vc.EXIT_FAILED and "verify failed" in text and "run_problems=SEAL_MISSING" in text


def test_full_finds_a_changed_object_that_quick_cannot(scratch, tmp_path):
    rig, world = prepared(scratch, tmp_path)
    key = world.key_of(0, "display")
    data = rig.target.objects[key]
    rig.target.objects[key] = bytes([data[0] ^ 1]) + data[1:]
    quick = run_invoke(rig, ["--run-id", RUN_1, "--mode", "quick"], scratch)
    assert quick[0] == 0
    code, text = run_invoke(rig, ["--run-id", RUN_1, "--mode", "full"], scratch)
    assert code == vc.EXIT_FAILED and "object_problems=SHA_MISMATCH:1" in text
    assert key not in text and "photos/" not in text


def test_a_removed_object_and_a_damaged_dump_are_reported(scratch, tmp_path):
    rig, world = prepared(scratch, tmp_path)
    del rig.target.objects[world.key_of(1, "thumbnail")]
    dump = mf.db_dump_key(RUN_1)
    rig.target.objects[dump] = rig.target.objects[dump][:-1]
    code, text = run_invoke(rig, ["--run-id", RUN_1, "--mode", "quick"], scratch)
    assert code == 1 and "DUMP_SIZE_MISMATCH" in text and "object_problems=MISSING_OBJECT:1" in text


def test_a_failing_run_still_writes_its_report(scratch, tmp_path):
    rig, _ = prepared(scratch, tmp_path)
    report = tmp_path / "failed.json"
    code, _ = run_invoke(rig, ["--run-id", RUN_2, "--report-file", str(report)], scratch)
    assert code == 1 and json.loads(report.read_bytes())["ok"] is False


# --- preflight ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["BACKUP_OCI_NAMESPACE", "BACKUP_OCI_BUCKET"])
def test_required_settings_are_required(scratch, name):
    rig = Rig()
    code, text = run_invoke(rig, ["--run-id", RUN_1], scratch, env={k: v for k, v in ENV.items() if k != name})
    assert code == vc.EXIT_PREFLIGHT and name in text and rig.built == []


@pytest.mark.parametrize(("name", "value"), [("BACKUP_OCI_NAMESPACE", "bad namespace"), ("BACKUP_OCI_BUCKET", "X"), ("BACKUP_OCI_REGION", "Frankfurt")])
def test_invalid_settings_are_refused_without_echoing_the_value(scratch, name, value):
    rig = Rig()
    code, text = run_invoke(rig, ["--run-id", RUN_1], scratch, env={**ENV, name: value})
    assert code == vc.EXIT_PREFLIGHT and name in text and value not in text and rig.built == []


def test_bad_arguments_are_refused_before_anything_is_built(scratch, tmp_path):
    rig = Rig()
    for argv in (
        ["--run-id", "../evil"],
        ["--run-id", RUN_1, "--oci-config", "relative"],
        ["--run-id", RUN_1, "--report-file", "relative.json"],
        ["--run-id", RUN_1, "--oci-profile", "bad profile"],
        ["--run-id", RUN_1, "--scratch-dir", str(tmp_path / "missing")],
    ):
        code, text = invoke(rig, argv)
        assert code == vc.EXIT_PREFLIGHT, (argv, text)
    assert rig.built == []


def test_an_existing_report_file_is_never_overwritten(scratch, tmp_path):
    rig = Rig()
    report = tmp_path / "r.json"
    report.write_text("precious")
    code, text = run_invoke(rig, ["--run-id", RUN_1, "--report-file", str(report)], scratch)
    assert code == vc.EXIT_PREFLIGHT and "already exists" in text and report.read_text() == "precious" and rig.built == []


def test_an_unknown_mode_is_a_usage_error(scratch):
    with pytest.raises(SystemExit) as excinfo:
        run_invoke(Rig(), ["--run-id", RUN_1, "--mode", "everything"], scratch)
    assert excinfo.value.code == 2


def test_storage_client_errors_exit_5_without_provider_text(scratch):
    def broken(settings, args):
        raise MediaStorageMisconfigured("principal", error_code="ProviderDetailSecret")

    rig = Rig()
    rig.deps = vc.VerifyDependencies(make_reader=broken)
    code, text = run_invoke(rig, ["--run-id", RUN_1], scratch)
    assert code == vc.EXIT_PREFLIGHT and "MediaStorageMisconfigured" in text and "ProviderDetailSecret" not in text


# --- lifecycle ---------------------------------------------------------------------------------------------------------------


def test_the_report_file_failing_after_the_check_exits_7(scratch, tmp_path, monkeypatch):
    async def fake(reader, run_id, **kwargs):
        return vf.VerifyReport(run_id, vf.VerifyMode.FULL, "2026-10-05T10:00:00Z", (), (), None, vf.VerifyCounts(), "sha256")

    rig = Rig()
    rig.deps = vc.VerifyDependencies(make_reader=rig._reader, verify=fake)

    def broken(path, data):
        raise OSError(28, "No space left")

    monkeypatch.setattr(vc, "write_report_file", broken)
    code, text = run_invoke(rig, ["--run-id", RUN_1, "--report-file", str(tmp_path / "r.json")], scratch)
    assert code == vc.EXIT_REPORT_NOT_WRITTEN and "verify ok" in text and "could not be written" in text


def test_sigterm_interrupts_cleanly(scratch):
    async def slow(reader, run_id, **kwargs):
        async def send():
            await asyncio.sleep(0.05)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.get_running_loop().create_task(send())
        await asyncio.sleep(3600)

    rig = Rig()
    rig.deps = vc.VerifyDependencies(make_reader=rig._reader, verify=slow)
    previous = signal.getsignal(signal.SIGTERM)
    code, text = run_invoke(rig, ["--run-id", RUN_1], scratch)
    assert code == vc.EXIT_INTERRUPTED and "interrupted" in text and signal.getsignal(signal.SIGTERM) == previous
    assert list(scratch.iterdir()) == []


def test_exit_codes_are_distinct_and_documented():
    codes = {vc.EXIT_SUCCESS, vc.EXIT_FAILED, vc.EXIT_PREFLIGHT, vc.EXIT_INTERRUPTED, vc.EXIT_REPORT_NOT_WRITTEN}
    assert len(codes) == 5
    for code in codes:
        assert f"    {code}  " in vc.__doc__


def test_main_dispatches_verify(monkeypatch):
    seen = {}

    def fake(env, argv, out, **kwargs):
        seen["argv"] = argv
        return 44

    monkeypatch.setattr(vc, "run_verify", fake)
    assert cli.main(["verify", "--run-id", RUN_1], env={}, out=io.StringIO()) == 44
    assert seen["argv"] == ["--run-id", RUN_1]
