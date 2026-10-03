"""Stage 14D.2D.2 — backup data root: lock, stale work, run workspace, atomic promotion.

Filesystem behaviour on a private temporary data root. Lock contention is
proven with real separate processes (kernel flock), not mocks. Compose
runtime behaviour is NOT proven here (owner E2E, 14D.2D.5).
"""

import errno
import os
import signal
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import app.backup.workspace as ws
from app.backup.run_id import RunIdError, new_run_id
from app.backup.workspace import (
    BackupDataRoot,
    CrossFilesystemError,
    DurabilityError,
    LockHeldError,
    PromotionError,
    RunDirectoryExistsError,
    StaleWorkError,
    UnsafeBackupPathError,
)

BACKEND = Path(__file__).resolve().parents[1]
RUN_A = "20261003T081500Z-3f9a1c2e"
RUN_B = "20261003T091500Z-0000abcd"


def mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


@pytest.fixture
def root(tmp_path) -> Path:
    path = tmp_path / "data"
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


@pytest.fixture
def data(root) -> BackupDataRoot:
    data_root = BackupDataRoot(root)
    data_root.prepare()
    return data_root


# --- data root ------------------------------------------------------------------------------


def test_prepare_creates_private_subdirectories(root):
    BackupDataRoot(root).prepare()
    for name in ("work", "encrypted", "evidence"):
        assert (root / name).is_dir() and mode(root / name) == 0o700
    assert not (root / "run.lock").exists()  # the lock file belongs to acquisition


@pytest.mark.parametrize("umask", [0o000, 0o022, 0o277])
def test_new_directories_are_0700_under_any_umask(root, umask):
    old = os.umask(umask)
    try:
        BackupDataRoot(root).prepare()
    finally:
        os.umask(old)
    for name in ("work", "encrypted", "evidence"):
        assert mode(root / name) == 0o700


def test_prepare_is_idempotent_on_a_valid_root(data, root):
    (root / "encrypted" / "keep").mkdir(mode=0o700)
    data.prepare()
    assert (root / "encrypted" / "keep").is_dir()


def test_prepare_without_creation_refuses_missing_directories(root):
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(root).prepare(create_missing=False)
    assert not (root / "work").exists()


def test_symlinked_root_is_refused(tmp_path, root):
    link = tmp_path / "link"
    link.symlink_to(root)
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(link).prepare()


@pytest.mark.parametrize("bad", [Path("relative/data"), Path("/")])
def test_relative_or_filesystem_root_is_refused(bad):
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(bad).prepare()


def test_root_that_is_a_file_is_refused(tmp_path):
    file = tmp_path / "file"
    file.write_text("")
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(file).prepare()


def test_broad_root_mode_is_refused_not_fixed(root):
    root.chmod(0o750)
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(root).prepare()
    assert mode(root) == 0o750


@pytest.mark.parametrize("name", ["work", "encrypted", "evidence"])
def test_symlinked_subdirectory_is_refused(tmp_path, root, name):
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    (root / name).symlink_to(target)
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(root).prepare()
    assert (root / name).is_symlink()  # untouched


@pytest.mark.parametrize("name", ["work", "encrypted", "evidence"])
def test_subdirectory_that_is_a_file_is_refused(root, name):
    (root / name).write_text("")
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(root).prepare()
    assert (root / name).is_file()


@pytest.mark.parametrize("name", ["work", "encrypted", "evidence"])
def test_unsafe_existing_subdirectory_mode_is_refused_not_fixed(root, name):
    (root / name).mkdir(mode=0o700)
    (root / name).chmod(0o755)
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(root).prepare()
    assert mode(root / name) == 0o755


def test_foreign_owner_is_refused(root):
    with pytest.raises(UnsafeBackupPathError, match="not owned"):
        BackupDataRoot(root, euid=os.geteuid() + 1).prepare()


# --- lock -----------------------------------------------------------------------------------


LOCK_HOLDER = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from app.backup.workspace import BackupDataRoot
    lock = BackupDataRoot(Path(sys.argv[1])).acquire_lock()
    print("LOCKED", flush=True)
    sys.stdin.readline()
    lock.release()
    print("RELEASED", flush=True)
    """
)


def start_holder(root: Path) -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        [sys.executable, "-c", LOCK_HOLDER, str(root)],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "LOCKED"
    return proc


def test_new_lock_file_is_0600_and_persists(data, root):
    old = os.umask(0)
    try:
        lock = data.acquire_lock()
    finally:
        os.umask(old)
    assert lock.held and mode(root / "run.lock") == 0o600
    lock.release()
    assert not lock.held
    assert (root / "run.lock").is_file() and mode(root / "run.lock") == 0o600


def test_lock_contention_across_processes_fails_immediately(data, root):
    holder = start_holder(root)
    try:
        with pytest.raises(LockHeldError):
            data.acquire_lock()
    finally:
        assert holder.stdin is not None and holder.stdout is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        assert holder.stdout.readline().strip() == "RELEASED"
        holder.wait(timeout=10)
    with data.acquire_lock() as lock:  # released -> next run may lock
        assert lock.held


def test_kernel_releases_lock_when_holder_process_dies(data, root):
    holder = start_holder(root)
    holder.send_signal(signal.SIGKILL)
    holder.wait(timeout=10)
    with data.acquire_lock() as lock:
        assert lock.held
    assert (root / "run.lock").exists()  # file persists, no stale lock


def test_second_independent_open_file_description_also_conflicts(data):
    with data.acquire_lock(), pytest.raises(LockHeldError):
        data.acquire_lock()


def test_double_release_and_context_manager_are_safe(data):
    lock = data.acquire_lock()
    lock.release()
    lock.release()
    with data.acquire_lock() as again:
        pass
    assert not again.held
    with data.acquire_lock():
        pass


def test_failed_acquisition_closes_its_fd(data, monkeypatch):
    opened: list[int] = []
    real_open = os.open

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if str(path) == "run.lock":
            opened.append(fd)
        return fd

    with data.acquire_lock():
        monkeypatch.setattr(ws.os, "open", tracking_open)
        with pytest.raises(LockHeldError):
            data.acquire_lock()
        monkeypatch.undo()
    assert opened
    for fd in opened:
        with pytest.raises(OSError) as exc:
            os.fstat(fd)
        assert exc.value.errno == errno.EBADF


def test_symlinked_lock_file_is_refused(tmp_path, data, root):
    target = tmp_path / "target"
    target.write_text("")
    target.chmod(0o600)
    (root / "run.lock").symlink_to(target)
    with pytest.raises(UnsafeBackupPathError):
        data.acquire_lock()


def test_non_regular_lock_file_is_refused(data, root):
    (root / "run.lock").mkdir(mode=0o700)
    with pytest.raises(UnsafeBackupPathError):
        data.acquire_lock()
    (root / "run.lock").rmdir()
    os.mkfifo(root / "run.lock", 0o600)
    with pytest.raises(UnsafeBackupPathError):
        data.acquire_lock()


def test_unsafe_lock_mode_is_refused_not_fixed(data, root):
    (root / "run.lock").write_text("")
    (root / "run.lock").chmod(0o644)
    with pytest.raises(UnsafeBackupPathError):
        data.acquire_lock()
    assert mode(root / "run.lock") == 0o644


def test_lock_with_foreign_owner_is_refused(root):
    BackupDataRoot(root).prepare()
    with pytest.raises(UnsafeBackupPathError):
        BackupDataRoot(root, euid=os.geteuid() + 1).acquire_lock()


# --- stale work -----------------------------------------------------------------------------


def test_empty_work_passes(data):
    data.assert_no_stale_work()


def test_canonical_stale_run_blocks_and_is_untouched(data, root):
    stale = root / "work" / RUN_A
    stale.mkdir(mode=0o700)
    (stale / "plan-estimate.sql").write_text("SECRET DUMP CONTENT")
    with pytest.raises(StaleWorkError) as exc:
        data.assert_no_stale_work()
    assert exc.value.entry_count == 1 and exc.value.run_ids == (RUN_A,)
    assert "SECRET" not in str(exc.value) and str(root) not in str(exc.value)
    assert (stale / "plan-estimate.sql").read_text() == "SECRET DUMP CONTENT"


@pytest.mark.parametrize("kind", ["file", "arbitrary-dir", "symlink", "dangling-symlink"])
def test_any_entry_blocks_without_traversal(tmp_path, data, root, kind):
    work = root / "work"
    if kind == "file":
        (work / "notes.txt").write_text("x")
    elif kind == "arbitrary-dir":
        (work / "weird name").mkdir()
    elif kind == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "big").write_text("should not be read")
        (work / RUN_B).symlink_to(outside)
    else:
        (work / "dangling").symlink_to(tmp_path / "missing")
    with pytest.raises(StaleWorkError) as exc:
        data.assert_no_stale_work()
    assert exc.value.entry_count == 1
    if kind == "symlink":
        assert exc.value.run_ids == (RUN_B,)
        assert (work / RUN_B).is_symlink()
    else:
        assert exc.value.run_ids == ()
    assert "weird name" not in str(exc.value) and "notes" not in str(exc.value)


def test_stale_report_is_capped(data, root):
    for i in range(8):
        (root / "work" / f"20261003T08150{i}Z-0000000{i}").mkdir()
    with pytest.raises(StaleWorkError) as exc:
        data.assert_no_stale_work()
    assert exc.value.entry_count == 8 and len(exc.value.run_ids) == ws.STALE_NAMES_REPORTED


# --- run workspace ---------------------------------------------------------------------------


def test_create_run_makes_a_private_directory_and_fixed_paths(data, root):
    old = os.umask(0)
    try:
        run = data.create_run(RUN_A)
    finally:
        os.umask(old)
    assert run.directory == root / "work" / RUN_A and mode(run.directory) == 0o700
    assert run.plaintext_dump == run.directory / "plan-estimate.sql"
    assert run.encrypted_artifact == run.directory / "plan-estimate.sql.gz.age"
    assert run.local_evidence == run.directory / "local-run.json"
    assert list(run.directory.iterdir()) == []


def test_create_run_with_generated_id(data):
    run_id = new_run_id()
    assert data.create_run(run_id).run_id == run_id


def test_collision_fails_without_reuse_or_delete(data, root):
    existing = root / "work" / RUN_A
    existing.mkdir(mode=0o700)
    (existing / "keep").write_text("keep")
    with pytest.raises(RunDirectoryExistsError):
        data.create_run(RUN_A)
    assert (existing / "keep").read_text() == "keep"


def test_collision_with_symlink_is_refused(tmp_path, data, root):
    target = tmp_path / "t"
    target.mkdir()
    (root / "work" / RUN_A).symlink_to(target)
    with pytest.raises(RunDirectoryExistsError):
        data.create_run(RUN_A)
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("bad", ["../escape", "x", "20261003T081500Z-3F9A1C2E", "", "a/b"])
def test_invalid_run_id_is_rejected_before_any_mutation(data, root, bad):
    before = sorted(p.name for p in (root / "work").iterdir())
    with pytest.raises(RunIdError):
        data.create_run(bad)
    with pytest.raises(RunIdError):
        data.promote(bad)
    assert sorted(p.name for p in (root / "work").iterdir()) == before
    assert not (root.parent / "escape").exists()


# --- promotion -------------------------------------------------------------------------------


def make_run(data: BackupDataRoot) -> Path:
    run = data.create_run(RUN_A)
    (run.directory / "plan-estimate.sql.gz.age").write_bytes(b"artifact")
    (run.directory / "local-run.json").write_bytes(b"{}\n")
    return run.directory


def test_promotion_moves_the_run_atomically(data, root):
    source = make_run(data)
    destination = data.promote(RUN_A)
    assert destination == root / "encrypted" / RUN_A
    assert not source.exists()
    assert (destination / "plan-estimate.sql.gz.age").read_bytes() == b"artifact"
    assert mode(destination) == 0o700


def test_promotion_fsync_sequence(data, monkeypatch, root):
    make_run(data)
    events: list[str] = []
    real_fsync, real_rename = ws._fsync, ws._rename_noreplace
    inode_names = {
        os.stat(root / "work").st_ino: "fsync(work/)",
        os.stat(root / "encrypted").st_ino: "fsync(encrypted/)",
        os.stat(root / "work" / RUN_A).st_ino: "fsync(run dir)",
    }

    def fsync(fd: int) -> None:
        events.append(inode_names.get(os.fstat(fd).st_ino, "fsync(other)"))
        real_fsync(fd)

    def rename(src_fd: int, name: str, dst_fd: int) -> None:
        events.append("rename")
        real_rename(src_fd, name, dst_fd)

    monkeypatch.setattr(ws, "_fsync", fsync)
    monkeypatch.setattr(ws, "_rename_noreplace", rename)
    data.promote(RUN_A)
    assert events == ["fsync(run dir)", "rename", "fsync(work/)", "fsync(encrypted/)"]


def test_destination_collision_fails_without_overwrite(data, root):
    source = make_run(data)
    existing = root / "encrypted" / RUN_A
    existing.mkdir(mode=0o700)  # empty: plain rename(2) would silently replace it
    with pytest.raises(PromotionError, match="already exists"):
        data.promote(RUN_A)
    assert source.is_dir() and list(existing.iterdir()) == []


def test_rename_noreplace_refuses_an_existing_empty_directory(root):
    (root / "a").mkdir()
    (root / "b").mkdir()
    (root / "a" / "x").mkdir()
    (root / "b" / "x").mkdir()
    fd_a = os.open(root / "a", os.O_RDONLY | os.O_DIRECTORY)
    fd_b = os.open(root / "b", os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(FileExistsError):
            ws._rename_noreplace(fd_a, "x", fd_b)
    finally:
        os.close(fd_a)
        os.close(fd_b)
    assert (root / "a" / "x").is_dir()


def test_destination_appearing_after_precheck_is_not_overwritten(data, root, monkeypatch):
    source = make_run(data)
    real_rename = ws._rename_noreplace

    def racing_rename(src_fd: int, name: str, dst_fd: int) -> None:
        os.mkdir(name, 0o700, dir_fd=dst_fd)  # an empty directory appears in the race window
        real_rename(src_fd, name, dst_fd)

    monkeypatch.setattr(ws, "_rename_noreplace", racing_rename)
    with pytest.raises(PromotionError, match="appeared"):
        data.promote(RUN_A)
    assert source.is_dir() and list((root / "encrypted" / RUN_A).iterdir()) == []


def test_symlinked_source_is_refused(tmp_path, data, root):
    target = tmp_path / "t"
    target.mkdir(mode=0o700)
    (root / "work" / RUN_A).symlink_to(target)
    with pytest.raises(UnsafeBackupPathError):
        data.promote(RUN_A)
    assert (root / "work" / RUN_A).is_symlink() and not (root / "encrypted" / RUN_A).exists()


def test_symlinked_destination_is_refused(tmp_path, data, root):
    source = make_run(data)
    (root / "encrypted" / RUN_A).symlink_to(tmp_path / "anywhere")
    with pytest.raises(PromotionError):
        data.promote(RUN_A)
    assert source.is_dir()


def test_source_that_is_a_file_or_missing_is_refused(data, root):
    with pytest.raises(PromotionError):
        data.promote(RUN_A)
    (root / "work" / RUN_A).write_text("")
    with pytest.raises(UnsafeBackupPathError):
        data.promote(RUN_A)


def test_unsafe_source_mode_is_refused(data, root):
    source = make_run(data)
    source.chmod(0o755)
    with pytest.raises(UnsafeBackupPathError):
        data.promote(RUN_A)
    assert source.is_dir()


def test_cross_filesystem_fails_closed_without_copy(data, root, monkeypatch):
    source = make_run(data)
    encrypted_ino = os.stat(root / "encrypted").st_ino
    real_fstat = os.fstat

    def fake_fstat(fd: int) -> os.stat_result:
        st = real_fstat(fd)
        if st.st_ino == encrypted_ino:
            values = list(st)
            values[stat.ST_DEV] = st.st_dev + 1
            return os.stat_result(values)
        return st

    calls: list[str] = []
    monkeypatch.setattr(ws.os, "fstat", fake_fstat)
    monkeypatch.setattr(ws, "_rename_noreplace", lambda *a: calls.append("rename"))
    with pytest.raises(CrossFilesystemError):
        data.promote(RUN_A)
    assert calls == [] and source.is_dir() and not (root / "encrypted" / RUN_A).exists()


def test_rename_failure_leaves_the_source_recoverable(data, root, monkeypatch):
    source = make_run(data)

    def failing(*args):
        raise OSError(errno.EXDEV, "simulated")

    monkeypatch.setattr(ws, "_rename_noreplace", failing)
    with pytest.raises(PromotionError, match="EXDEV"):
        data.promote(RUN_A)
    assert (source / "plan-estimate.sql.gz.age").read_bytes() == b"artifact"
    assert not (root / "encrypted" / RUN_A).exists()


def test_run_dir_fsync_failure_prevents_promotion(data, root, monkeypatch):
    source = make_run(data)

    def failing(fd):
        raise OSError(errno.EIO, "simulated")

    monkeypatch.setattr(ws, "_fsync", failing)
    with pytest.raises(DurabilityError) as exc:
        data.promote(RUN_A)
    assert exc.value.promoted is False and source.is_dir()


@pytest.mark.parametrize("failing_call", [2, 3])
def test_parent_fsync_failure_after_rename_is_surfaced(data, root, monkeypatch, failing_call):
    make_run(data)
    calls = {"n": 0}
    real = ws._fsync

    def fsync(fd: int) -> None:
        calls["n"] += 1
        if calls["n"] == failing_call:
            raise OSError(errno.EIO, "simulated")
        real(fd)

    monkeypatch.setattr(ws, "_fsync", fsync)
    with pytest.raises(DurabilityError) as exc:
        data.promote(RUN_A)
    assert exc.value.promoted is True
    assert (root / "encrypted" / RUN_A).is_dir()  # the rename happened; durability unconfirmed


def test_no_copy_fallback_exists():
    source = Path(ws.__file__).read_text()
    for forbidden in ("shutil", "copytree", "copyfile", "copy2", "os.rename(", "os.replace("):
        assert forbidden not in source


def test_promotion_does_not_judge_content(data, root):
    data.create_run(RUN_A)  # empty run dir: promotion is a filesystem operation only
    assert data.promote(RUN_A) == root / "encrypted" / RUN_A
