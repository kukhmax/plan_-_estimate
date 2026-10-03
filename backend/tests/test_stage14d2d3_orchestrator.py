"""Stage 14D.2D.3 — backup orchestration sequencing and failure behaviour.

The real data root, lock, workspace, evidence and promotion code run on a
private temporary directory; the snapshot dump, metadata reader and
encryption are stand-ins (one test uses the real 14D.2B primitive with a
stand-in `age`). Nothing here proves real PostgreSQL or Compose behaviour
(14D.2D.4 / 14D.2D.5).
"""

import asyncio
import hashlib
import json
import os
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import app.backup.workspace as ws
from app.backup.evidence import ErrorCode, FailureStage
from app.backup.orchestrator import (
    BackupDependencies,
    BackupOrchestrator,
    BackupRunFailed,
    BackupRunSettings,
)
from app.backup.pg_connection import PgConnectionConfig
from app.backup.snapshot_metadata import SnapshotMetadata
from app.backup.workspace import EvidenceWriteError
from app.core.db_dump_encryption import (
    AgeFailedError,
    EncryptedDumpResult,
    PlaintextCleanupError,
    encrypt_dump_artifact,
)
from app.core.pg_snapshot_dump import PgDumpFailedError, SnapshotDumpResult
from app.domain.services.media_backup_ready_set import ReadyAsset, ready_set_digest

T0 = datetime(2026, 10, 3, 8, 15, 0, tzinfo=UTC)
SNAPSHOT = "00000003-0000001B-1"
TAG = "pe-snapshot-0123456789ab"
HEAD = "0032_photo_attachments"
RECIPIENT = "age1" + "q" * 58
FAKE_PASSWORD = "fakePwNeverLogged0123456789"
DUMP = b"--\n-- PostgreSQL database dump\n--\nSELECT 1;\n--\n-- PostgreSQL database dump complete\n--\n"
READY = ready_set_digest(
    [
        ReadyAsset(
            asset_id=__import__("uuid").UUID(int=i + 1),
            key_original=f"photos/v1/{i}/original.jpg",
            key_display=f"photos/v1/{i}/display.jpg",
            key_thumbnail=f"photos/v1/{i}/thumb.jpg",
            byte_size=100 + i,
            display_byte_size=50 + i,
            thumbnail_byte_size=10 + i,
            sha256=f"{i:064x}",
        )
        for i in range(3)
    ]
)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class Harness:
    """Stand-ins that record the order of events."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.events: list[str] = []
        self.observed_revision = HEAD
        self.dump_error: BaseException | None = None
        self.encrypt_mode = "ok"
        self.block_dump = False

    async def pg_dump_version(self, command) -> str:
        self.events.append("probe")
        return "pg_dump (PostgreSQL) 16.15 (Debian 16.15-1.pgdg13+2)"

    def resolve_head(self, location) -> str:
        self.events.append("resolve_head")
        assert not (self.root / "work").exists() or list((self.root / "work").iterdir()) == []
        return HEAD

    async def read_metadata(self, dsn: str, snapshot_id: str, session_tag: str) -> SnapshotMetadata:
        self.events.append(f"metadata:{snapshot_id}:{session_tag}")
        assert FAKE_PASSWORD not in dsn
        return SnapshotMetadata(
            database_name="plan_estimate",
            server_version="16.15",
            server_version_num=160015,
            alembic_revision=self.observed_revision,
            photo_asset_status_counts={"FAILED": 1, "PENDING": 1, "READY": 3},
        )

    async def snapshot_dump(self, dsn, command, output_path: Path, *, timeout_seconds, session_tag, after_export):
        self.events.append("export")
        await after_export(SNAPSHOT)
        self.events.append("ready_inventory")
        self.events.append("pg_dump")
        if self.block_dump:
            await asyncio.sleep(3600)
        if self.dump_error is not None:
            raise self.dump_error
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(DUMP)
        self.events.append("exporter_released")
        return SnapshotDumpResult(
            snapshot_id=SNAPSHOT,
            ready=READY,
            server_major_version=16,
            dump_path=output_path,
            dump_size=len(DUMP),
            dump_sha256=hashlib.sha256(DUMP).hexdigest(),
        )

    async def encrypt(self, dump: SnapshotDumpResult, recipients, *, age_binary, timeout_seconds):
        self.events.append("encrypt")
        self.encrypt_input = dump
        artifact = dump.dump_path.parent / "plan-estimate.sql.gz.age"
        if self.encrypt_mode == "age_fails":
            raise AgeFailedError("age exited with status 1", returncode=1, stderr_tail="age: boom")
        artifact.write_bytes(b"age-encryption.org/v1\nCIPHERTEXT")
        artifact.chmod(0o600)
        result = EncryptedDumpResult(
            artifact_path=artifact,
            artifact_size=artifact.stat().st_size,
            artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            plaintext_size=dump.dump_size,
            plaintext_sha256=dump.dump_sha256,
            recipients=tuple(recipients),
            age_version="v1.3.2",
        )
        if self.encrypt_mode == "cleanup_fails":
            raise PlaintextCleanupError("encrypted artifact is valid, but plaintext cleanup is incomplete", result=result)
        dump.dump_path.unlink()
        return result


def settings(root: Path, passfile: Path) -> BackupRunSettings:
    connection = PgConnectionConfig(
        host="postgres", port=5432, database="plan_estimate", user="pe_backup", passfile=passfile, sslmode="disable"
    )
    return BackupRunSettings(data_root=root, connection=connection, recipients=(RECIPIENT,))


def make(root: Path, tmp_path: Path, harness: Harness, **overrides: Any) -> BackupOrchestrator:
    passfile = tmp_path / "pgpass"
    passfile.write_text(f"postgres:5432:plan_estimate:pe_backup:{FAKE_PASSWORD}\n")
    passfile.chmod(0o600)
    config = settings(root, passfile)
    deps = BackupDependencies(
        snapshot_dump=harness.snapshot_dump,
        encrypt=harness.encrypt,
        read_metadata=harness.read_metadata,
        resolve_head=harness.resolve_head,
        pg_dump_version=harness.pg_dump_version,
        clock=Clock(),
        session_tag_factory=lambda: TAG,
        process_env=config.connection.libpq_env(),
    )
    for key, value in overrides.items():
        setattr(deps, key, value)
    return BackupOrchestrator(config, deps)


@pytest.fixture
def root(tmp_path) -> Path:
    path = tmp_path / "data"
    path.mkdir(mode=0o700)
    return path


def only_run_id(directory: Path) -> str:
    (entry,) = list(directory.iterdir())
    return entry.name.removesuffix(".failed.json")


def failure_doc(root: Path) -> dict:
    (path,) = list((root / "evidence").iterdir())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    return json.loads(path.read_bytes())


def assert_not_promoted(root: Path) -> None:
    assert list((root / "encrypted").iterdir()) == []


# --- success -----------------------------------------------------------------------------------


async def test_success_sequence_evidence_and_promotion(root, tmp_path):
    h = Harness(root)
    result = await make(root, tmp_path, h).run()
    assert h.events == [
        "probe", "resolve_head", "export", f"metadata:{SNAPSHOT}:{TAG}", "ready_inventory", "pg_dump",
        "exporter_released", "encrypt",
    ]
    run_dir = root / "encrypted" / result.run_id
    assert result.run_directory == run_dir
    assert list((root / "work").iterdir()) == [] and list((root / "evidence").iterdir()) == []
    assert sorted(p.name for p in run_dir.iterdir()) == ["local-run.json", "plan-estimate.sql.gz.age"]
    raw = (run_dir / "local-run.json").read_bytes()
    assert raw == result.evidence.to_canonical_json()
    assert stat.S_IMODE((run_dir / "local-run.json").stat().st_mode) == 0o600
    doc = json.loads(raw)
    assert doc["status"] == "complete" and doc["run_id"] == result.run_id
    assert doc["database"]["alembic_revision"] == doc["database"]["expected_alembic_head"] == HEAD
    assert doc["snapshot"] == {
        "method": "exported-snapshot", "ready_set_format": "plan-estimate/ready-set/v1", "ready_count": 3,
        "ready_set_sha256": READY.ready_set_sha256,
    }
    assert doc["dump"]["plaintext_sha256"] == hashlib.sha256(DUMP).hexdigest()
    assert doc["artifact"]["sha256"] == hashlib.sha256((run_dir / "plan-estimate.sql.gz.age").read_bytes()).hexdigest()
    assert doc["artifact"]["recipient_count"] == 1 and doc["diagnostics"] == {"snapshot_id": SNAPSHOT, "session_tag": TAG}
    assert doc["started_at"] < doc["snapshot_exported_at"] < doc["dump_completed_at"] < doc["completed_at"]
    assert h.encrypt_input.dump_path == root / "work" / result.run_id / "plan-estimate.sql"
    assert (root / "run.lock").exists()
    with ws.BackupDataRoot(root).acquire_lock():  # lock released
        pass


async def test_evidence_is_written_before_promotion(root, tmp_path, monkeypatch):
    h = Harness(root)
    real_promote = ws.BackupDataRoot.promote
    seen: dict = {}

    def promote(self, run_id):
        seen["evidence_present"] = (root / "work" / run_id / "local-run.json").is_file()
        seen["plaintext_gone"] = not (root / "work" / run_id / "plan-estimate.sql").exists()
        return real_promote(self, run_id)

    monkeypatch.setattr(ws.BackupDataRoot, "promote", promote)
    await make(root, tmp_path, h).run()
    assert seen == {"evidence_present": True, "plaintext_gone": True}


async def test_success_with_the_real_encryption_primitive(root, tmp_path):
    fake_age = tmp_path / "bin" / "age"
    fake_age.parent.mkdir()
    fake_age.write_text(
        f"#!{sys.executable}\nimport sys\nif sys.argv[1:] == ['--version']:\n    print('v1.3.2'); sys.exit(0)\n"
        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    )
    fake_age.chmod(0o700)
    h = Harness(root)
    orchestrator = make(root, tmp_path, h, encrypt=encrypt_dump_artifact)
    object.__setattr__(orchestrator.settings, "age_binary", str(fake_age))
    result = await orchestrator.run()
    artifact = root / "encrypted" / result.run_id / "plan-estimate.sql.gz.age"
    import gzip

    assert gzip.decompress(artifact.read_bytes()) == DUMP  # stand-in age = identity
    assert result.evidence.artifact.age_version == "v1.3.2"


# --- revision -------------------------------------------------------------------------------------


async def test_revision_mismatch_aborts_before_pg_dump(root, tmp_path):
    h = Harness(root)
    h.observed_revision = "0031_photo_assets"
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.SCHEMA_REVISION_MISMATCH and exc.value.stage is FailureStage.SCHEMA_REVISION
    assert "pg_dump" not in h.events and "ready_inventory" not in h.events and "encrypt" not in h.events
    assert_not_promoted(root)
    run_id = exc.value.run_id
    assert run_id and list((root / "work" / run_id).iterdir()) == []  # stays as stale work, nothing written
    doc = failure_doc(root)
    assert doc["failure"] == {
        "stage": "schema_revision", "error_code": "SCHEMA_REVISION_MISMATCH", "plaintext_retained": False,
        "artifact_valid": False, "partials_present": False,
    }


# --- dump / encryption failures ---------------------------------------------------------------------


async def test_dump_failure_never_encrypts(root, tmp_path):
    h = Harness(root)
    h.dump_error = PgDumpFailedError("pg_dump exited with status 1", returncode=1, stderr_tail=FAKE_PASSWORD)
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.PG_DUMP_FAILED and exc.value.stage is FailureStage.DUMP
    assert "encrypt" not in h.events
    assert_not_promoted(root)
    assert failure_doc(root)["failure"]["error_code"] == "PG_DUMP_FAILED"
    assert FAKE_PASSWORD.encode() not in (root / "evidence" / f"{exc.value.run_id}.failed.json").read_bytes()


async def test_encryption_failure_keeps_plaintext_and_does_not_promote(root, tmp_path):
    h = Harness(root)
    h.encrypt_mode = "age_fails"
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.AGE_FAILED and exc.value.stage is FailureStage.ENCRYPT
    run_dir = root / "work" / exc.value.run_id
    assert not (run_dir / "local-run.json").exists() and (run_dir / "plan-estimate.sql").exists()
    assert_not_promoted(root)
    assert failure_doc(root)["failure"] == {
        "stage": "encrypt", "error_code": "AGE_FAILED", "plaintext_retained": True, "artifact_valid": False,
        "partials_present": False,
    }


async def test_plaintext_cleanup_error_fails_the_run_with_valid_artifact(root, tmp_path):
    h = Harness(root)
    h.encrypt_mode = "cleanup_fails"
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.PLAINTEXT_CLEANUP_FAILED
    run_dir = root / "work" / exc.value.run_id
    assert (run_dir / "plan-estimate.sql.gz.age").exists() and not (run_dir / "local-run.json").exists()
    assert_not_promoted(root)
    failure = failure_doc(root)["failure"]
    assert failure["plaintext_retained"] is True and failure["artifact_valid"] is True


# --- evidence write failure ----------------------------------------------------------------------


async def test_complete_evidence_write_failure_does_not_promote(root, tmp_path, monkeypatch):
    h = Harness(root)

    def failing(self, run_id, data):
        raise EvidenceWriteError("local-run.json could not be written (EIO)")

    monkeypatch.setattr(ws.BackupDataRoot, "write_run_evidence", failing)
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.EVIDENCE_WRITE_FAILED and exc.value.stage is FailureStage.EVIDENCE
    run_dir = root / "work" / exc.value.run_id
    assert (run_dir / "plan-estimate.sql.gz.age").exists()
    assert_not_promoted(root)
    assert failure_doc(root)["failure"]["artifact_valid"] is True


async def test_failure_evidence_write_failure_keeps_the_original_failure(root, tmp_path, monkeypatch, caplog):
    h = Harness(root)
    h.dump_error = PgDumpFailedError("x", returncode=2, stderr_tail="")

    def failing(self, run_id, data):
        raise OSError("disk full")

    monkeypatch.setattr(ws.BackupDataRoot, "write_failure_evidence", failing)
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.PG_DUMP_FAILED
    assert list((root / "evidence").iterdir()) == []
    assert "OSError" in caplog.text and "disk full" not in caplog.text


# --- promotion -------------------------------------------------------------------------------------


@pytest.mark.parametrize("promoted", [False, True])
async def test_promotion_durability_failures(root, tmp_path, monkeypatch, promoted):
    h = Harness(root)
    calls = {"n": 0}
    real_promote = ws.BackupDataRoot.promote

    def promote(self, run_id):
        calls["n"] += 1
        if promoted:
            real_promote(self, run_id)
        raise ws.DurabilityError("simulated", promoted=promoted)

    monkeypatch.setattr(ws.BackupDataRoot, "promote", promote)
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert calls["n"] == 1  # never retried
    run_id = exc.value.run_id
    if promoted:
        assert exc.value.code is ErrorCode.PROMOTION_DURABILITY_UNCONFIRMED
        assert (root / "encrypted" / run_id / "local-run.json").exists()  # not moved back
        assert list((root / "work").iterdir()) == []
    else:
        assert exc.value.code is ErrorCode.PROMOTION_NOT_DURABLE
        assert (root / "work" / run_id).is_dir() and list((root / "encrypted").iterdir()) == []
    failure = failure_doc(root)["failure"]
    assert failure["stage"] == "promote" and failure["artifact_valid"] is True


# --- lock / stale / preflight ----------------------------------------------------------------------


async def test_lock_held_creates_nothing(root, tmp_path):
    h = Harness(root)
    ws.BackupDataRoot(root).prepare()
    with ws.BackupDataRoot(root).acquire_lock(), pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.LOCK_HELD and exc.value.run_id is None
    assert list((root / "work").iterdir()) == [] and list((root / "evidence").iterdir()) == []
    assert "export" not in h.events


async def test_stale_work_blocks_and_nothing_is_deleted(root, tmp_path):
    h = Harness(root)
    ws.BackupDataRoot(root).prepare()
    stale = root / "work" / "20261001T000000Z-deadbeef"
    stale.mkdir(mode=0o700)
    (stale / "plan-estimate.sql").write_text("old")
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h).run()
    assert exc.value.code is ErrorCode.STALE_WORK and exc.value.run_id is None
    assert (stale / "plan-estimate.sql").read_text() == "old"
    assert "resolve_head" not in h.events and list((root / "evidence").iterdir()) == []


async def test_process_env_mismatch_is_a_preflight_failure(root, tmp_path):
    h = Harness(root)
    orchestrator = make(root, tmp_path, h)
    orchestrator.deps.process_env = {**orchestrator.settings.connection.libpq_env(), "PGHOST": "other"}
    with pytest.raises(BackupRunFailed) as exc:
        await orchestrator.run()
    assert exc.value.code is ErrorCode.CONFIGURATION_INVALID and exc.value.stage is FailureStage.PREFLIGHT
    assert not (root / "run.lock").exists() and h.events == []


async def test_passfile_invalid_is_a_preflight_failure(root, tmp_path):
    h = Harness(root)
    orchestrator = make(root, tmp_path, h)
    orchestrator.settings.connection.passfile.chmod(0o644)
    with pytest.raises(BackupRunFailed) as exc:
        await orchestrator.run()
    assert exc.value.code is ErrorCode.PASSFILE_INVALID and exc.value.run_id is None
    assert FAKE_PASSWORD not in str(exc.value)


async def test_unresolvable_head_is_a_preflight_failure(root, tmp_path):
    from app.backup.schema_revision import ExpectedHeadError

    h = Harness(root)

    def no_head(location):
        raise ExpectedHeadError("repository must have exactly one Alembic head (found 2)")

    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h, resolve_head=no_head).run()
    assert exc.value.code is ErrorCode.SCHEMA_HEAD_UNRESOLVED and exc.value.run_id is None
    assert list((root / "work").iterdir()) == []


# --- cancellation ----------------------------------------------------------------------------------


async def test_cancellation_records_cancelled_and_releases_the_lock(root, tmp_path):
    h = Harness(root)
    h.block_dump = True
    task = asyncio.create_task(make(root, tmp_path, h).run())
    for _ in range(200):
        if "pg_dump" in h.events:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert_not_promoted(root)
    run_id = only_run_id(root / "work")
    doc = failure_doc(root)
    assert doc["run_id"] == run_id and doc["failure"]["error_code"] == "CANCELLED"
    with ws.BackupDataRoot(root).acquire_lock():
        pass


# --- secrets -----------------------------------------------------------------------------------


async def test_no_password_in_any_output_surface(root, tmp_path, caplog):
    h = Harness(root)
    result = await make(root, tmp_path, h).run()
    surfaces = [result.evidence.to_canonical_json().decode(), caplog.text, repr(result)]
    h2 = Harness(root)
    h2.dump_error = PgDumpFailedError(f"pg_dump: password {FAKE_PASSWORD}", returncode=1, stderr_tail=FAKE_PASSWORD)
    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h2).run()
    surfaces += [str(exc.value), json.dumps(failure_doc(root))]
    for text in surfaces:
        assert FAKE_PASSWORD not in text
