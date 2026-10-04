"""Backup data root: lock, stale-run check, run workspace, atomic promotion (Stage 14D.2D.2).

One persistent data root (owner decision D1; docs/STAGE_14D_BACKUP_RESTORE_PLAN.md
§16.4), in the container `/backup`, holds:

    run.lock      0600  persistent; the kernel flock on its open fd is the run lock
    work/         0700  in-progress runs: work/<run_id>/ (0700)
    encrypted/    0700  locally complete runs: encrypted/<run_id>/ (atomic rename from work/)
    evidence/     0700  reserved for best-effort failure evidence (later slice)

Secrets are never under the data root. Everything is opened relative to
directory file descriptors with O_NOFOLLOW, checked with fstat (directory /
regular file, owned by the effective UID, no group / other bits) and never
"repaired": an unsafe pre-existing entry is refused, only directories and
files created here get 0700 / 0600 (fchmod, independent of the umask).

Stale work is fail-closed: any entry in work/ blocks a new run; it is never
inspected recursively, renamed or deleted -- the operator decides.

Promotion is an atomic `renameat2(RENAME_NOREPLACE)` of work/<run_id> to
encrypted/<run_id> on one filesystem (same st_dev), surrounded by explicit
fsyncs; there is no copy fallback and no plain-rename fallback. Promotion
does not judge the run's content: only the orchestrator decides that a run
is complete and calls it.
"""

import ctypes
import errno
import fcntl
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from app.backup.run_id import RunIdError, validate_run_id
from app.core.db_dump_encryption import ENCRYPTED_DUMP_NAME

WORK_DIR = "work"
ENCRYPTED_DIR = "encrypted"
EVIDENCE_DIR = "evidence"
LOCK_FILE = "run.lock"
SUBDIRS = (WORK_DIR, ENCRYPTED_DIR, EVIDENCE_DIR)
PLAINTEXT_DUMP_NAME = "plan-estimate.sql"
LOCAL_EVIDENCE_NAME = "local-run.json"
RUN_SIDECAR_NAMES = frozenset({"ready-assets.txt", "recipients.txt"})  # = run_sidecars.SIDECAR_NAMES
FAILED_EVIDENCE_SUFFIX = ".failed.json"
PUBLISHED_EVIDENCE_SUFFIX = ".published.json"  # 14D.2J: written by `upload` after a run was sealed in the target
UPLOAD_FAILED_EVIDENCE = re.compile(r"^\.upload-failed-[0-9]{8}T[0-9]{6}Z\.json$")
DIR_MODE = 0o700
FILE_MODE = 0o600
STALE_NAMES_REPORTED = 5
RENAME_NOREPLACE = 1

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class WorkspaceError(RuntimeError):
    """The backup data root is unusable. Messages carry names relative to
    the data root only -- never contents or host paths."""


class UnsafeBackupPathError(WorkspaceError):
    pass


class LockHeldError(WorkspaceError):
    """Another backup run holds run.lock."""


class RunFileMissingError(UnsafeBackupPathError):
    """A file expected inside a promoted run does not exist."""


class StaleWorkError(WorkspaceError):
    """work/ is not empty: a previous run is incomplete. Manual inspection required."""

    def __init__(self, entry_count: int, run_ids: tuple[str, ...]) -> None:
        shown = ", ".join(run_ids) if run_ids else "none"
        super().__init__(
            f"backup work directory is not empty ({entry_count} entr{'y' if entry_count == 1 else 'ies'};"
            f" canonical run ids: {shown}); inspect it manually -- nothing was changed"
        )
        self.entry_count = entry_count
        self.run_ids = run_ids


class RunDirectoryExistsError(WorkspaceError):
    pass


class CrossFilesystemError(WorkspaceError):
    """work/ and encrypted/ are not on one filesystem: atomic promotion is impossible."""


class PromotionError(WorkspaceError):
    """Promotion did not happen; the run directory is still in work/."""


class EvidenceWriteError(WorkspaceError):
    """A local evidence file could not be written durably (or already exists)."""


class DurabilityError(WorkspaceError):
    """An fsync failed. `promoted` tells whether the rename already happened."""

    def __init__(self, message: str, *, promoted: bool) -> None:
        super().__init__(message)
        self.promoted = promoted


# --- low-level helpers (module-level so tests can observe the sequence) ------------------


def _fsync(fd: int) -> None:
    os.fsync(fd)


_libc = ctypes.CDLL(None, use_errno=True)
_renameat2 = getattr(_libc, "renameat2", None)
if _renameat2 is not None:
    _renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    _renameat2.restype = ctypes.c_int


def _rename_noreplace(src_dir_fd: int, name: str, dst_dir_fd: int) -> None:
    """Atomic rename that fails with FileExistsError if the destination
    exists (plain rename(2) silently replaces an empty directory)."""
    if _renameat2 is None:
        raise OSError(errno.ENOSYS, "renameat2 is not available")
    encoded = name.encode("ascii")
    if _renameat2(src_dir_fd, encoded, dst_dir_fd, encoded, RENAME_NOREPLACE) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def _euid(euid: int | None) -> int:
    return os.geteuid() if euid is None else euid


def _check_private(st: os.stat_result, what: str, *, directory: bool, euid: int) -> None:
    if directory and not stat.S_ISDIR(st.st_mode):
        raise UnsafeBackupPathError(f"{what} is not a directory")
    if not directory and not stat.S_ISREG(st.st_mode):
        raise UnsafeBackupPathError(f"{what} is not a regular file")
    if st.st_uid != euid:
        raise UnsafeBackupPathError(f"{what} is not owned by the effective user")
    if st.st_mode & 0o077:
        raise UnsafeBackupPathError(f"{what} has group / other permissions (expected {'0700' if directory else '0600'})")


def _open_dir(name: str | Path, what: str, *, dir_fd: int | None, euid: int) -> int:
    """Open an existing directory without following a symlink and verify it."""
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except FileNotFoundError:
        raise UnsafeBackupPathError(f"{what} does not exist") from None
    except OSError as exc:  # ELOOP (symlink), ENOTDIR, EACCES
        raise UnsafeBackupPathError(f"{what} cannot be opened as a directory ({errno.errorcode.get(exc.errno or 0, 'error')})") from None
    try:
        _check_private(os.fstat(fd), what, directory=True, euid=euid)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _open_root(root: Path, euid: int) -> int:
    if not root.is_absolute():
        raise UnsafeBackupPathError("backup data root must be an absolute path")
    if root == Path(root.anchor):
        raise UnsafeBackupPathError("backup data root must not be a filesystem root")
    return _open_dir(root, "backup data root", dir_fd=None, euid=euid)


def _create_private_dir(name: str, what: str, *, dir_fd: int, euid: int) -> int:
    """mkdir (fails if it exists), then open it and fchmod 0700 -- the umask
    cannot leave it narrower or wider."""
    os.mkdir(name, DIR_MODE, dir_fd=dir_fd)
    fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    try:
        os.fchmod(fd, DIR_MODE)
        _check_private(os.fstat(fd), what, directory=True, euid=euid)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _open_subdir(root_fd: int, name: str, *, euid: int) -> int:
    return _open_dir(name, f"{name}/", dir_fd=root_fd, euid=euid)


# --- data root ------------------------------------------------------------------------------


@dataclass(frozen=True)
class BackupDataRoot:
    """The persistent data root (container: /backup; tests: any private dir)."""

    path: Path
    euid: int | None = None

    def prepare(self, *, create_missing: bool = True) -> None:
        """Validate the root and its three directories; create missing ones
        privately when allowed. Existing unsafe entries are refused, never chmod-ed."""
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            created = False
            for name in SUBDIRS:
                try:
                    os.close(_open_subdir(root_fd, name, euid=uid))
                except UnsafeBackupPathError:
                    if not create_missing or _lexists(name, root_fd):
                        raise
                    os.close(_create_private_dir(name, f"{name}/", dir_fd=root_fd, euid=uid))
                    created = True
            if created:
                _fsync(root_fd)
        finally:
            os.close(root_fd)

    def acquire_lock(self) -> "RunLock":
        return RunLock.acquire(self)

    def assert_no_stale_work(self) -> None:
        """Fail closed if work/ has any entry. Names only; nothing is followed,
        traversed, renamed or deleted."""
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            work_fd = _open_subdir(root_fd, WORK_DIR, euid=uid)
            try:
                with os.scandir(work_fd) as entries:
                    names = [entry.name for entry in entries]
            finally:
                os.close(work_fd)
        finally:
            os.close(root_fd)
        if names:
            canonical = []
            for name in sorted(names):
                try:
                    canonical.append(validate_run_id(name))
                except RunIdError:
                    continue
            raise StaleWorkError(len(names), tuple(canonical[:STALE_NAMES_REPORTED]))

    def create_run(self, run_id: str) -> "RunWorkspace":
        """Create work/<run_id>/ (0700). Fails if it exists -- never reused,
        overwritten or deleted, no retry with another id."""
        run_id = validate_run_id(run_id)
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            work_fd = _open_subdir(root_fd, WORK_DIR, euid=uid)
            try:
                try:
                    run_fd = _create_private_dir(run_id, f"{WORK_DIR}/<run_id>", dir_fd=work_fd, euid=uid)
                except FileExistsError:
                    raise RunDirectoryExistsError("the run directory already exists; refusing to reuse it") from None
                try:
                    _fsync(run_fd)
                finally:
                    os.close(run_fd)
                _fsync(work_fd)
            finally:
                os.close(work_fd)
        finally:
            os.close(root_fd)
        return RunWorkspace(run_id=run_id, directory=self.path / WORK_DIR / run_id)

    def promote(self, run_id: str) -> Path:
        """Atomically move work/<run_id>/ to encrypted/<run_id>/.

        Durability sequence (files inside were already fsynced by their
        writers): fsync(run dir) -> renameat2(NOREPLACE) -> fsync(work/) ->
        fsync(encrypted/). Same filesystem required; no copy fallback."""
        run_id = validate_run_id(run_id)
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            work_fd = _open_subdir(root_fd, WORK_DIR, euid=uid)
            try:
                encrypted_fd = _open_subdir(root_fd, ENCRYPTED_DIR, euid=uid)
                try:
                    return self._promote(run_id, work_fd, encrypted_fd, uid)
                finally:
                    os.close(encrypted_fd)
            finally:
                os.close(work_fd)
        finally:
            os.close(root_fd)

    def write_run_evidence(self, run_id: str, data: bytes) -> Path:
        """work/<run_id>/local-run.json -- exclusive, 0600, fsynced with its directory."""
        run_id = validate_run_id(run_id)
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            work_fd = _open_subdir(root_fd, WORK_DIR, euid=uid)
            try:
                run_fd = _open_dir(run_id, "work/<run_id>", dir_fd=work_fd, euid=uid)
                try:
                    _write_private_file(run_fd, LOCAL_EVIDENCE_NAME, data)
                finally:
                    os.close(run_fd)
            finally:
                os.close(work_fd)
        finally:
            os.close(root_fd)
        return self.path / WORK_DIR / run_id / LOCAL_EVIDENCE_NAME

    def write_run_file(self, run_id: str, name: str, data: bytes) -> Path:
        """work/<run_id>/<name> for one of the fixed sidecar names -- exclusive, 0600, fsynced."""
        if name not in RUN_SIDECAR_NAMES:
            raise EvidenceWriteError("not a run sidecar name")
        run_id = validate_run_id(run_id)
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            work_fd = _open_subdir(root_fd, WORK_DIR, euid=uid)
            try:
                run_fd = _open_dir(run_id, "work/<run_id>", dir_fd=work_fd, euid=uid)
                try:
                    _write_private_file(run_fd, name, data)
                finally:
                    os.close(run_fd)
            finally:
                os.close(work_fd)
        finally:
            os.close(root_fd)
        return self.path / WORK_DIR / run_id / name

    def write_failure_evidence(self, run_id: str, data: bytes) -> Path:
        """evidence/<run_id>.failed.json -- exclusive, 0600, fsynced with its directory."""
        run_id = validate_run_id(run_id)
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            evidence_fd = _open_subdir(root_fd, EVIDENCE_DIR, euid=uid)
            try:
                _write_private_file(evidence_fd, f"{run_id}{FAILED_EVIDENCE_SUFFIX}", data)
            finally:
                os.close(evidence_fd)
        finally:
            os.close(root_fd)
        return self.path / EVIDENCE_DIR / f"{run_id}{FAILED_EVIDENCE_SUFFIX}"

    def run_entry_names(self, run_id: str, *, promoted: bool) -> frozenset[str]:
        """Names directly inside work/<run_id> (or encrypted/<run_id> when
        promoted); empty if it does not exist. Names only: nothing is read,
        followed or traversed."""
        run_id = validate_run_id(run_id)
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            parent_fd = _open_subdir(root_fd, ENCRYPTED_DIR if promoted else WORK_DIR, euid=uid)
            try:
                try:
                    run_fd = os.open(run_id, _DIR_FLAGS, dir_fd=parent_fd)
                except (FileNotFoundError, NotADirectoryError):
                    return frozenset()
                except OSError:
                    raise UnsafeBackupPathError("the run directory cannot be opened") from None
                try:
                    with os.scandir(run_fd) as entries:
                        return frozenset(entry.name for entry in entries)
                finally:
                    os.close(run_fd)
            finally:
                os.close(parent_fd)
        finally:
            os.close(root_fd)

    # -- reading a promoted run and the upload evidence (14D.2J) ------------------------------------

    def promoted_run_ids(self) -> list[str]:
        """Canonical run ids found as entries of encrypted/ (other names are ignored), oldest first."""
        return sorted(self._canonical_ids(ENCRYPTED_DIR, lambda name: name))

    def published_run_ids(self) -> list[str]:
        """Run ids with `evidence/<run_id>.published.json`, oldest first."""
        return sorted(
            self._canonical_ids(
                EVIDENCE_DIR,
                lambda name: name.removesuffix(PUBLISHED_EVIDENCE_SUFFIX) if name.endswith(PUBLISHED_EVIDENCE_SUFFIX) else "",
            )
        )

    def _canonical_ids(self, subdir: str, to_id: Callable[[str], str]) -> list[str]:
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            dir_fd = _open_subdir(root_fd, subdir, euid=uid)
            try:
                with os.scandir(dir_fd) as entries:
                    names = [entry.name for entry in entries]
            finally:
                os.close(dir_fd)
        finally:
            os.close(root_fd)
        ids = []
        for name in names:
            try:
                ids.append(validate_run_id(to_id(name)))
            except RunIdError:
                continue
        return ids

    def read_promoted_file(self, run_id: str, name: str, *, max_bytes: int) -> bytes:
        """Contents of encrypted/<run_id>/<name>: no symlink, a private regular file of the effective user,
        at most `max_bytes` (larger is refused, not truncated)."""
        fd = self._open_promoted_file(run_id, name)
        try:
            with os.fdopen(fd, "rb", closefd=True) as handle:
                data = handle.read(max_bytes + 1)
        except OSError as exc:
            raise UnsafeBackupPathError(f"{name} cannot be read ({errno.errorcode.get(exc.errno or 0, 'error')})") from None
        if len(data) > max_bytes:
            raise UnsafeBackupPathError(f"{name} is larger than the allowed {max_bytes} bytes")
        return data

    def verified_promoted_path(self, run_id: str, name: str) -> Path:
        """The path of encrypted/<run_id>/<name> after the same checks as `read_promoted_file`."""
        os.close(self._open_promoted_file(run_id, name))
        return self.path / ENCRYPTED_DIR / validate_run_id(run_id) / name

    def _open_promoted_file(self, run_id: str, name: str) -> int:
        if "/" in name or name in {"", ".", ".."}:
            raise UnsafeBackupPathError("not a file name")
        run_id = validate_run_id(run_id)
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            encrypted_fd = _open_subdir(root_fd, ENCRYPTED_DIR, euid=uid)
            try:
                if not _lexists(run_id, encrypted_fd):
                    raise RunFileMissingError("the run does not exist in encrypted/")
                run_fd = _open_dir(run_id, "encrypted/<run_id>", dir_fd=encrypted_fd, euid=uid)
                try:
                    try:
                        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=run_fd)
                    except FileNotFoundError:
                        raise RunFileMissingError(f"{name} does not exist in the run") from None
                    except OSError as exc:
                        raise UnsafeBackupPathError(
                            f"{name} cannot be opened as a regular file ({errno.errorcode.get(exc.errno or 0, 'error')})"
                        ) from None
                    try:
                        _check_private(os.fstat(fd), name, directory=False, euid=uid)
                    except BaseException:
                        os.close(fd)
                        raise
                    return fd
                finally:
                    os.close(run_fd)
            finally:
                os.close(encrypted_fd)
        finally:
            os.close(root_fd)

    def write_upload_evidence(self, run_id: str, suffix: str, data: bytes) -> Path:
        """evidence/<run_id><suffix> for `.published.json` or `.upload-failed-<UTC>.json` -- exclusive, 0600, fsynced."""
        run_id = validate_run_id(run_id)
        if suffix != PUBLISHED_EVIDENCE_SUFFIX and not UPLOAD_FAILED_EVIDENCE.match(suffix):
            raise EvidenceWriteError("not an upload evidence name")
        uid = _euid(self.euid)
        root_fd = _open_root(self.path, uid)
        try:
            evidence_fd = _open_subdir(root_fd, EVIDENCE_DIR, euid=uid)
            try:
                _write_private_file(evidence_fd, f"{run_id}{suffix}", data)
            finally:
                os.close(evidence_fd)
        finally:
            os.close(root_fd)
        return self.path / EVIDENCE_DIR / f"{run_id}{suffix}"

    def _promote(self, run_id: str, work_fd: int, encrypted_fd: int, uid: int) -> Path:
        try:
            source_st = os.stat(run_id, dir_fd=work_fd, follow_symlinks=False)
        except FileNotFoundError:
            raise PromotionError("the run directory does not exist in work/") from None
        if stat.S_ISLNK(source_st.st_mode):
            raise UnsafeBackupPathError("work/<run_id> is a symlink")
        _check_private(source_st, "work/<run_id>", directory=True, euid=uid)
        if _lexists(run_id, encrypted_fd):
            raise PromotionError("encrypted/<run_id> already exists; refusing to overwrite")
        work_dev, encrypted_dev = os.fstat(work_fd).st_dev, os.fstat(encrypted_fd).st_dev
        if not (work_dev == encrypted_dev == source_st.st_dev):
            raise CrossFilesystemError("work/ and encrypted/ are on different filesystems; atomic promotion impossible")

        run_fd = os.open(run_id, _DIR_FLAGS, dir_fd=work_fd)
        try:
            if os.fstat(run_fd).st_ino != source_st.st_ino:
                raise PromotionError("the run directory changed during promotion")
            try:
                _fsync(run_fd)
            except OSError:
                raise DurabilityError("fsync of the run directory failed; not promoted", promoted=False) from None
        finally:
            os.close(run_fd)

        try:
            _rename_noreplace(work_fd, run_id, encrypted_fd)
        except FileExistsError:
            raise PromotionError("encrypted/<run_id> appeared during promotion; refusing to overwrite") from None
        except OSError as exc:
            reason = errno.errorcode.get(exc.errno or 0, "error")
            raise PromotionError(f"atomic rename failed ({reason}); the run is still in work/") from None

        for fd, name in ((work_fd, "work/"), (encrypted_fd, "encrypted/")):
            try:
                _fsync(fd)
            except OSError:
                raise DurabilityError(
                    f"run promoted, but fsync of {name} failed; durability not confirmed", promoted=True
                ) from None
        return self.path / ENCRYPTED_DIR / run_id


def _write_private_file(dir_fd: int, name: str, data: bytes) -> None:
    """Exclusive create (never overwrite, never follow a symlink), 0600 via
    fchmod, full write, fsync(file), fsync(directory)."""
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE, dir_fd=dir_fd)
    except FileExistsError:
        raise EvidenceWriteError(f"{name} already exists; refusing to overwrite") from None
    except OSError as exc:
        raise EvidenceWriteError(f"{name} cannot be created ({errno.errorcode.get(exc.errno or 0, 'error')})") from None
    try:
        os.fchmod(fd, FILE_MODE)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        _fsync(fd)
    except OSError as exc:
        raise EvidenceWriteError(f"{name} could not be written ({errno.errorcode.get(exc.errno or 0, 'error')})") from None
    finally:
        os.close(fd)
    try:
        _fsync(dir_fd)
    except OSError:
        raise EvidenceWriteError(f"directory fsync after writing {name} failed") from None


def _lexists(name: str, dir_fd: int) -> bool:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


# --- run workspace ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunWorkspace:
    """Paths of one in-progress run; names are fixed constants, never input."""

    run_id: str
    directory: Path

    @property
    def plaintext_dump(self) -> Path:
        return self.directory / PLAINTEXT_DUMP_NAME

    @property
    def encrypted_artifact(self) -> Path:
        return self.directory / ENCRYPTED_DUMP_NAME

    @property
    def local_evidence(self) -> Path:
        return self.directory / LOCAL_EVIDENCE_NAME


# --- run lock ---------------------------------------------------------------------------------


class RunLock:
    """Exclusive, non-blocking flock on <data root>/run.lock, held by an open
    fd for the whole run. The file persists; the kernel releases the lock when
    the fd is closed or the process dies, so there is no stale lock to clean."""

    def __init__(self, fd: int) -> None:
        self._fd: int | None = fd

    @classmethod
    def acquire(cls, data_root: BackupDataRoot) -> "RunLock":
        uid = _euid(data_root.euid)
        root_fd = _open_root(data_root.path, uid)
        try:
            fd = cls._open_lock_file(root_fd, uid)
        finally:
            os.close(root_fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise LockHeldError("another backup run holds run.lock") from None
        except BaseException:
            os.close(fd)
            raise
        return cls(fd)

    @staticmethod
    def _open_lock_file(root_fd: int, uid: int) -> int:
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        try:
            fd = os.open(LOCK_FILE, flags | os.O_CREAT | os.O_EXCL, FILE_MODE, dir_fd=root_fd)
            created = True
        except FileExistsError:
            try:
                fd = os.open(LOCK_FILE, flags, dir_fd=root_fd)
            except OSError as exc:  # ELOOP (symlink), EISDIR, EACCES
                reason = errno.errorcode.get(exc.errno or 0, "error")
                raise UnsafeBackupPathError(f"run.lock cannot be opened as a regular file ({reason})") from None
            created = False
        try:
            if created:
                os.fchmod(fd, FILE_MODE)
            _check_private(os.fstat(fd), "run.lock", directory=False, euid=uid)
            if created:
                _fsync(root_fd)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @property
    def held(self) -> bool:
        return self._fd is not None

    def release(self) -> None:
        """Idempotent: a second release is a no-op."""
        fd, self._fd = self._fd, None
        if fd is not None:
            os.close(fd)  # closing the only fd of the open file description drops the flock

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.release()
