"""Backup data-root / mount contract (Stage 14D.2C, corrected in 14D.2D.2).

Container paths are fixed and independent of the host user name. The host
backup root (recommended `/home/ubuntu/backups/plan-estimate/db-backup/`,
0700) holds the data root and, separately, the secrets; the `backup` Compose
service mounts:

    <host root>/data           -> /backup              rw  ONE data mount (owner decision D1)
    <host root>/secrets/pgpass -> /run/secrets/pgpass  ro  libpq / asyncpg passfile

Inside the data root: `work/` (in-progress runs), `encrypted/` (locally
complete runs), `evidence/` (failure evidence), `run.lock`. They must share
one mount so that work/<run_id> -> encrypted/<run_id> is one atomic rename
(separate bind mounts fail with EXDEV even on the same host filesystem).
Secrets never live under the data root.

`private_dir_problem` is the read-only preflight check; creation and the
run lifecycle are in `app.backup.workspace`.
"""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from app.backup.workspace import ENCRYPTED_DIR, EVIDENCE_DIR, WORK_DIR

HOST_ROOT_RECOMMENDED = "/home/ubuntu/backups/plan-estimate/db-backup"
CONTAINER_DATA_ROOT = Path("/backup")
PASSFILE_CONTAINER_PATH = Path("/run/secrets/pgpass")


@dataclass(frozen=True)
class BackupLayout:
    root: Path = CONTAINER_DATA_ROOT

    @property
    def work(self) -> Path:
        return self.root / WORK_DIR

    @property
    def encrypted(self) -> Path:
        return self.root / ENCRYPTED_DIR

    @property
    def evidence(self) -> Path:
        return self.root / EVIDENCE_DIR

    def writable_dirs(self) -> dict[str, Path]:
        return {"data root": self.root, "work": self.work, "encrypted": self.encrypted, "evidence": self.evidence}


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
