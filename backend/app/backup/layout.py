"""Backup workspace / mount contract (Stage 14D.2C).

Container paths are fixed and independent of the host user name. The host
side (recommended `/home/ubuntu/backups/plan-estimate/db-backup/`, 0700) is
bind-mounted by the `backup` Compose service:

    <host root>/work        -> /backup/work         rw  per-run plaintext + partials (14D.2D lifecycle)
    <host root>/encrypted   -> /backup/encrypted    rw  completed encrypted artifacts
    <host root>/evidence    -> /backup/evidence     rw  per-run evidence (no secrets)
    <host root>/secrets/pgpass -> /run/secrets/pgpass ro  libpq / asyncpg passfile

Only the root directories are checked here; per-run directories and files
are checked by the 14D.2B primitive and the 14D.2D orchestrator.
"""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

HOST_ROOT_RECOMMENDED = "/home/ubuntu/backups/plan-estimate/db-backup"
CONTAINER_ROOT = Path("/backup")
PASSFILE_CONTAINER_PATH = Path("/run/secrets/pgpass")


@dataclass(frozen=True)
class BackupLayout:
    work: Path = CONTAINER_ROOT / "work"
    encrypted: Path = CONTAINER_ROOT / "encrypted"
    evidence: Path = CONTAINER_ROOT / "evidence"

    def writable_dirs(self) -> dict[str, Path]:
        return {"work": self.work, "encrypted": self.encrypted, "evidence": self.evidence}


def private_dir_problem(path: Path, *, euid: int | None = None) -> str | None:
    """None if `path` is an existing, writable, non-symlink directory owned by
    the effective user with no group / other bits; otherwise a short reason
    (never file contents)."""
    expected_uid = os.geteuid() if euid is None else euid
    try:
        st = os.lstat(path)
    except OSError:
        return "missing (not mounted?)"
    if stat.S_ISLNK(st.st_mode):
        return "is a symlink"
    if not stat.S_ISDIR(st.st_mode):
        return "is not a directory"
    if st.st_uid != expected_uid:
        return "not owned by the effective user"
    if st.st_mode & 0o077:
        return "mode broader than 0700"
    if not os.access(path, os.W_OK | os.X_OK):
        return "not writable"
    return None
