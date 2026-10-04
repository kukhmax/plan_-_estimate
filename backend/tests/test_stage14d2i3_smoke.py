"""Stage 14D.2I.3 — logic of the live media-restore smoke, exercised on in-memory stores."""

import sys
import types
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from app.backup import restore_media as rm
from app.backup import target as tg
from app.domain.services.media_storage import InMemoryMediaStorage, _StoredObject
from scripts import stage14d2i3_media_restore_smoke as smoke
from tests.test_stage14d2g_media_sync import NO_RETRY, RUN_1, World, sealed

ENDPOINT = "https://" + "0123456789abcdef" * 2 + ".eu.r2.cloudflarestorage.com"
DESTINATION = "plan-estimate-media-drill-restore"
FORBIDDEN = ("plan-estimate-media-prod", "plan-estimate-media-drill-source")
NAMES = [
    "restore_all_objects",
    "destination_matches_manifest",
    "rerun_is_idempotent",
    "conflict_is_reported_and_kept",
    "foreign_object_stops_restore",
    "unsafe_destination_refused",
    "damaged_backup_bytes_not_written",
    "report_is_secret_free",
]


class MemoryAdmin:
    def __init__(self, store: InMemoryMediaStorage) -> None:
        self.store = store

    async def put_bytes(self, key: str, data: bytes) -> None:
        self.store._objects[key] = _StoredObject(data=data, content_type="image/jpeg")

    async def delete(self, key: str) -> None:
        self.store._objects.pop(key, None)


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


async def backup_with_run(scratch: Path, tmp_path: Path, count: int = 2) -> tg.InMemoryBackupTarget:
    target = tg.InMemoryBackupTarget()
    await sealed(World(count), target, scratch, tmp_path, RUN_1)
    return target


async def backup_in(scratch: Path, tmp_path: Path, name: str) -> tg.InMemoryBackupTarget:
    """A second sealed run in its own directory (a test may need a fresh backup after the first was consumed)."""
    (tmp_path / name).mkdir()
    return await backup_with_run(scratch, tmp_path / name)


async def run(
    backup: tg.InMemoryBackupTarget,
    store: InMemoryMediaStorage,
    scratch: Path,
    created: set[str] | None = None,
    **kwargs: Any,
) -> list[smoke.CheckResult]:
    options: dict[str, Any] = {
        "run_id": RUN_1,
        "destination_bucket": DESTINATION,
        "forbidden_buckets": FORBIDDEN,
        "created": set() if created is None else created,
        "retry": NO_RETRY,
    }
    options.update(kwargs)
    return await smoke.run_checks(backup, store, MemoryAdmin(store), scratch, **options)


def failed(results: list[smoke.CheckResult]) -> dict[str, str]:
    return {r.name: r.detail for r in results if not r.passed}


async def test_a_genuine_run_passes_every_check_and_leaves_only_what_it_created(scratch: Path, tmp_path: Path):
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    created: set[str] = set()
    results = await run(backup, store, scratch, created)
    assert [r.name for r in results] == NAMES and failed(results) == {}
    assert created and set(store._objects) <= created, "every object left in the destination was created by the smoke"
    assert list(scratch.iterdir()) == []


async def test_a_destination_that_is_not_empty_is_not_touched(scratch: Path, tmp_path: Path):
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    created: set[str] = set()
    store._objects["photos/v1/00000000-0000-4000-8000-0000000000aa/original.jpg"] = _StoredObject(b"someone else's", "image/jpeg")
    with pytest.raises(smoke.SmokeCannotRun):
        await run(backup, store, scratch, created)
    assert created == set() and len(store._objects) == 1


async def test_a_run_with_too_few_objects_or_no_forbidden_list_cannot_be_used(scratch: Path, tmp_path: Path):
    (tmp_path / "e").mkdir()
    empty = await backup_with_run(scratch, tmp_path / "e", 0)
    with pytest.raises(smoke.SmokeCannotRun):
        await run(empty, InMemoryMediaStorage(), scratch)
    backup = await backup_with_run(scratch, tmp_path)
    with pytest.raises(smoke.SmokeCannotRun):
        await run(backup, InMemoryMediaStorage(), scratch, forbidden_buckets=())


async def test_an_unsealed_run_cannot_be_used(scratch: Path, tmp_path: Path):
    from app.backup import manifest as mf
    from app.backup import media_sync as ms

    backup = await backup_with_run(scratch, tmp_path)
    del backup.objects[mf.complete_key(RUN_1)]
    with pytest.raises(ms.PriorRunError):
        await run(backup, InMemoryMediaStorage(), scratch)


class WriteNothing:
    """A broken restore that reports success without writing: the independent check must notice."""

    async def __call__(self, reader: Any, run: Any, destination: Any, **kwargs: Any) -> rm.MediaRestoreReport:
        counts = rm.RestoreCounts(objects_total=len(run.manifest.objects), restored=len(run.manifest.objects))
        return rm.MediaRestoreReport(run.run_id, None, (), None, counts)


async def test_a_restore_that_claims_success_without_writing_fails_the_independent_check(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    monkeypatch.setattr(rm, "restore_media", WriteNothing())
    results = await run(backup, store, scratch)
    assert next(iter(failed(results))) == "destination_matches_manifest"
    assert all(r.detail.startswith("skipped") for r in results[2:])


async def test_a_restore_that_replaces_what_it_finds_fails_the_conflict_check(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A broken restore that treats a conflicting object like a missing one and overwrites it."""
    real = rm.restore_media

    async def overwriting(reader: Any, run: Any, destination: Any, **kwargs: Any) -> rm.MediaRestoreReport:
        workdir = scratch / "overwrite"
        workdir.mkdir(exist_ok=True)
        for obj in run.manifest.objects:
            path = workdir / "o"
            await reader.download_to(obj.key, path)
            destination.inner._objects[obj.key] = _StoredObject(data=path.read_bytes(), content_type="image/jpeg")
            path.unlink()
        workdir.rmdir()
        return await real(reader, run, destination, **kwargs)

    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    monkeypatch.setattr(rm, "restore_media", overwriting)
    assert "conflict_is_reported_and_kept" in failed(await run(backup, store, scratch))


async def test_a_restore_without_the_foreign_object_guard_fails_the_foreign_check(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    real = rm.restore_media

    async def permissive(reader: Any, run: Any, destination: Any, **kwargs: Any) -> rm.MediaRestoreReport:
        kwargs["allow_foreign_objects"] = True
        return await real(reader, run, destination, **kwargs)

    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    monkeypatch.setattr(rm, "restore_media", permissive)
    assert "foreign_object_stops_restore" in failed(await run(backup, store, scratch))


async def test_a_restore_without_the_destination_guard_fails_the_unsafe_check(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    real = rm.restore_media

    async def unguarded(reader: Any, run: Any, destination: Any, **kwargs: Any) -> rm.MediaRestoreReport:
        kwargs["destination_bucket"] = DESTINATION  # ignores the bucket it was asked about
        return await real(reader, run, destination, **kwargs)

    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    monkeypatch.setattr(rm, "restore_media", unguarded)
    assert "unsafe_destination_refused" in failed(await run(backup, store, scratch))


# --- a broken restore must fail the matching check -----------------------------------------------------------------------------------

Behavior = Any  # async (real, reader, run, destination, kwargs) -> MediaRestoreReport


def scripted(monkeypatch: pytest.MonkeyPatch, behaviors: dict[int, Behavior]) -> None:
    """Replace `restore_media`; call number n of the smoke runs `behaviors[n]` instead of the honest engine.
    The smoke calls it for: 1 restore all, 2 rerun, 3 conflict, 4 foreign object, 5 unsafe bucket, 6 damaged bytes, 7 report."""
    real = rm.restore_media
    calls = {"n": 0}

    async def wrapper(reader: Any, run: Any, destination: Any, **kwargs: Any) -> rm.MediaRestoreReport:
        calls["n"] += 1
        behavior = behaviors.get(calls["n"])
        if behavior is None:
            return await real(reader, run, destination, **kwargs)
        return await behavior(real, reader, run, destination, kwargs)

    monkeypatch.setattr(rm, "restore_media", wrapper)


def canned(run: Any, *, restored: int = 0, present: int = 0) -> rm.MediaRestoreReport:
    counts = rm.RestoreCounts(objects_total=len(run.manifest.objects), restored=restored, already_present=present)
    return rm.MediaRestoreReport(run.run_id, None, (), None, counts)


def stored_bytes(destination: Any) -> dict[str, bytes]:
    return {key: obj.data for key, obj in destination.inner._objects.items()}


async def honest_then(after: Callable[[Any, Any], Awaitable[None]]) -> Behavior:
    async def behavior(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        report = await real(reader, run, destination, **kwargs)
        await after(run, destination)
        return report

    return behavior


async def test_a_claim_of_success_without_the_restored_counts_fails_restore_all(
    scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    async def claims_present(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        return canned(run, present=len(run.manifest.objects))

    scripted(monkeypatch, {1: claims_present})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "restore_all_objects" in failed(await run(backup, store, scratch))


async def test_an_extra_object_in_the_destination_fails_the_key_comparison(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def plant(run_: Any, destination: Any) -> None:
        destination.inner._objects["photos/v1/00000000-0000-4000-8000-0000000000ee/original.jpg"] = _StoredObject(b"x", "image/jpeg")

    scripted(monkeypatch, {1: await honest_then(plant)})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "destination_matches_manifest" in failed(await run(backup, store, scratch))


async def test_a_changed_object_in_the_destination_fails_the_content_comparison(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def corrupt(run_: Any, destination: Any) -> None:
        key = min(stored_bytes(destination))
        data = destination.inner._objects[key].data
        destination.inner._objects[key] = _StoredObject(bytes([data[0] ^ 0xFF]) + data[1:], "image/jpeg")

    scripted(monkeypatch, {1: await honest_then(corrupt)})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "destination_matches_manifest" in failed(await run(backup, store, scratch))


async def test_a_rerun_that_has_to_restore_again_fails_the_idempotency_check(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def lose_one(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        destination.inner._objects.pop(min(stored_bytes(destination)))
        return await real(reader, run, destination, **kwargs)

    scripted(monkeypatch, {2: lose_one})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "rerun_is_idempotent" in failed(await run(backup, store, scratch))


async def test_a_rerun_that_reports_new_restores_fails_the_idempotency_check(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def claims_a_restore(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        total = len(run.manifest.objects)
        return canned(run, restored=1, present=total - 1)  # looks fine, but a resumed run must restore nothing

    scripted(monkeypatch, {2: claims_a_restore})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "rerun_is_idempotent" in failed(await run(backup, store, scratch))


async def test_a_rerun_that_writes_or_reads_the_backup_fails_the_idempotency_check(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def writes(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        key = min(stored_bytes(destination))
        spare = kwargs["scratch_dir"] / "spare"
        spare.write_bytes(stored_bytes(destination)[key])
        await destination.put_object(key, spare, "image/jpeg")  # an identical re-put: harmless, but a write
        spare.unlink()
        return await real(reader, run, destination, **kwargs)

    scripted(monkeypatch, {2: writes})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "rerun_is_idempotent" in failed(await run(backup, store, scratch))

    async def reads(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        spare = kwargs["scratch_dir"] / "spare2"
        await reader.download_to(run.manifest.objects[0].key, spare)
        spare.unlink()
        return await real(reader, run, destination, **kwargs)

    scripted(monkeypatch, {2: reads})
    backup2, store2 = await backup_in(scratch, tmp_path, "b"), InMemoryMediaStorage()
    assert "rerun_is_idempotent" in failed(await run(backup2, store2, scratch))


async def test_a_conflict_that_goes_unreported_fails_the_conflict_check(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def ignores(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        return canned(run, present=len(run.manifest.objects))

    scripted(monkeypatch, {3: ignores})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "conflict_is_reported_and_kept" in failed(await run(backup, store, scratch))


async def test_a_conflicting_object_that_is_silently_repaired_fails_the_conflict_check(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def repairs(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        report = await real(reader, run, destination, **kwargs)
        victim = run.manifest.objects[0]
        path = kwargs["scratch_dir"] / "fix"
        await reader.download_to(victim.key, path)
        destination.inner._objects[victim.key] = _StoredObject(path.read_bytes(), "image/jpeg")
        path.unlink()
        return report

    scripted(monkeypatch, {3: repairs})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "conflict_is_reported_and_kept" in failed(await run(backup, store, scratch))


async def test_damaged_bytes_that_go_unreported_or_get_written_fail_the_damaged_check(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def unreported(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        return canned(run, restored=len(run.manifest.objects) - 1)

    scripted(monkeypatch, {6: unreported})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "damaged_backup_bytes_not_written" in failed(await run(backup, store, scratch))

    async def writes_victim(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        report = await real(reader, run, destination, **kwargs)
        victim = run.manifest.objects[1]
        destination.inner._objects[victim.key] = _StoredObject(b"damaged", "image/jpeg")
        return report

    scripted(monkeypatch, {6: writes_victim})
    backup2, store2 = await backup_in(scratch, tmp_path, "c"), InMemoryMediaStorage()
    assert "damaged_backup_bytes_not_written" in failed(await run(backup2, store2, scratch))


async def test_a_report_that_leaks_fails_the_secret_free_check(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rm.MediaRestoreReport, "report_bytes", lambda self: b"photos/v1/leaked")
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    assert "report_is_secret_free" in failed(await run(backup, store, scratch))


async def test_a_planted_foreign_object_is_recorded_for_cleanup_even_if_the_step_crashes(scratch: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def crash(real: Any, reader: Any, run: Any, destination: Any, kwargs: Any) -> rm.MediaRestoreReport:
        raise RuntimeError("boom")

    scripted(monkeypatch, {4: crash})
    backup, store = await backup_with_run(scratch, tmp_path), InMemoryMediaStorage()
    created: set[str] = set()
    results = await run(backup, store, scratch, created)
    assert "foreign_object_stops_restore" in failed(results)
    assert set(store._objects) <= created, "whatever was planted is on the cleanup list"


def test_report_format():
    report = smoke.format_report([smoke.CheckResult("a", True, "ok"), smoke.CheckResult("b", False, "KeyError")], RUN_1)
    assert report.endswith("RESULT: FAIL (1/2 checks passed)") and RUN_1 in report and "KeyError" in report


# --- configuration --------------------------------------------------------------------------------------------------------------------


def good_env(**overrides: str) -> dict[str, str]:
    env = {
        "R2_ENDPOINT_URL": ENDPOINT,
        "R2_ACCESS_KEY_ID": "id",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_BUCKET": DESTINATION,
        "R2_FORBIDDEN_BUCKETS": ",".join(FORBIDDEN),
        "OCI_NAMESPACE": "ns",
    }
    env.update(overrides)
    return env


def test_load_r2_config_accepts_the_restore_token_environment_and_hides_credentials():
    config = smoke.load_r2_config(good_env())
    assert config.bucket == DESTINATION and config.forbidden_buckets == FORBIDDEN
    assert "secret" not in repr(config)


@pytest.mark.parametrize(
    "overrides",
    [
        {"R2_ENDPOINT_URL": "https://abc.r2.cloudflarestorage.com"},
        {"R2_ACCESS_KEY_ID": ""},
        {"R2_SECRET_ACCESS_KEY": ""},
        {"R2_BUCKET": "plan-estimate-media-prod"},
        {"R2_BUCKET": "Bad_Name"},
        {"R2_FORBIDDEN_BUCKETS": ""},
        {"R2_FORBIDDEN_BUCKETS": DESTINATION},
        {"R2_FORBIDDEN_BUCKETS": "Bad_Name"},
    ],
)
def test_load_r2_config_refuses_unsafe_configuration(overrides: dict[str, str]):
    with pytest.raises(ValueError) as excinfo:
        smoke.load_r2_config(good_env(**overrides))
    assert "secret" not in str(excinfo.value)


def test_main_refuses_unsafe_inputs(capsys: pytest.CaptureFixture[str]):
    base = ["--namespace", "ns", "--run-id", RUN_1]
    assert smoke.main([*base, "--bucket", "plan-estimate-backup-prod"], good_env()) == smoke.EXIT_CANNOT_RUN
    assert "not a drill bucket" in capsys.readouterr().err
    assert smoke.main(["--run-id", RUN_1], {**good_env(), "OCI_NAMESPACE": ""}) == smoke.EXIT_CANNOT_RUN
    assert "--namespace" in capsys.readouterr().err
    assert smoke.main(["--namespace", "ns", "--run-id", "../x"], good_env()) == smoke.EXIT_CANNOT_RUN
    assert smoke.main(base, good_env(R2_BUCKET="plan-estimate-media-prod")) == smoke.EXIT_CANNOT_RUN
    assert "drill" in capsys.readouterr().err


def test_main_reports_a_missing_oci_principal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    def no_principal() -> None:
        raise ConnectionRefusedError("169.254.169.254 refused")

    fake = types.ModuleType("oci")
    fake.auth = types.SimpleNamespace(  # type: ignore[attr-defined]
        signers=types.SimpleNamespace(InstancePrincipalsSecurityTokenSigner=no_principal)
    )
    monkeypatch.setitem(sys.modules, "oci", fake)
    assert smoke.main(["--namespace", "ns", "--run-id", RUN_1], good_env()) == smoke.EXIT_NO_PRINCIPAL
    out = capsys.readouterr().out
    assert "NOT obtainable" in out and "169.254" not in out


def test_main_distinguishes_a_missing_sdk_from_a_missing_principal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setitem(sys.modules, "oci", None)
    assert smoke.main(["--namespace", "ns", "--run-id", RUN_1], good_env()) == smoke.EXIT_CANNOT_RUN
    captured = capsys.readouterr()
    assert "oci==2.187.1" in captured.err and "NOT obtainable" not in captured.out


def test_main_refuses_an_unsafe_oci_config_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    config = tmp_path / "config"
    config.write_text("[DEFAULT]\nuser=x\n")
    config.chmod(0o644)
    code = smoke.main(["--namespace", "ns", "--run-id", RUN_1, "--oci-config", str(config)], good_env())
    assert code == smoke.EXIT_NO_PRINCIPAL
    out = capsys.readouterr().out
    assert "NOT obtainable" in out and str(config) not in out
