"""Stage 14D.2H — logic of the live verify smoke, exercised on an in-memory target."""

import dataclasses
import sys
import types
from pathlib import Path

import pytest

from app.backup import manifest as mf
from app.backup import media_sync as ms
from app.backup import target as tg
from app.backup import verify as vf
from scripts import stage14d2h_verify_smoke as smoke
from tests.test_stage14d2e_manifest import RECIPIENT_A, RECIPIENT_B
from tests.test_stage14d2g_media_sync import (
    NO_RETRY,
    RUN_1,
    RUN_2,
    World,
    publish,
    run_sync,
    sealed,
)

NAMES_BASE = [
    "full_verify_passes",
    "quick_verify_reads_documents_only",
    "unknown_run_reported",
    "recipient_mismatch_reported",
    "flipped_bytes_detected",
    "changed_size_detected",
    "hidden_object_detected",
    "changed_dump_detected",
    "report_is_secret_free",
]


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


async def two_runs(scratch: Path, tmp_path: Path) -> tg.InMemoryBackupTarget:
    world, target = World(2), tg.InMemoryBackupTarget()
    prior = await sealed(world, target, scratch, tmp_path, RUN_1)
    result = await run_sync(world, target, scratch, run_id=RUN_2, prior=prior)
    await publish(world, target, result, scratch, tmp_path, RUN_2)
    target.calls.clear()
    return target


def failed(results: list[smoke.CheckResult]) -> dict[str, str]:
    return {r.name: r.detail for r in results if not r.passed}


async def test_a_genuine_run_passes_every_check(scratch: Path, tmp_path: Path):
    target = await two_runs(scratch, tmp_path)
    results = await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY)
    assert [r.name for r in results] == NAMES_BASE
    assert failed(results) == {}
    assert list(scratch.iterdir()) == []


async def test_the_inherited_run_and_expected_recipients_add_their_checks(scratch: Path, tmp_path: Path):
    target = await two_runs(scratch, tmp_path)
    results = await smoke.run_checks(
        target, scratch, run_id=RUN_1, run_id_2=RUN_2, expect_recipients=(RECIPIENT_A, RECIPIENT_B), retry=NO_RETRY
    )
    names = [r.name for r in results]
    assert "inherited_run_verified_by_download" in names and "expected_recipients_accepted" in names
    assert failed(results) == {}


async def test_the_smoke_never_changes_the_target(scratch: Path, tmp_path: Path):
    target = await two_runs(scratch, tmp_path)
    before = dict(target.objects)
    await smoke.run_checks(target, scratch, run_id=RUN_1, run_id_2=RUN_2, retry=NO_RETRY)
    assert target.objects == before
    assert {op for op, _ in target.calls} <= {"head", "download_to"}


async def test_the_inherited_check_needs_a_run_that_really_inherited(scratch: Path, tmp_path: Path):
    target = await two_runs(scratch, tmp_path)
    results = await smoke.run_checks(target, scratch, run_id=RUN_1, run_id_2=RUN_1, retry=NO_RETRY)
    assert "inherited_run_verified_by_download" in failed(results), "a run without inherited lines proves nothing"


async def test_wrong_expected_recipients_fail_the_positive_recipient_check(scratch: Path, tmp_path: Path):
    target = await two_runs(scratch, tmp_path)
    results = await smoke.run_checks(
        target, scratch, run_id=RUN_1, expect_recipients=("age1" + "z" * 58,), retry=NO_RETRY
    )
    assert list(failed(results)) == ["expected_recipients_accepted"]


async def test_a_damaged_stored_run_fails_the_genuine_checks(scratch: Path, tmp_path: Path):
    target = await two_runs(scratch, tmp_path)
    key = next(k for k in target.objects if k.startswith("photos/v1/") and k.endswith("thumb.jpg"))
    data = target.objects[key]
    target.objects[key] = bytes([data[0] ^ 0xFF]) + data[1:]
    results = await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY)
    assert "full_verify_passes" in failed(results)


async def test_an_unsealed_run_cannot_be_used(scratch: Path, tmp_path: Path):
    target = await two_runs(scratch, tmp_path)
    del target.objects[mf.complete_key(RUN_1)]
    with pytest.raises(ms.PriorRunError):
        await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY)


async def test_a_run_with_too_few_objects_cannot_be_used(scratch: Path, tmp_path: Path):
    world, target = World(0), tg.InMemoryBackupTarget()
    await sealed(world, target, scratch, tmp_path, RUN_1)
    with pytest.raises(ValueError):
        await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY)


async def test_a_verifier_that_sees_nothing_fails_every_negative_check(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The smoke must not pass because the library under test is blind."""
    target = await two_runs(scratch, tmp_path)
    real = vf.verify_run_in_target

    async def blind(reader: tg.BackupReader, run_id: str, **kwargs: object) -> vf.VerifyReport:
        report = await real(reader, RUN_1, **kwargs)  # type: ignore[arg-type]
        return dataclasses.replace(report, run_problems=(), object_problems=(), aborted=None)

    monkeypatch.setattr(vf, "verify_run_in_target", blind)
    results = await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY)
    assert set(failed(results)) == {
        "unknown_run_reported",
        "recipient_mismatch_reported",
        "flipped_bytes_detected",
        "changed_size_detected",
        "hidden_object_detected",
        "changed_dump_detected",
        "report_is_secret_free",
    }


async def test_a_verifier_with_extra_problems_fails_the_exactly_one_checks(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = await two_runs(scratch, tmp_path)
    real = vf.verify_run_in_target

    async def noisy(reader: tg.BackupReader, run_id: str, **kwargs: object) -> vf.VerifyReport:
        report = await real(reader, run_id, **kwargs)  # type: ignore[arg-type]
        extra = vf.ObjectProblem("00000000-0000-4000-8000-000000000000", mf.Role.DISPLAY, vf.ObjectProblemCode.MISSING_OBJECT)
        return dataclasses.replace(report, object_problems=(*report.object_problems, extra))

    monkeypatch.setattr(vf, "verify_run_in_target", noisy)
    results = await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY)
    assert {"flipped_bytes_detected", "changed_size_detected", "hidden_object_detected"} <= set(failed(results))


async def test_a_verifier_that_reads_every_object_in_quick_mode_fails_the_quick_check(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = await two_runs(scratch, tmp_path)
    real = vf.verify_run_in_target

    async def greedy(reader: tg.BackupReader, run_id: str, **kwargs: object) -> vf.VerifyReport:
        kwargs["mode"] = vf.VerifyMode.FULL
        return await real(reader, run_id, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(vf, "verify_run_in_target", greedy)
    assert "quick_verify_reads_documents_only" in failed(await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY))


async def test_a_report_that_leaks_fails_the_secret_free_check(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = await two_runs(scratch, tmp_path)
    monkeypatch.setattr(vf.VerifyReport, "report_bytes", lambda self: b"SHA_MISMATCH photos/v1/leaked")
    assert "report_is_secret_free" in failed(await smoke.run_checks(target, scratch, run_id=RUN_1, retry=NO_RETRY))


def test_random_recipients_are_well_formed_and_distinct():
    from app.core.db_dump_encryption import parse_age_recipients

    values = {smoke.random_recipient() for _ in range(20)}
    assert len(values) == 20 and parse_age_recipients(values)


def test_report_format():
    report = smoke.format_report([smoke.CheckResult("a", True, "ok"), smoke.CheckResult("b", False, "KeyError")], [RUN_1])
    assert report.endswith("RESULT: FAIL (1/2 checks passed)") and RUN_1 in report and "KeyError" in report


def test_main_refuses_non_drill_buckets_bad_run_ids_and_missing_namespace(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    assert smoke.main(["--namespace", "ns", "--bucket", "plan-estimate-backup-prod", "--run-id", RUN_1]) == smoke.EXIT_CANNOT_RUN
    assert "not a drill bucket" in capsys.readouterr().err
    assert smoke.main(["--run-id", RUN_1]) == smoke.EXIT_CANNOT_RUN
    assert "--namespace" in capsys.readouterr().err
    assert smoke.main(["--namespace", "ns", "--run-id", "../x"]) == smoke.EXIT_CANNOT_RUN
    assert "canonical form" in capsys.readouterr().err
    assert smoke.main(["--namespace", "ns", "--run-id", RUN_1, "--run-id-2", "nope"]) == smoke.EXIT_CANNOT_RUN


def test_main_reports_a_missing_instance_principal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    def no_principal() -> None:
        raise ConnectionRefusedError("169.254.169.254 refused")

    fake = types.ModuleType("oci")
    fake.auth = types.SimpleNamespace(  # type: ignore[attr-defined]
        signers=types.SimpleNamespace(InstancePrincipalsSecurityTokenSigner=no_principal)
    )
    monkeypatch.setitem(sys.modules, "oci", fake)
    assert smoke.main(["--namespace", "ns", "--run-id", RUN_1]) == smoke.EXIT_NO_PRINCIPAL
    out = capsys.readouterr().out
    assert "NOT obtainable" in out and "169.254" not in out


def test_main_distinguishes_a_missing_sdk_from_a_missing_principal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setitem(sys.modules, "oci", None)
    assert smoke.main(["--namespace", "ns", "--run-id", RUN_1]) == smoke.EXIT_CANNOT_RUN
    captured = capsys.readouterr()
    assert "oci==2.187.1" in captured.err and "NOT obtainable" not in captured.out
