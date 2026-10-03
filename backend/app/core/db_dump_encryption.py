"""Encrypted database backup artifact (Stage 14D.2B).

`docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` §9.1. Converts the verified private
plaintext dump produced by the 14D.2A snapshot primitive into the canonical
encrypted artifact `plan-estimate.sql.gz.age` in the same private work
directory:

    plaintext (0600, verified by 14D.2A)
      -> streaming gzip (in-process zlib, MTIME 0, no name / comment)
      -> streaming `age --encrypt --recipient age1…` (official CLI)
      -> `<artifact>.partial` (0600, exclusive) -> fsync
      -> SHA-256 + size re-read from disk -> rename -> directory fsync
      -> unlink plaintext -> directory fsync

No gzip file is written. Backup uses PUBLIC native X25519 recipients only;
there is no identity / decryption parameter. Backup-time success means the
whole stream reached age, age exited 0 and the output is durably stored and
hashed -- it does NOT prove decryptability (that needs the private identity:
real-age round-trip tests and the 14D.5 restore drill).

The plaintext is never removed unless the encrypted artifact is complete and
durable; on any earlier failure, timeout or cancellation the plaintext is
left untouched, age is killed and reaped, and only the partial file created
by this call is removed. Deletion is unlink only, not secure erasure.
"""

import asyncio
import hashlib
import os
import re
import shutil
import stat
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from app.core.pg_snapshot_dump import SnapshotDumpResult

ENCRYPTED_DUMP_NAME = "plan-estimate.sql.gz.age"
PARTIAL_SUFFIX = ".partial"
CHUNK_SIZE = 1024 * 1024
GZIP_LEVEL = 6
# wbits 16 + 15: gzip wrapper. zlib documents this header as having no file
# name, no extra field, no comment and modification time 0.
GZIP_WBITS = 31
ARTIFACT_MODE = 0o600
STDERR_TAIL_BYTES = 2000
VERSION_TIMEOUT_SECONDS = 30.0
# Compressed + encrypted output can slightly exceed incompressible input.
SPACE_MARGIN_BYTES = 16 * 1024 * 1024
# The child gets nothing from the backup environment (cloud credentials,
# DSNs): only a fixed PATH and the C locale.
AGE_CHILD_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C"}

# Native X25519 recipient: "age1" + 58 bech32 characters (no "1" separator
# after the prefix, so plugin recipients `age1<name>1…` never match).
_X25519_RECIPIENT = re.compile(r"^age1[02-9ac-hj-np-z]{58}$")
_AGE_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)([-+.][0-9A-Za-z.+-]*)?$")

T = TypeVar("T")


class DumpEncryptionError(RuntimeError):
    """The encrypted artifact was not completed. Unless stated otherwise the
    plaintext dump is untouched and no final artifact exists."""

    plaintext_retained = True


class AgeRecipientError(DumpEncryptionError):
    """Recipient configuration is empty, malformed or not a public X25519
    recipient. Messages name the position, never the value."""


class AgeToolError(DumpEncryptionError):
    """The age binary is missing, not executable, or its version output
    cannot be understood."""


class AgeFailedError(DumpEncryptionError):
    def __init__(self, message: str, *, returncode: int | None, stderr_tail: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr_tail = stderr_tail


class EncryptTimeoutError(DumpEncryptionError):
    pass


class ArtifactCollisionError(DumpEncryptionError):
    """An artifact or partial file already exists; nothing was touched."""


class UnsafeWorkPathError(DumpEncryptionError):
    """The work directory or the plaintext input is not private."""


class InsufficientSpaceError(DumpEncryptionError):
    pass


class PlaintextIntegrityError(DumpEncryptionError):
    """The plaintext read now is not the dump 14D.2A verified (size / SHA-256
    mismatch, or it could not be read)."""


class CompressionError(DumpEncryptionError):
    pass


class ArtifactFinalizeError(DumpEncryptionError):
    """age succeeded but the artifact could not be made durable / hashed /
    renamed; no final artifact is left."""


class PlaintextCleanupError(DumpEncryptionError):
    """The encrypted artifact is complete, durable and valid (`result`), but
    the plaintext could not be removed (or its removal made durable)."""

    def __init__(self, message: str, *, result: "EncryptedDumpResult") -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class EncryptedDumpResult:
    artifact_path: Path
    artifact_size: int
    artifact_sha256: str
    plaintext_size: int
    plaintext_sha256: str
    recipients: tuple[str, ...]
    age_version: str


def parse_age_recipients(values: str | Iterable[str]) -> tuple[str, ...]:
    """Accept 1..N native X25519 public recipients (comma / whitespace
    separated string or an iterable); duplicates collapse, order kept."""
    raw = re.split(r"[\s,]+", values) if isinstance(values, str) else [str(v) for v in values]
    items = [item.strip() for item in raw if item.strip()]
    if not items:
        raise AgeRecipientError("no age recipient configured")
    recipients: list[str] = []
    for position, item in enumerate(items, start=1):
        if "AGE-SECRET-KEY-" in item.upper():
            raise AgeRecipientError(
                f"recipient #{position} looks like an age PRIVATE key; only public age1… recipients are accepted"
            )
        if item.startswith(("ssh-", "ecdsa-", "sk-")):
            raise AgeRecipientError(f"recipient #{position} is an SSH key; only native age1… recipients are accepted")
        if not _X25519_RECIPIENT.match(item):
            raise AgeRecipientError(f"recipient #{position} is not a native X25519 age recipient")
        if item not in recipients:
            recipients.append(item)
    return tuple(recipients)


def age_encrypt_argv(age_path: str, recipients: Iterable[str]) -> list[str]:
    """Encryption only: no identity, passphrase, decrypt, armor or output
    option ever appears (the output is the inherited stdout descriptor)."""
    argv = [age_path, "--encrypt"]
    for recipient in recipients:
        argv += ["--recipient", recipient]
    return argv


def parse_age_version(output: str) -> str:
    lines = output.strip().splitlines()
    line = lines[0].strip() if lines else ""
    if not _AGE_VERSION.match(line):
        raise AgeToolError("cannot understand the age --version output")
    return line


def resolve_age_binary(age_binary: str) -> str:
    resolved = shutil.which(age_binary)
    if resolved is None:
        raise AgeToolError("age binary not found or not executable")
    return os.path.abspath(resolved)


def _tail(data: bytes) -> str:
    return data[-STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")


async def _reap(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()


async def _spawn(argv: list[str], **kwargs: Any) -> asyncio.subprocess.Process:
    try:
        return await asyncio.create_subprocess_exec(*argv, env=dict(AGE_CHILD_ENV), **kwargs)
    except OSError as exc:  # FileNotFoundError / PermissionError / ENOEXEC
        raise AgeToolError(f"age binary could not be started ({type(exc).__name__})") from None


async def age_version(age_path: str) -> str:
    proc = await _spawn(
        [age_path, "--version"],
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(VERSION_TIMEOUT_SECONDS):
            stdout, _ = await proc.communicate()
    except BaseException:
        await asyncio.shield(_reap(proc))
        raise
    if proc.returncode != 0:
        raise AgeToolError(f"age --version exited with status {proc.returncode}")
    return parse_age_version(stdout.decode("utf-8", errors="replace"))


def _euid() -> int:
    return os.geteuid()


def _free_bytes(path: Path) -> int:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def _check_private_dir(path: Path) -> None:
    if not path.is_absolute():
        raise UnsafeWorkPathError("work directory must be an absolute path")
    if path == Path(path.anchor):
        raise UnsafeWorkPathError("work directory must not be a filesystem root")
    try:
        st = os.lstat(path)
    except OSError:
        raise UnsafeWorkPathError("work directory does not exist") from None
    if stat.S_ISLNK(st.st_mode):
        raise UnsafeWorkPathError("work directory must not be a symlink")
    if not stat.S_ISDIR(st.st_mode):
        raise UnsafeWorkPathError("work directory is not a directory")
    if st.st_uid != _euid():
        raise UnsafeWorkPathError("work directory is not owned by the effective user")
    if st.st_mode & 0o077:
        raise UnsafeWorkPathError("work directory mode is broader than 0700")


def _open_plaintext(path: Path) -> int:
    try:
        # O_NONBLOCK: opening a FIFO must not block the event loop (it is then
        # refused below); it has no effect on reads of a regular file.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError:
        raise UnsafeWorkPathError(f"plaintext dump {path.name} cannot be opened as a regular non-symlink file") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise UnsafeWorkPathError(f"plaintext dump {path.name} is not a regular file")
        if st.st_uid != _euid():
            raise UnsafeWorkPathError(f"plaintext dump {path.name} is not owned by the effective user")
        if st.st_mode & 0o177:
            raise UnsafeWorkPathError(f"plaintext dump {path.name} is not private (expected 0600)")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _create_private_exclusive(path: Path) -> int:
    """Exclusive create, 0600 whatever the umask (no global umask change)."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, ARTIFACT_MODE)
    except FileExistsError:
        raise ArtifactCollisionError(f"{path.name} already exists; refusing to overwrite") from None
    try:
        os.fchmod(fd, ARTIFACT_MODE)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb", buffering=0) as fh:
        while chunk := fh.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


class _GzipChunks:
    """Reads the plaintext in bounded chunks, hashes it and returns the gzip
    output for that chunk; after EOF returns the gzip trailer once, then
    None. Runs in a worker thread, one step at a time."""

    def __init__(self, fd: int, chunk_size: int) -> None:
        self._file = os.fdopen(fd, "rb", buffering=0)
        self._chunk_size = chunk_size
        self._compressor = zlib.compressobj(GZIP_LEVEL, zlib.DEFLATED, GZIP_WBITS)
        self._sha = hashlib.sha256()
        self._finished = False
        self.size = 0

    @property
    def sha256(self) -> str:
        return self._sha.hexdigest()

    def next_chunk(self) -> bytes | None:
        if self._finished:
            return None
        try:
            data = self._file.read(self._chunk_size)
        except OSError:
            raise PlaintextIntegrityError("plaintext dump could not be read") from None
        try:
            if data:
                self._sha.update(data)
                self.size += len(data)
                return self._compressor.compress(data)
            self._finished = True
            return self._compressor.flush(zlib.Z_FINISH)
        except zlib.error:
            raise CompressionError("gzip compression failed") from None

    def close(self) -> None:
        self._file.close()


class _Worker:
    """Runs blocking steps in the default executor. The step in flight is
    awaited through `shield`, so a timeout / cancellation never leaves it
    running unobserved: cleanup waits for it before closing descriptors."""

    def __init__(self) -> None:
        self._inflight: asyncio.Future[object] | None = None

    async def run(self, fn: Callable[[], T]) -> T:
        future: asyncio.Future[T] = asyncio.get_running_loop().run_in_executor(None, fn)
        self._inflight = future  # type: ignore[assignment]
        return await asyncio.shield(future)

    async def settle(self) -> None:
        future = self._inflight
        if future is not None:
            await asyncio.wait([future])
            if not future.cancelled():
                future.exception()  # retrieved: the original failure is what propagates


async def _drain_tail(stream: asyncio.StreamReader) -> bytes:
    tail = b""
    while chunk := await stream.read(65536):
        tail = (tail + chunk)[-STDERR_TAIL_BYTES:]
    return tail


async def encrypt_dump_artifact(
    dump: SnapshotDumpResult,
    recipients: str | Iterable[str],
    *,
    age_binary: str = "age",
    timeout_seconds: float = 3600.0,
    chunk_size: int = CHUNK_SIZE,
) -> EncryptedDumpResult:
    """Encrypt the 14D.2A plaintext dump into `<dump dir>/plan-estimate.sql.gz.age`
    and, only after the artifact is durable, unlink the plaintext."""
    parsed = parse_age_recipients(recipients)
    plaintext = Path(dump.dump_path)
    work_dir = plaintext.parent
    _check_private_dir(work_dir)
    final = work_dir / ENCRYPTED_DUMP_NAME
    partial = work_dir / (ENCRYPTED_DUMP_NAME + PARTIAL_SUFFIX)
    if plaintext.name in (final.name, partial.name):
        raise UnsafeWorkPathError("plaintext dump must not use the artifact file name")
    for existing in (final, partial):
        if os.path.lexists(existing):
            raise ArtifactCollisionError(f"{existing.name} already exists; refusing to overwrite")

    plain_fd = _open_plaintext(plaintext)
    reader = _GzipChunks(plain_fd, chunk_size)
    worker = _Worker()
    out_fd: int | None = None
    partial_created = False
    proc: asyncio.subprocess.Process | None = None
    stderr_task: asyncio.Task[bytes] | None = None
    try:
        if os.fstat(plain_fd).st_size != dump.dump_size:
            raise PlaintextIntegrityError("plaintext dump size differs from the verified snapshot dump")
        if _free_bytes(work_dir) < dump.dump_size + dump.dump_size // 100 + SPACE_MARGIN_BYTES:
            raise InsufficientSpaceError("not enough free space in the work directory for the encrypted artifact")
        age_path = resolve_age_binary(age_binary)
        try:
            async with asyncio.timeout(timeout_seconds):
                version = await age_version(age_path)

                out_fd = _create_private_exclusive(partial)
                partial_created = True
                proc = await _spawn(
                    age_encrypt_argv(age_path, parsed),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=out_fd,
                    stderr=asyncio.subprocess.PIPE,
                )
                assert proc.stdin is not None and proc.stderr is not None
                stderr_task = asyncio.create_task(_drain_tail(proc.stderr))
                stdin_broken = False
                try:
                    while (data := await worker.run(reader.next_chunk)) is not None:
                        if data:
                            proc.stdin.write(data)
                            await proc.stdin.drain()
                    if reader.size != dump.dump_size or reader.sha256 != dump.dump_sha256:
                        raise PlaintextIntegrityError("plaintext dump differs from the verified snapshot dump")
                    proc.stdin.close()
                    await proc.stdin.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    stdin_broken = True  # age stopped reading; reported with its exit status below
                returncode = await proc.wait()
                stderr_tail = _tail(await stderr_task)
                if returncode != 0:
                    raise AgeFailedError(
                        f"age exited with status {returncode}", returncode=returncode, stderr_tail=stderr_tail
                    )
                if stdin_broken:
                    raise AgeFailedError(
                        "age exited before consuming the whole input", returncode=returncode, stderr_tail=stderr_tail
                    )

                fd = out_fd
                try:
                    await worker.run(lambda: os.fsync(fd))
                    size, sha = await worker.run(lambda: _hash_file(partial))
                except OSError:
                    raise ArtifactFinalizeError("encrypted artifact could not be made durable or hashed") from None
        except TimeoutError:
            raise EncryptTimeoutError(f"encryption did not finish within {timeout_seconds} s") from None
        if size == 0:
            raise ArtifactFinalizeError("age produced an empty artifact")
        try:
            if os.path.lexists(final):
                raise ArtifactCollisionError(f"{final.name} appeared during encryption; refusing to overwrite")
            os.rename(partial, final)
        except OSError:
            raise ArtifactFinalizeError("encrypted artifact could not be renamed") from None
        partial_created = False
        try:
            _fsync_dir(work_dir)
        except OSError:
            final.unlink(missing_ok=True)  # never leave a final name that is not durable
            raise ArtifactFinalizeError("work directory fsync failed after rename") from None
    except BaseException:
        await asyncio.shield(_abort(proc, stderr_task, worker))
        if partial_created:
            partial.unlink(missing_ok=True)
        raise
    finally:
        reader.close()
        if out_fd is not None:
            os.close(out_fd)

    result = EncryptedDumpResult(
        artifact_path=final,
        artifact_size=size,
        artifact_sha256=sha,
        plaintext_size=reader.size,
        plaintext_sha256=reader.sha256,
        recipients=parsed,
        age_version=version,
    )
    try:
        os.unlink(plaintext)
        _fsync_dir(work_dir)
    except OSError as exc:
        raise PlaintextCleanupError(
            f"encrypted artifact is valid, but plaintext cleanup is incomplete ({type(exc).__name__})",
            result=result,
        ) from None
    return result


async def _abort(
    proc: asyncio.subprocess.Process | None, stderr_task: asyncio.Task[bytes] | None, worker: _Worker
) -> None:
    if proc is not None:
        await _reap(proc)
    if stderr_task is not None:
        if not stderr_task.done():
            stderr_task.cancel()
        await asyncio.wait([stderr_task])
        if not stderr_task.cancelled():
            stderr_task.exception()
    await worker.settle()
