"""Stage 14D.2D.1 — local backup evidence v1 (pure)."""

import asyncio
import dataclasses
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.backup.evidence import (
    EMPTY_READY_SET_SHA256,
    FORMAT_COMPLETE,
    FORMAT_FAILED,
    ArtifactFacts,
    CompleteRunEvidence,
    DatabaseFacts,
    Diagnostics,
    DumpFacts,
    ErrorCode,
    EvidenceError,
    FailedRunEvidence,
    FailureStage,
    SnapshotFacts,
    canonical_json,
    error_code_for,
    format_timestamp,
    validate_snapshot_id,
)
from app.backup.pg_connection import PassfileError, PgConnectionConfigError
from app.backup.schema_revision import (
    ExpectedHeadError,
    ObservedRevisionError,
    SchemaRevisionMismatchError,
)
from app.core.db_dump_encryption import (
    AgeFailedError,
    PlaintextCleanupError,
    PlaintextIntegrityError,
)
from app.core.pg_snapshot_dump import (
    PgDumpFailedError,
    PgDumpTimeoutError,
    PgDumpVersionMismatchError,
)
from app.domain.services.media_backup_ready_set import (
    READY_SET_HEADER,
    ReadySetFormatError,
)

T0 = datetime(2026, 10, 3, 8, 15, 0, tzinfo=UTC)
RUN_ID = "20261003T081500Z-3f9a1c2e"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
READY_SHA = "d" * 64


def database(**overrides: Any) -> DatabaseFacts:
    values: dict[str, Any] = {
        "name": "plan_estimate",
        "server_version": "16.15",
        "server_version_num": 160015,
        "alembic_revision": "0032_photo_attachments",
        "expected_alembic_head": "0032_photo_attachments",
        "photo_asset_status_counts": {"READY": 3, "PENDING": 1, "FAILED": 1},
    }
    values.update(overrides)
    return DatabaseFacts(**values)


def complete(**overrides: Any) -> CompleteRunEvidence:
    values: dict[str, Any] = {
        "run_id": RUN_ID,
        "started_at": T0,
        "snapshot_exported_at": T0 + timedelta(seconds=2),
        "dump_completed_at": T0 + timedelta(seconds=30),
        "completed_at": T0 + timedelta(seconds=45),
        "database": database(),
        "snapshot": SnapshotFacts(ready_count=3, ready_set_sha256=READY_SHA),
        "dump": DumpFacts(
            pg_dump_version="pg_dump (PostgreSQL) 16.15 (Debian 16.15-1.pgdg13+2)",
            plaintext_sha256=SHA_A,
            plaintext_size=123456,
        ),
        "artifact": ArtifactFacts(sha256=SHA_B, size=23456, age_version="v1.3.2", recipient_count=1),
        "diagnostics": Diagnostics(snapshot_id="00000003-0000001B-1", session_tag="pe-snapshot-0123456789ab"),
    }
    values.update(overrides)
    return CompleteRunEvidence(**values)


def failed(**overrides: Any) -> FailedRunEvidence:
    values: dict[str, Any] = {
        "run_id": RUN_ID,
        "started_at": T0,
        "failed_at": T0 + timedelta(seconds=5),
        "stage": FailureStage.DUMP,
        "error_code": ErrorCode.PG_DUMP_FAILED,
        "plaintext_retained": False,
        "artifact_valid": False,
        "partials_present": False,
    }
    values.update(overrides)
    return FailedRunEvidence(**values)


# --- canonical serialization -----------------------------------------------------------------


def test_complete_evidence_canonical_bytes_are_stable():
    expected = (
        b'{"artifact":{"age_version":"v1.3.2","encryption":"age","name":"plan-estimate.sql.gz.age",'
        b'"recipient_count":1,"sha256":"' + SHA_B.encode() + b'","size":23456},'
        b'"completed_at":"2026-10-03T08:15:45Z",'
        b'"database":{"alembic_revision":"0032_photo_attachments","expected_alembic_head":"0032_photo_attachments",'
        b'"name":"plan_estimate","photo_asset_status_counts":{"FAILED":1,"PENDING":1,"READY":3},'
        b'"server_version":"16.15","server_version_num":160015},'
        b'"diagnostics":{"session_tag":"pe-snapshot-0123456789ab","snapshot_id":"00000003-0000001B-1"},'
        b'"dump":{"format":"plain","pg_dump_version":"pg_dump (PostgreSQL) 16.15 (Debian 16.15-1.pgdg13+2)",'
        b'"plaintext_sha256":"' + SHA_A.encode() + b'","plaintext_size":123456},'
        b'"dump_completed_at":"2026-10-03T08:15:30Z","format":"plan-estimate/local-db-backup/v1",'
        b'"run_id":"20261003T081500Z-3f9a1c2e",'
        b'"snapshot":{"method":"exported-snapshot","ready_count":3,"ready_set_format":"plan-estimate/ready-set/v1",'
        b'"ready_set_sha256":"' + READY_SHA.encode() + b'"},'
        b'"snapshot_exported_at":"2026-10-03T08:15:02Z","started_at":"2026-10-03T08:15:00Z","status":"complete"}\n'
    )
    assert complete().to_canonical_json() == expected


def test_canonical_json_is_byte_stable_sorted_ascii_and_newline_terminated():
    evidence = complete()
    first = evidence.to_canonical_json()
    assert first == complete().to_canonical_json() == evidence.to_canonical_json()
    assert first.endswith(b"\n") and first.count(b"\n") == 1
    assert first.isascii() and b" :" not in first and b", " not in first
    document = json.loads(first)
    assert list(document) == sorted(document)
    assert canonical_json(document) == first  # parse + re-serialize is identity


def test_canonical_json_escapes_non_ascii_and_refuses_nan():
    assert canonical_json({"b": "ż", "a": 1}) == b'{"a":1,"b":"\\u017c"}\n'
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_failed_evidence_canonical_bytes_are_stable():
    assert failed().to_canonical_json() == (
        b'{"failed_at":"2026-10-03T08:15:05Z","failure":{"artifact_valid":false,"error_code":"PG_DUMP_FAILED",'
        b'"partials_present":false,"plaintext_retained":false,"stage":"dump"},'
        b'"format":"plan-estimate/local-db-backup-failure/v1","run_id":"20261003T081500Z-3f9a1c2e",'
        b'"started_at":"2026-10-03T08:15:00Z","status":"failed"}\n'
    )


# --- schema / allowlist ------------------------------------------------------------------------


def all_keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | set().union(*(all_keys(v) for v in node.values()))
    return set()


def test_complete_and_failed_schemas_are_separate_and_allowlisted():
    complete_doc = complete().to_document()
    failed_doc = failed().to_document()
    assert complete_doc["format"] == FORMAT_COMPLETE and complete_doc["status"] == "complete"
    assert failed_doc["format"] == FORMAT_FAILED and failed_doc["status"] == "failed"
    assert set(failed_doc) == {"format", "status", "run_id", "started_at", "failed_at", "failure"}
    assert set(failed_doc["failure"]) == {
        "stage", "error_code", "plaintext_retained", "artifact_valid", "partials_present"
    }
    assert "artifact" not in failed_doc and "failure" not in complete_doc


FORBIDDEN_KEY_FRAGMENTS = (
    "password", "passfile", "secret", "token", "dsn", "url", "env", "identity", "private", "recipients",
    "stderr", "stdout", "message", "exception", "traceback", "path", "host", "user", "source_sha256", "tool",
)


@pytest.mark.parametrize("document", [complete().to_document(), failed().to_document()])
def test_no_secret_or_free_form_fields(document):
    for key in all_keys(document):
        assert not any(fragment in key.lower() for fragment in FORBIDDEN_KEY_FRAGMENTS), key


def test_failure_evidence_cannot_carry_free_form_text():
    fields = {f.name for f in dataclasses.fields(FailedRunEvidence)}
    assert fields == {
        "run_id", "started_at", "failed_at", "stage", "error_code", "plaintext_retained", "artifact_valid",
        "partials_present",
    }
    with pytest.raises(TypeError):
        failed(message="connection to postgresql://u:pw@h/db failed")  # type: ignore[call-arg]
    with pytest.raises(EvidenceError):
        failed(error_code="password authentication failed for user x")  # type: ignore[arg-type]
    with pytest.raises(EvidenceError):
        failed(stage="dump; rm -rf /")  # type: ignore[arg-type]
    for flag in ("plaintext_retained", "artifact_valid", "partials_present"):
        with pytest.raises(EvidenceError):
            failed(**{flag: "yes"})
        with pytest.raises(EvidenceError):
            failed(**{flag: 1})


def test_error_code_ignores_exception_text():
    secret = "postgresql://backup:S3cr3t@postgres/db stderr: FATAL password authentication failed"
    exc = PgDumpFailedError(secret, returncode=1, stderr_tail=secret)
    code = error_code_for(exc)
    assert code is ErrorCode.PG_DUMP_FAILED
    document = failed(error_code=code).to_canonical_json()
    assert b"S3cr3t" not in document and b"FATAL" not in document


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (PassfileError("x"), ErrorCode.PASSFILE_INVALID),
        (PgConnectionConfigError("x"), ErrorCode.CONFIGURATION_INVALID),
        (ExpectedHeadError("x"), ErrorCode.SCHEMA_HEAD_UNRESOLVED),
        (SchemaRevisionMismatchError("0031_a", "0032_b"), ErrorCode.SCHEMA_REVISION_MISMATCH),
        (ObservedRevisionError("x"), ErrorCode.SCHEMA_REVISION_INVALID),
        (ReadySetFormatError("x"), ErrorCode.READY_SET_INVALID),
        (PgDumpVersionMismatchError("x"), ErrorCode.PG_DUMP_VERSION_MISMATCH),
        (PgDumpTimeoutError("x"), ErrorCode.PG_DUMP_TIMEOUT),
        (AgeFailedError("x", returncode=1, stderr_tail="t"), ErrorCode.AGE_FAILED),
        (PlaintextIntegrityError("x"), ErrorCode.PLAINTEXT_INTEGRITY),
        (asyncio.CancelledError(), ErrorCode.CANCELLED),
        (RuntimeError("anything"), ErrorCode.UNEXPECTED_ERROR),
        (KeyError("x"), ErrorCode.UNEXPECTED_ERROR),
    ],
)
def test_error_codes_are_mapped_by_type(exc, code):
    assert error_code_for(exc) is code


def test_plaintext_cleanup_error_has_its_own_code():
    class FakeResult:
        pass

    assert error_code_for(PlaintextCleanupError("x", result=FakeResult())) is ErrorCode.PLAINTEXT_CLEANUP_FAILED  # type: ignore[arg-type]


# --- field validation --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["", "A" * 64, "a" * 63, "a" * 65, "g" * 64, " " + "a" * 63, None, 0, b"a" * 64]
)
def test_sha256_fields_are_validated(value):
    with pytest.raises(EvidenceError):
        complete(artifact=ArtifactFacts(sha256=value, size=1, age_version="v1.3.2", recipient_count=1))
    with pytest.raises(EvidenceError):
        DumpFacts(pg_dump_version="pg_dump (PostgreSQL) 16.15", plaintext_sha256=value, plaintext_size=1)


def test_ready_digest_must_match_the_count():
    assert EMPTY_READY_SET_SHA256 == hashlib.sha256(READY_SET_HEADER).hexdigest()
    assert EMPTY_READY_SET_SHA256 == "6e2b1178c1af4635f75bd0c77e7cce463e0e7055c120984e99ccf2d5a4922240"
    SnapshotFacts(ready_count=0, ready_set_sha256=EMPTY_READY_SET_SHA256)
    with pytest.raises(EvidenceError):
        SnapshotFacts(ready_count=0, ready_set_sha256=READY_SHA)
    with pytest.raises(EvidenceError):
        SnapshotFacts(ready_count=2, ready_set_sha256=EMPTY_READY_SET_SHA256)
    with pytest.raises(EvidenceError):
        SnapshotFacts(ready_count=1, ready_set_sha256="D" * 64)


def test_ready_count_must_equal_ready_status_count():
    with pytest.raises(EvidenceError, match="same snapshot"):
        complete(snapshot=SnapshotFacts(ready_count=2, ready_set_sha256=READY_SHA))


@pytest.mark.parametrize("value", [-1, True, False, 1.0, "3", None, 2**53, "\uff13"])
def test_integer_fields_reject_non_integers_and_out_of_range(value):
    with pytest.raises(EvidenceError):
        SnapshotFacts(ready_count=value, ready_set_sha256=READY_SHA)


@pytest.mark.parametrize("value", [0, -5, True, 1.5])
def test_sizes_must_be_positive_integers(value):
    with pytest.raises(EvidenceError):
        ArtifactFacts(sha256=SHA_B, size=value, age_version="v1.3.2", recipient_count=1)
    with pytest.raises(EvidenceError):
        DumpFacts(pg_dump_version="pg_dump (PostgreSQL) 16.15", plaintext_sha256=SHA_A, plaintext_size=value)


@pytest.mark.parametrize(("count", "ok"), [(0, False), (1, True), (2, True), (32, True), (33, False), (True, False)])
def test_recipient_count_bounds(count, ok):
    if ok:
        ArtifactFacts(sha256=SHA_B, size=1, age_version="v1.3.2", recipient_count=count)
    else:
        with pytest.raises(EvidenceError):
            ArtifactFacts(sha256=SHA_B, size=1, age_version="v1.3.2", recipient_count=count)


@pytest.mark.parametrize("version", ["", "1.3", "age 1.3.2", "v1.3.2\n", "x" * 70, "(devel)"])
def test_age_version_is_validated(version):
    with pytest.raises(EvidenceError):
        ArtifactFacts(sha256=SHA_B, size=1, age_version=version, recipient_count=1)


@pytest.mark.parametrize(
    "version", ["", "16.15", "psql (PostgreSQL) 16.15", "pg_dump (PostgreSQL) 16.15\n", "pg_dump (PostgreSQL) " + "x" * 200]
)
def test_pg_dump_version_is_validated_and_capped(version):
    with pytest.raises(EvidenceError):
        DumpFacts(pg_dump_version=version, plaintext_sha256=SHA_A, plaintext_size=1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "db name"},
        {"name": "x" * 64},
        {"name": "db\nname"},
        {"server_version": "sixteen"},
        {"server_version": "16.15 " + "x" * 80},
        {"server_version_num": 99999},
        {"server_version_num": "160015"},
        {"alembic_revision": "0031_photo_assets"},  # mismatch cannot be a complete run
        {"alembic_revision": "bad id"},
        {"expected_alembic_head": ""},
        {"photo_asset_status_counts": {"READY": 3, "PENDING": 1}},
        {"photo_asset_status_counts": {"READY": 3, "PENDING": 1, "FAILED": 1, "DELETED": 0}},
        {"photo_asset_status_counts": {"READY": 3, "PENDING": -1, "FAILED": 1}},
    ],
)
def test_database_facts_are_validated(overrides):
    with pytest.raises(EvidenceError):
        database(**overrides)


def test_server_versions_seen_in_practice_are_accepted():
    for version in ("16.15", "16.15 (Debian 16.15-1.pgdg13+2)", "17.2", "16beta1"):
        if version == "16beta1":
            with pytest.raises(EvidenceError):
                database(server_version=version)
        else:
            database(server_version=version)


def test_timestamps_must_be_aware_and_ordered():
    assert format_timestamp(datetime(2026, 10, 3, 10, 15, 0, 999, tzinfo=UTC)) == "2026-10-03T10:15:00Z"
    with pytest.raises(EvidenceError):
        format_timestamp(datetime(2026, 10, 3, 10, 15))  # noqa: DTZ001 - naive on purpose
    with pytest.raises(EvidenceError):
        complete(started_at=datetime(2026, 10, 3, 8, 15))  # noqa: DTZ001 - naive on purpose
    with pytest.raises(EvidenceError):
        complete(completed_at=T0 + timedelta(seconds=1))  # before dump_completed_at
    with pytest.raises(EvidenceError):
        failed(failed_at=T0 - timedelta(seconds=1))
    with pytest.raises(EvidenceError):
        complete(started_at="2026-10-03T08:15:00Z")  # type: ignore[arg-type]


def test_run_id_is_validated_without_echo():
    for bad in ("../x", "20261003T081500Z-3F9A1C2E", ""):
        with pytest.raises(EvidenceError) as exc:
            complete(run_id=bad)
        assert bad == "" or bad not in str(exc.value)
        with pytest.raises(EvidenceError):
            failed(run_id=bad)


@pytest.mark.parametrize(
    "snapshot_id",
    ["", "00000003-0000001b-1", "00000003-0000001B", "00000003-0000001B-1'; DROP TABLE x; --",
     "00000003-0000001B-1 ", "1-2-3\n", "0" * 17 + "-1-1", "1-1-" + "9" * 11],
)
def test_snapshot_id_is_strictly_validated(snapshot_id):
    with pytest.raises(EvidenceError):
        validate_snapshot_id(snapshot_id)


def test_valid_snapshot_ids_and_session_tags():
    assert validate_snapshot_id("00000003-0000001B-1") == "00000003-0000001B-1"
    Diagnostics(snapshot_id="00000003-0000001B-1", session_tag="pe-snapshot-0123456789ab")
    for tag in ("short", "UPPER-case-tag-123", "x" * 41, "tag with space", "pe-snapshot-ab_cd"):
        with pytest.raises(EvidenceError):
            Diagnostics(snapshot_id="00000003-0000001B-1", session_tag=tag)


def test_nested_facts_must_have_the_right_types():
    with pytest.raises(EvidenceError):
        complete(dump={"pg_dump_version": "x"})  # type: ignore[arg-type]
