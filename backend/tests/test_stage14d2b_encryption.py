"""Stage 14D.2B — encrypted database artifact primitive (local, no real age).

`encrypt_dump_artifact` is exercised against a stand-in `age` executable (a
small Python script) whose behaviour each test chooses: copy stdin to stdout
(so the "artifact" is exactly the gzip stream and can be inspected), exit
non-zero, hang, stop reading, record argv / environment. Real encryption and
decryption with disposable identities is proven in
test_stage14d2b_age_roundtrip.py (opt-in, needs the age CLI).
"""

import asyncio
import gzip
import hashlib
import json
import os
import stat
import sys
import tracemalloc
import zlib
from pathlib import Path

import pytest

import app.core.db_dump_encryption as enc
from app.core.db_dump_encryption import (
    ENCRYPTED_DUMP_NAME,
    AgeFailedError,
    AgeRecipientError,
    AgeToolError,
    ArtifactCollisionError,
    ArtifactFinalizeError,
    CompressionError,
    EncryptTimeoutError,
    InsufficientSpaceError,
    PlaintextCleanupError,
    PlaintextIntegrityError,
    UnsafeWorkPathError,
    age_encrypt_argv,
    encrypt_dump_artifact,
    parse_age_recipients,
    parse_age_version,
)
from app.core.pg_snapshot_dump import SnapshotDumpResult
from app.domain.services.media_backup_ready_set import ready_set_digest

# Syntactically valid native X25519 recipients (bech32 charset, 58 chars);
# they are public values, never paired with a committed identity.
R1 = "age1" + "q" * 58
R2 = "age1" + "p" * 58
SQL = b"--\n-- PostgreSQL database dump\n--\n" + b"INSERT INTO t VALUES (1, 'x');\n" * 5000 + (
    b"--\n-- PostgreSQL database dump complete\n--\n"
)
SECRET_SENTINEL = "PE_TEST_SECRET_SENTINEL"


# --- helpers ---------------------------------------------------------------------------


def child_pids() -> list[int]:
    """Direct children of this process (any state, zombies included)."""
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(fields[1]) == os.getpid():
            found.append(int(entry))
    return found


def fake_age(tmp_path: Path, body: str, version: str = "v1.2.1", name: str = "age") -> str:
    """A stand-in age binary. `body` runs for encryption; `--version` prints
    `version` (or the body handles it when version is None)."""
    script = tmp_path / "bin" / name
    script.parent.mkdir(exist_ok=True)
    version_code = (
        f"if sys.argv[1:] == ['--version']:\n    print({version!r}); sys.exit(0)\n" if version is not None else ""
    )
    script.write_text(f"#!{sys.executable}\nimport os, sys, time\n{version_code}{body}\n")
    script.chmod(0o700)
    return str(script)


COPY = (
    "while True:\n"
    "    b = sys.stdin.buffer.read(65536)\n"
    "    if not b: break\n"
    "    sys.stdout.buffer.write(b)\n"
    "sys.stdout.flush()"
)


def make_dump(tmp_path: Path, data: bytes = SQL, mode: int = 0o600, name: str = "plan-estimate.sql") -> SnapshotDumpResult:
    work = tmp_path / "run"
    work.mkdir(mode=0o700, exist_ok=True)
    work.chmod(0o700)
    path = work / name
    path.write_bytes(data)
    path.chmod(mode)
    return SnapshotDumpResult(
        snapshot_id="00000003-0000001B-1",
        ready=ready_set_digest([]),
        server_major_version=16,
        dump_path=path,
        dump_size=len(data),
        dump_sha256=hashlib.sha256(data).hexdigest(),
    )


def artifact(dump: SnapshotDumpResult) -> Path:
    return dump.dump_path.parent / ENCRYPTED_DUMP_NAME


def partial(dump: SnapshotDumpResult) -> Path:
    return dump.dump_path.parent / (ENCRYPTED_DUMP_NAME + ".partial")


def assert_failed_cleanly(dump: SnapshotDumpResult, original: bytes = SQL) -> None:
    assert dump.dump_path.read_bytes() == original
    assert stat.S_IMODE(dump.dump_path.stat().st_mode) == 0o600
    assert not artifact(dump).exists()
    assert not partial(dump).exists()
    assert child_pids() == []


# --- recipients / argv / version ---------------------------------------------------------


def test_recipients_parse_split_and_dedupe():
    assert parse_age_recipients(f" {R1}, {R2}\n{R1} ") == (R1, R2)
    assert parse_age_recipients([R2, R1]) == (R2, R1)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ,  ",
        "age1short",
        "age1" + "b" * 58,  # 'b' is not in the bech32 charset
        "AGE1" + "Q" * 58,
        "age1yubikey1" + "q" * 50,  # plugin recipient
        "age1" + "q" * 59,
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample",
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ",
        "ecdsa-sha2-nistp256 AAAAE2VjZHNh",
    ],
)
def test_recipients_reject_non_native_values(value):
    with pytest.raises(AgeRecipientError):
        parse_age_recipients(value)


def test_secret_shaped_recipient_is_rejected_without_echoing_it(caplog):
    secret = "AGE-SECRET-KEY-1" + "Q" * 58
    with pytest.raises(AgeRecipientError) as exc:
        parse_age_recipients([R1, secret])
    assert "PRIVATE" in str(exc.value) and "#2" in str(exc.value)
    assert secret not in str(exc.value) and "Q" * 10 not in str(exc.value)
    assert secret not in caplog.text


def test_malformed_recipient_error_does_not_echo_value():
    value = "age1" + "b" * 58
    with pytest.raises(AgeRecipientError) as exc:
        parse_age_recipients(value)
    assert value not in str(exc.value)


def test_argv_is_encryption_only():
    argv = age_encrypt_argv("/usr/bin/age", (R1, R2))
    assert argv == ["/usr/bin/age", "--encrypt", "--recipient", R1, "--recipient", R2]
    forbidden = {"-d", "--decrypt", "-i", "--identity", "-p", "--passphrase", "-a", "--armor", "-o", "--output", "-R"}
    assert forbidden.isdisjoint(argv)


@pytest.mark.parametrize("output", ["v1.2.1\n", "1.1.1\n", "v1.3.0-rc.1\n", "v1.2.1+dirty\n"])
def test_parse_age_version(output):
    assert parse_age_version(output) == output.strip()


@pytest.mark.parametrize("output", ["", "(devel)", "age version unknown", "v1.2"])
def test_parse_age_version_rejects_unknown(output):
    with pytest.raises(AgeToolError):
        parse_age_version(output)


# --- success path ------------------------------------------------------------------------


async def test_success_produces_gzip_artifact_and_removes_plaintext(tmp_path):
    dump = make_dump(tmp_path)
    result = await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    final = artifact(dump)
    data = final.read_bytes()
    assert result.artifact_path == final
    assert result.artifact_size == len(data) == final.stat().st_size
    assert result.artifact_sha256 == hashlib.sha256(data).hexdigest()
    assert result.plaintext_size == len(SQL)
    assert result.plaintext_sha256 == hashlib.sha256(SQL).hexdigest()
    assert result.recipients == (R1,)
    assert result.age_version == "v1.2.1"
    assert gzip.decompress(data) == SQL
    assert not dump.dump_path.exists()
    assert not partial(dump).exists()
    assert child_pids() == []
    # no .gz (or any other) intermediate file
    assert sorted(p.name for p in final.parent.iterdir()) == [ENCRYPTED_DUMP_NAME]


async def test_gzip_header_has_no_name_comment_or_time_and_no_path(tmp_path):
    dump = make_dump(tmp_path, name="secret-host-path-dump.sql")
    await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    data = artifact(dump).read_bytes()  # fake age = identity, so this is the gzip stream
    assert data[:3] == b"\x1f\x8b\x08"
    flg = data[3]
    assert flg & 0b00011110 == 0  # no FEXTRA / FNAME / FCOMMENT / FHCRC
    assert data[4:8] == b"\x00\x00\x00\x00"  # MTIME == 0
    for leak in (b"secret-host-path-dump", str(tmp_path).encode(), os.uname().nodename.encode()):
        assert leak not in data
    # exactly one member, CRC32 / ISIZE validated by the decompressor
    d = zlib.decompressobj(31)
    assert d.decompress(data) == SQL and d.eof and d.unused_data == b""


async def test_final_and_partial_are_private_under_permissive_umask(tmp_path):
    dump = make_dump(tmp_path)
    marker = tmp_path / "partial-mode"
    body = (
        f"import stat\np = {str(partial(dump))!r}\n"
        f"open({str(marker)!r}, 'w').write(oct(stat.S_IMODE(os.stat(p).st_mode)))\n" + COPY
    )
    binary = fake_age(tmp_path, body)
    old = os.umask(0)
    try:
        await encrypt_dump_artifact(dump, R1, age_binary=binary, timeout_seconds=30)
    finally:
        os.umask(old)
    assert marker.read_text() == "0o600"
    assert stat.S_IMODE(artifact(dump).stat().st_mode) == 0o600


@pytest.mark.parametrize("umask", [0o000, 0o002, 0o022, 0o277])
async def test_final_mode_is_0600_for_any_umask(tmp_path, umask):
    dump = make_dump(tmp_path)
    binary = fake_age(tmp_path, COPY)
    old = os.umask(umask)
    try:
        await encrypt_dump_artifact(dump, R1, age_binary=binary, timeout_seconds=30)
    finally:
        os.umask(old)
    assert stat.S_IMODE(artifact(dump).stat().st_mode) == 0o600


async def test_child_environment_is_minimal_and_argv_encryption_only(tmp_path, monkeypatch):
    monkeypatch.setenv(SECRET_SENTINEL, "do-not-leak")
    monkeypatch.setenv("MEDIA_S3_SECRET_ACCESS_KEY", "do-not-leak")
    dump = make_dump(tmp_path)
    record = tmp_path / "record"
    body = (
        f"import json\njson.dump({{'argv': sys.argv[1:], 'env': dict(os.environ)}}, open({str(record)!r}, 'w'))\n"
        + COPY
    )
    await encrypt_dump_artifact(dump, [R1, R2], age_binary=fake_age(tmp_path, body), timeout_seconds=30)
    seen = json.loads(record.read_text())
    assert seen["argv"] == ["--encrypt", "--recipient", R1, "--recipient", R2]
    assert SECRET_SENTINEL not in seen["env"] and "MEDIA_S3_SECRET_ACCESS_KEY" not in seen["env"]
    assert set(seen["env"]) <= {"PATH", "LC_ALL", "LC_CTYPE", "PWD", "SHLVL", "_"}


# --- collisions --------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["final", "partial"])
async def test_existing_output_is_never_overwritten(tmp_path, which):
    dump = make_dump(tmp_path)
    existing = artifact(dump) if which == "final" else partial(dump)
    existing.write_bytes(b"pre-existing")
    with pytest.raises(ArtifactCollisionError) as exc:
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert existing.read_bytes() == b"pre-existing"  # untouched, not removed
    assert dump.dump_path.read_bytes() == SQL
    assert str(tmp_path) not in str(exc.value)  # names only


async def test_existing_partial_symlink_is_a_collision(tmp_path):
    dump = make_dump(tmp_path)
    target = tmp_path / "elsewhere"
    partial(dump).symlink_to(target)
    with pytest.raises(ArtifactCollisionError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert partial(dump).is_symlink() and not target.exists()


# --- failures: plaintext retained, partial removed, child reaped -----------------------------


async def test_age_nonzero_exit(tmp_path):
    dump = make_dump(tmp_path)
    body = "sys.stdin.buffer.read(); sys.stdout.write('junk'); sys.stderr.write('age: error: boom'); sys.exit(3)"
    with pytest.raises(AgeFailedError) as exc:
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, body), timeout_seconds=30)
    assert exc.value.returncode == 3 and "boom" in exc.value.stderr_tail
    assert exc.value.plaintext_retained
    assert_failed_cleanly(dump)


async def test_age_exiting_without_reading_input_fails(tmp_path):
    dump = make_dump(tmp_path, data=os.urandom(4 * 1024 * 1024))
    original = dump.dump_path.read_bytes()
    with pytest.raises(AgeFailedError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, "sys.exit(0)"), timeout_seconds=30)
    assert_failed_cleanly(dump, original)


async def test_age_zero_exit_with_empty_output_fails(tmp_path):
    dump = make_dump(tmp_path)
    with pytest.raises(ArtifactFinalizeError):
        await encrypt_dump_artifact(
            dump, R1, age_binary=fake_age(tmp_path, "sys.stdin.buffer.read()"), timeout_seconds=30
        )
    assert_failed_cleanly(dump)


async def test_stderr_tail_is_bounded(tmp_path):
    dump = make_dump(tmp_path)
    body = "sys.stdin.buffer.read(); sys.stderr.write('x' * 200000 + 'END'); sys.exit(1)"
    with pytest.raises(AgeFailedError) as exc:
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, body), timeout_seconds=30)
    assert len(exc.value.stderr_tail) <= enc.STDERR_TAIL_BYTES and exc.value.stderr_tail.endswith("END")


async def test_missing_age_binary(tmp_path):
    dump = make_dump(tmp_path)
    for binary in (str(tmp_path / "nope" / "age"), "pe-no-such-age-binary"):
        with pytest.raises(AgeToolError):
            await encrypt_dump_artifact(dump, R1, age_binary=binary, timeout_seconds=30)
        assert_failed_cleanly(dump)


async def test_non_executable_age_binary(tmp_path):
    dump = make_dump(tmp_path)
    binary = fake_age(tmp_path, COPY)
    os.chmod(binary, 0o600)
    with pytest.raises(AgeToolError):
        await encrypt_dump_artifact(dump, R1, age_binary=binary, timeout_seconds=30)
    assert_failed_cleanly(dump)


@pytest.mark.parametrize(
    "body", ["print('not a version'); sys.exit(0)", "sys.exit(2)"], ids=["unparseable", "nonzero"]
)
async def test_unusable_age_version(tmp_path, body):
    dump = make_dump(tmp_path)
    with pytest.raises(AgeToolError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, body, version=None), timeout_seconds=30)
    assert_failed_cleanly(dump)


async def test_timeout(tmp_path):
    dump = make_dump(tmp_path)
    with pytest.raises(EncryptTimeoutError) as exc:
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, "time.sleep(60)"), timeout_seconds=1)
    assert exc.value.plaintext_retained
    assert_failed_cleanly(dump)


async def test_timeout_while_age_stops_reading(tmp_path):
    dump = make_dump(tmp_path, data=os.urandom(8 * 1024 * 1024))
    original = dump.dump_path.read_bytes()
    body = "sys.stdin.buffer.read(1000); time.sleep(60)"
    with pytest.raises(EncryptTimeoutError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, body), timeout_seconds=1)
    assert_failed_cleanly(dump, original)


async def test_cancellation(tmp_path):
    dump = make_dump(tmp_path)
    started = tmp_path / "started"
    body = f"open({str(started)!r}, 'w').close()\ntime.sleep(60)"
    task = asyncio.create_task(
        encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, body), timeout_seconds=60)
    )
    for _ in range(200):
        if started.exists():
            break
        await asyncio.sleep(0.05)
    assert started.exists() and partial(dump).exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert_failed_cleanly(dump)


async def test_compression_failure(tmp_path, monkeypatch):
    class Broken:
        def compress(self, data):
            raise zlib.error("boom")

        def flush(self, mode=zlib.Z_FINISH):
            raise zlib.error("boom")

    monkeypatch.setattr(enc.zlib, "compressobj", lambda *a, **k: Broken())
    dump = make_dump(tmp_path)
    with pytest.raises(CompressionError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump)


async def test_plaintext_sha_mismatch_is_rejected(tmp_path):
    dump = make_dump(tmp_path)
    tampered = SQL.replace(b"(1, 'x')", b"(2, 'x')", 1)
    dump.dump_path.write_bytes(tampered)  # same size, different bytes
    with pytest.raises(PlaintextIntegrityError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump, tampered)


async def test_plaintext_size_mismatch_is_rejected(tmp_path):
    dump = make_dump(tmp_path)
    dump.dump_path.write_bytes(SQL[:-10])
    with pytest.raises(PlaintextIntegrityError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump, SQL[:-10])


async def test_insufficient_space(tmp_path, monkeypatch):
    monkeypatch.setattr(enc, "_free_bytes", lambda path: 1024)
    dump = make_dump(tmp_path)
    with pytest.raises(InsufficientSpaceError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump)


async def test_recipient_failure_happens_before_anything(tmp_path):
    dump = make_dump(tmp_path)
    with pytest.raises(AgeRecipientError):
        await encrypt_dump_artifact(dump, "", age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump)


# --- unsafe work directory / input ---------------------------------------------------------


async def test_work_dir_broader_than_0700_is_refused(tmp_path):
    dump = make_dump(tmp_path)
    dump.dump_path.parent.chmod(0o750)
    with pytest.raises(UnsafeWorkPathError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    dump.dump_path.parent.chmod(0o700)
    assert_failed_cleanly(dump)


async def test_symlinked_work_dir_is_refused(tmp_path):
    dump = make_dump(tmp_path)
    link = tmp_path / "linked-run"
    link.symlink_to(dump.dump_path.parent)
    via_link = SnapshotDumpResult(**{**dump.__dict__, "dump_path": link / dump.dump_path.name})
    with pytest.raises(UnsafeWorkPathError):
        await encrypt_dump_artifact(via_link, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump)


async def test_relative_work_dir_is_refused(tmp_path, monkeypatch):
    dump = make_dump(tmp_path)
    monkeypatch.chdir(tmp_path)
    relative = SnapshotDumpResult(**{**dump.__dict__, "dump_path": Path("run") / dump.dump_path.name})
    with pytest.raises(UnsafeWorkPathError):
        await encrypt_dump_artifact(relative, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)


async def test_foreign_owner_is_refused(tmp_path, monkeypatch):
    dump = make_dump(tmp_path)
    monkeypatch.setattr(enc, "_euid", lambda: os.geteuid() + 1)
    with pytest.raises(UnsafeWorkPathError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump)


async def test_plaintext_with_broad_mode_is_refused(tmp_path):
    dump = make_dump(tmp_path, mode=0o644)
    with pytest.raises(UnsafeWorkPathError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert dump.dump_path.read_bytes() == SQL and not partial(dump).exists()


async def test_plaintext_symlink_is_refused(tmp_path):
    dump = make_dump(tmp_path)
    link = dump.dump_path.parent / "link.sql"
    link.symlink_to(dump.dump_path)
    via_link = SnapshotDumpResult(**{**dump.__dict__, "dump_path": link})
    with pytest.raises(UnsafeWorkPathError):
        await encrypt_dump_artifact(via_link, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump)


async def test_plaintext_not_regular_file_is_refused(tmp_path):
    dump = make_dump(tmp_path)
    fifo = dump.dump_path.parent / "fifo.sql"
    os.mkfifo(fifo, 0o600)
    via_fifo = SnapshotDumpResult(**{**dump.__dict__, "dump_path": fifo})
    with pytest.raises(UnsafeWorkPathError):
        await asyncio.wait_for(
            encrypt_dump_artifact(via_fifo, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30), 10
        )


# --- finalization / cleanup ------------------------------------------------------------------


async def test_directory_fsync_failure_after_rename_leaves_no_final_and_keeps_plaintext(tmp_path, monkeypatch):
    def failing(path):
        raise OSError("fsync failed")

    monkeypatch.setattr(enc, "_fsync_dir", failing)
    dump = make_dump(tmp_path)
    with pytest.raises(ArtifactFinalizeError):
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert_failed_cleanly(dump)


async def test_plaintext_unlink_failure_keeps_valid_artifact(tmp_path, monkeypatch):
    dump = make_dump(tmp_path)
    real_unlink = os.unlink

    def guarded_unlink(path, *args, **kwargs):
        if Path(path) == dump.dump_path:
            raise PermissionError("simulated")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(enc.os, "unlink", guarded_unlink)
    with pytest.raises(PlaintextCleanupError) as exc:
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    monkeypatch.undo()
    result = exc.value.result
    data = artifact(dump).read_bytes()
    assert result.artifact_sha256 == hashlib.sha256(data).hexdigest() and gzip.decompress(data) == SQL
    assert "valid" in str(exc.value) and "plaintext cleanup is incomplete" in str(exc.value)
    assert dump.dump_path.read_bytes() == SQL  # still present, reported
    assert not partial(dump).exists()


async def test_plaintext_dir_fsync_failure_after_unlink_reports_cleanup_error(tmp_path, monkeypatch):
    dump = make_dump(tmp_path)
    calls = []
    real = enc._fsync_dir

    def second_fails(path):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("fsync failed")
        real(path)

    monkeypatch.setattr(enc, "_fsync_dir", second_fails)
    with pytest.raises(PlaintextCleanupError) as exc:
        await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    assert exc.value.result.artifact_path.exists()


async def test_plaintext_is_unlinked_only_after_durable_completion(tmp_path, monkeypatch):
    dump = make_dump(tmp_path)
    events: list[str] = []
    real_fsync_dir, real_unlink, real_rename = enc._fsync_dir, os.unlink, os.rename

    def fsync_dir(path):
        events.append("fsync_dir")
        real_fsync_dir(path)

    def rename(src, dst, *a, **k):
        events.append("rename")
        return real_rename(src, dst, *a, **k)

    def unlink(path, *a, **k):
        if Path(path) == dump.dump_path:
            events.append("unlink_plaintext")
        return real_unlink(path, *a, **k)

    monkeypatch.setattr(enc, "_fsync_dir", fsync_dir)
    monkeypatch.setattr(enc.os, "rename", rename)
    monkeypatch.setattr(enc.os, "unlink", unlink)
    await encrypt_dump_artifact(dump, R1, age_binary=fake_age(tmp_path, COPY), timeout_seconds=30)
    monkeypatch.undo()
    assert events == ["rename", "fsync_dir", "unlink_plaintext", "fsync_dir"]


# --- resources -------------------------------------------------------------------------------


async def test_large_input_is_streamed_in_bounded_chunks(tmp_path, monkeypatch):
    work = tmp_path / "run"
    work.mkdir(mode=0o700)
    source = work / "plan-estimate.sql"
    digest = hashlib.sha256()
    total = 0
    fd = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        for i in range(64):  # 64 MiB, half incompressible
            block = os.urandom(512 * 1024) + (b"INSERT %d;\n" % i) * 47000
            block = block[: 1024 * 1024]
            fh.write(block)
            digest.update(block)
            total += len(block)
    dump = SnapshotDumpResult(
        snapshot_id="1-2-3",
        ready=ready_set_digest([]),
        server_major_version=16,
        dump_path=source,
        dump_size=total,
        dump_sha256=digest.hexdigest(),
    )
    reads: list[int] = []
    real_fdopen = os.fdopen

    class Spy:
        def __init__(self, inner):
            self._inner = inner

        def read(self, n=-1):
            reads.append(n)
            return self._inner.read(n)

        def close(self):
            self._inner.close()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    def spying_fdopen(fd, *args, **kwargs):
        handle = real_fdopen(fd, *args, **kwargs)
        return Spy(handle) if "r" in (args[0] if args else kwargs.get("mode", "r")) else handle

    monkeypatch.setattr(enc.os, "fdopen", spying_fdopen)
    slow_copy = (
        "while True:\n"
        "    b = sys.stdin.buffer.read(65536)\n"
        "    if not b: break\n"
        "    sys.stdout.buffer.write(b)\n"
    )
    tracemalloc.start()
    try:
        result = await encrypt_dump_artifact(
            dump, R1, age_binary=fake_age(tmp_path, slow_copy), timeout_seconds=120
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    monkeypatch.undo()
    assert reads and all(0 < n <= enc.CHUNK_SIZE for n in reads)  # never a whole-file read
    assert peak < 16 * 1024 * 1024, f"peak traced memory {peak} bytes"
    assert result.plaintext_size == total
    assert gunzip_sha256(result.artifact_path) == dump.dump_sha256


def gunzip_sha256(path: Path) -> str:
    out = hashlib.sha256()
    d = zlib.decompressobj(31)
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            out.update(d.decompress(chunk))
    out.update(d.flush())
    assert d.eof
    return out.hexdigest()
