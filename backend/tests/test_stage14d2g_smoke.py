"""Stage 14D.2G — logic of the live media-sync smoke, exercised on in-memory stores."""

import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.backup import target as tg
from app.domain.exceptions import MediaStorageUnavailable
from app.domain.services.media_storage import InMemoryMediaStorage
from scripts import stage14d2g_media_sync_smoke as smoke

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
NO_RETRY = tg.RetryPolicy(max_attempts=1, base_delay=0.0)
BUCKET_SOURCE, BUCKET_TARGET = "plan-estimate-media-drill-source", "plan-estimate-backup-drill"
ENDPOINT = "https://" + "0123456789abcdef" * 2 + ".eu.r2.cloudflarestorage.com"
NAMES = [
    "run1_copies_all",
    "run1_publishes_and_verifies",
    "run2_inherits_without_any_download",
    "run2_publishes_with_inherited_provenance",
    "run3_deep_verifies_by_download",
    "run4_reports_exactly_the_planted_failures",
    "run4_cannot_be_published",
    "conflicting_target_object_unchanged",
    "refused_objects_not_created",
    "source_listing_counts",
    "report_is_secret_free",
]


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


async def run(source: InMemoryMediaStorage, target: tg.InMemoryBackupTarget, scratch: Path) -> smoke.SmokeOutcome:
    return await smoke.run_checks(
        source,
        target,
        scratch,
        now=NOW,
        source_bucket=BUCKET_SOURCE,
        target_bucket=BUCKET_TARGET,
        uploaded=[],
        retry=NO_RETRY,
    )


def failed(outcome: smoke.SmokeOutcome) -> dict[str, str]:
    return {r.name: r.detail for r in outcome.results if not r.passed}


async def test_a_create_only_target_passes_every_check(scratch: Path):
    source, target = InMemoryMediaStorage(), tg.InMemoryBackupTarget()
    outcome = await run(source, target, scratch)
    assert [r.name for r in outcome.results] == NAMES
    assert failed(outcome) == {}
    assert len(outcome.uploaded_keys) == 9 + 8 + smoke.JUNK_KEYS and len(outcome.asset_prefixes) == 6
    assert len(outcome.run_ids) == 4 and outcome.run_ids == sorted(set(outcome.run_ids))
    assert list(scratch.iterdir()) == []


async def test_the_baseline_of_a_non_empty_source_bucket_is_accounted_for(scratch: Path):
    source, target = InMemoryMediaStorage(), tg.InMemoryBackupTarget()
    for n in range(5):
        path = scratch / f"seed{n}"
        path.write_bytes(b"leftover-from-another-drill")
        await source.put_object(f"photos/v1/00000000-0000-4000-8000-00000000000{n}/original.jpg", path, "image/jpeg")
        path.unlink()
    outcome = await run(source, target, scratch)
    assert failed(outcome) == {}


async def test_no_key_is_ever_written_twice(scratch: Path):
    """The engine checks before it writes: an object that exists is verified or refused, never put over."""
    target = tg.InMemoryBackupTarget()
    outcome = await run(InMemoryMediaStorage(), target, scratch)
    assert failed(outcome) == {}
    puts = [key for op, key in target.calls if op == "put_new"]
    assert puts and len(puts) == len(set(puts))


async def test_the_runs_leave_exactly_the_expected_objects_in_the_target(scratch: Path):
    source, target = InMemoryMediaStorage(), tg.InMemoryBackupTarget()
    outcome = await run(source, target, scratch)
    keys = sorted(target.objects)
    for run_id in outcome.run_ids[:2]:
        assert f"db/{run_id}/plan-estimate.sql.gz.age" in keys
        assert f"runs/{run_id}/manifest.jsonl" in keys and f"runs/{run_id}/COMPLETE.json" in keys
    for run_id in outcome.run_ids[2:]:
        assert not [key for key in keys if run_id in key], "deep and failed runs publish nothing"
    photos = [key for key in keys if key.startswith("photos/v1/")]
    # 9 good + (missing: original + thumb) 2 + (bad sha: display + thumb) 2 + (conflict: planted display + original + thumb) 3
    assert len(photos) == 16


class DownTarget(tg.InMemoryBackupTarget):
    async def put_new(self, key, source, content_type):  # type: ignore[no-untyped-def]
        raise MediaStorageUnavailable("down", error_code="ServiceUnavailable", http_status=503)


async def test_a_target_that_cannot_be_written_stops_the_smoke_during_setup(scratch: Path):
    # the planted conflict needs one working create: the failure propagates instead of reporting misleading checks
    with pytest.raises(MediaStorageUnavailable):
        await run(InMemoryMediaStorage(), DownTarget(), scratch)
    assert list(scratch.iterdir()) == []


class CorruptingTarget(tg.InMemoryBackupTarget):
    """Stores every thumbnail with a flipped byte: post-copy verification must fail."""

    async def put_new(self, key, source, content_type):  # type: ignore[no-untyped-def]
        if key.endswith("thumb.jpg"):
            self.corrupt_on_store.add(key)
        return await super().put_new(key, source, content_type)


async def test_later_checks_are_skipped_after_a_failure(scratch: Path):
    outcome = await run(InMemoryMediaStorage(), CorruptingTarget(), scratch)
    results = {r.name: r for r in outcome.results}
    assert [r.name for r in outcome.results] == NAMES
    assert not results["run1_copies_all"].passed
    assert all(r.detail.startswith("skipped") for name, r in results.items() if name != "run1_copies_all")
    assert list(scratch.iterdir()) == []


def test_report_format(scratch: Path):
    outcome = smoke.SmokeOutcome(
        [smoke.CheckResult("a", True, "ok"), smoke.CheckResult("b", False, "KeyError")],
        ["k"],
        ["photos/v1/x/"],
        ["20261004T120000Z-0123abcd"],
    )
    report = smoke.format_report(outcome)
    assert report.endswith("RESULT: FAIL (1/2 checks passed)")
    assert "photos/v1/x/" in report and "20261004T120000Z-0123abcd" in report and "KeyError" in report


# --- configuration -------------------------------------------------------------------------------------------


def good_env(**overrides: str) -> dict[str, str]:
    env = {
        "R2_ENDPOINT_URL": ENDPOINT,
        "R2_ACCESS_KEY_ID": "id",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_BUCKET": BUCKET_SOURCE,
        "OCI_NAMESPACE": "ns",
    }
    env.update(overrides)
    return env


def test_load_r2_config_accepts_a_drill_bucket_and_hides_credentials():
    config = smoke.load_r2_config(good_env())
    assert config.bucket == BUCKET_SOURCE
    assert "secret" not in repr(config) and "id" not in repr(config).replace("bucket", "")


@pytest.mark.parametrize(
    "overrides",
    [
        {"R2_ENDPOINT_URL": "https://abc.r2.cloudflarestorage.com"},
        {"R2_ENDPOINT_URL": "http://" + "0123456789abcdef" * 2 + ".eu.r2.cloudflarestorage.com"},
        {"R2_ACCESS_KEY_ID": ""},
        {"R2_SECRET_ACCESS_KEY": ""},
        {"R2_BUCKET": "plan-estimate-media-prod"},
        {"R2_BUCKET": "Bad_Name"},
    ],
)
def test_load_r2_config_refuses_unsafe_configuration(overrides: dict[str, str]):
    with pytest.raises(ValueError) as excinfo:
        smoke.load_r2_config(good_env(**overrides))
    assert "secret" not in str(excinfo.value)


def test_main_refuses_non_drill_buckets_and_missing_inputs(capsys: pytest.CaptureFixture[str]):
    assert smoke.main(["--namespace", "ns", "--bucket", "plan-estimate-backup-prod"], good_env()) == smoke.EXIT_CANNOT_RUN
    assert "not a drill bucket" in capsys.readouterr().err
    assert smoke.main([], {**good_env(), "OCI_NAMESPACE": ""}) == smoke.EXIT_CANNOT_RUN
    assert "--namespace" in capsys.readouterr().err
    assert smoke.main(["--namespace", "ns"], good_env(R2_BUCKET="plan-estimate-media-prod")) == smoke.EXIT_CANNOT_RUN
    assert "drill" in capsys.readouterr().err
    assert smoke.main(["--namespace", "ns", "--bucket", BUCKET_SOURCE], good_env()) == smoke.EXIT_CANNOT_RUN
    assert "must differ" in capsys.readouterr().err


def test_main_reports_a_missing_instance_principal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    def no_principal() -> None:
        raise ConnectionRefusedError("169.254.169.254 refused")

    fake = types.ModuleType("oci")
    fake.auth = types.SimpleNamespace(  # type: ignore[attr-defined]
        signers=types.SimpleNamespace(InstancePrincipalsSecurityTokenSigner=no_principal)
    )
    monkeypatch.setitem(sys.modules, "oci", fake)
    pytest.importorskip("boto3")
    assert smoke.main(["--namespace", "ns"], good_env()) == smoke.EXIT_NO_PRINCIPAL
    out = capsys.readouterr().out
    assert "NOT obtainable" in out and "169.254" not in out


def test_main_distinguishes_a_missing_sdk_from_a_missing_principal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    pytest.importorskip("boto3")
    monkeypatch.setitem(sys.modules, "oci", None)
    assert smoke.main(["--namespace", "ns"], good_env()) == smoke.EXIT_CANNOT_RUN
    captured = capsys.readouterr()
    assert "oci==2.187.1" in captured.err and "NOT obtainable" not in captured.out
