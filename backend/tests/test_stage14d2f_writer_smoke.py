"""Stage 14D.2F — logic of the live OCI writer smoke, exercised on the in-memory target."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.backup import manifest as mf
from app.backup import target as tg
from app.backup.run_id import new_run_id
from scripts import stage14d2f_oci_writer_smoke as smoke

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
RUN_ID = "20261004T120000Z-0123abcd"
NO_RETRY = tg.RetryPolicy(max_attempts=1, base_delay=0.0)

EXPECTED = [
    "principal_and_put_created",
    "put_identical_is_idempotent",
    "put_different_bytes_refused",
    "object_unchanged_after_conflict",
    "publish_run_zero_asset",
    "stored_run_verifies",
    "stored_dump_matches",
    "republish_different_seal_refused",
    "seal_unchanged",
]


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


async def run(target: tg.InMemoryBackupTarget, scratch: Path) -> dict[str, smoke.CheckResult]:
    results = await smoke.run_checks(target, scratch, now=NOW, run_id=RUN_ID, retry=NO_RETRY)
    return {r.name: r for r in results}


async def test_a_create_only_target_passes_every_check_and_leaves_no_files(scratch: Path):
    target = tg.InMemoryBackupTarget()
    results = await run(target, scratch)
    assert list(results) == EXPECTED
    assert all(r.passed for r in results.values()), {n: r.detail for n, r in results.items() if not r.passed}
    assert sorted(target.objects) == [
        f"db/{RUN_ID}/plan-estimate.sql.gz.age",
        f"runs/{RUN_ID}/COMPLETE.json",
        f"runs/{RUN_ID}/manifest.jsonl",
        f"smoke/14d2f/{RUN_ID}/object.bin",
    ]
    assert list(scratch.iterdir()) == []
    sealed = mf.verify_run(target.objects[f"runs/{RUN_ID}/COMPLETE.json"], target.objects[f"runs/{RUN_ID}/manifest.jsonl"])
    assert sealed.manifest.summary.objects == 0


class OverwritingTarget(tg.InMemoryBackupTarget):
    """A broken target that replaces existing objects: the smoke must notice."""

    async def put_new(self, key, source, content_type):  # type: ignore[no-untyped-def]
        self.objects[key] = Path(source).read_bytes()
        return tg.PutOutcome.CREATED


async def test_a_target_that_overwrites_fails_the_conflict_checks(scratch: Path):
    results = await run(OverwritingTarget(), scratch)
    failed = {name for name, r in results.items() if not r.passed}
    assert "put_different_bytes_refused" in failed
    assert "republish_different_seal_refused" in failed


class DownTarget(tg.InMemoryBackupTarget):
    async def put_new(self, key, source, content_type):  # type: ignore[no-untyped-def]
        raise tg.MediaStorageUnavailable("down", error_code="ServiceUnavailable", http_status=503)


async def test_an_unavailable_target_fails_without_leaking_details(scratch: Path):
    results = await run(DownTarget(), scratch)
    assert not results["principal_and_put_created"].passed
    assert results["principal_and_put_created"].detail == "MediaStorageUnavailable (code=ServiceUnavailable, status=503)"
    assert not results["publish_run_zero_asset"].passed
    for name in ("stored_run_verifies", "stored_dump_matches", "republish_different_seal_refused", "seal_unchanged"):
        assert results[name].detail.startswith("skipped")
    assert list(scratch.iterdir()) == []


def test_report_format():
    report = smoke.format_report(
        [smoke.CheckResult("a", True, "ok"), smoke.CheckResult("b", False, "KeyError")], RUN_ID
    )
    assert report.endswith("RESULT: FAIL (1/2 checks passed)")
    assert RUN_ID in report and "PASS" in report and "KeyError" in report


def test_run_id_helper_matches_the_manifest_contract():
    assert mf.db_dump_key(new_run_id()).startswith("db/")


def test_main_refuses_non_drill_buckets_and_missing_namespace(capsys, monkeypatch):
    monkeypatch.delenv("OCI_NAMESPACE", raising=False)
    assert smoke.main(["--namespace", "ns", "--bucket", "plan-estimate-backup-prod"]) == smoke.EXIT_CANNOT_RUN
    assert "not a drill bucket" in capsys.readouterr().err
    assert smoke.main([]) == smoke.EXIT_CANNOT_RUN
    assert "--namespace" in capsys.readouterr().err


def test_main_reports_a_missing_instance_principal(monkeypatch, capsys):
    import sys
    import types

    def no_principal() -> None:
        raise ConnectionRefusedError("169.254.169.254 refused")

    fake = types.ModuleType("oci")
    fake.auth = types.SimpleNamespace(  # type: ignore[attr-defined]
        signers=types.SimpleNamespace(InstancePrincipalsSecurityTokenSigner=no_principal)
    )
    monkeypatch.setitem(sys.modules, "oci", fake)
    assert smoke.main(["--namespace", "ns"]) == smoke.EXIT_NO_PRINCIPAL
    out = capsys.readouterr().out
    assert "NOT obtainable" in out and "169.254" not in out


def test_main_distinguishes_a_missing_sdk_from_a_missing_principal(monkeypatch, capsys):
    import sys

    monkeypatch.setitem(sys.modules, "oci", None)
    assert smoke.main(["--namespace", "ns"]) == smoke.EXIT_CANNOT_RUN
    captured = capsys.readouterr()
    assert "oci==2.187.1" in captured.err and "NOT obtainable" not in captured.out
