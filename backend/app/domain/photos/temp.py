"""Bounded temporary storage for photo processing (Stage 14B.3; plan §5.1).

The VM/container disk is never a photo store: every file created here is a
short-lived processing artefact inside a per-operation workspace directory
under PHOTO_TEMP_DIR, removed in `finally`. Every entry the application
creates carries the fixed prefix `pe-photo-`, so the age-based stale sweep
can positively identify Stage 14 artefacts and never touches anything else.
"""

import logging
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

PHOTO_TEMP_PREFIX = "pe-photo-"


class PhotoTempDirError(Exception):
    """PHOTO_TEMP_DIR is unusable (a symlink, not a directory, or unsafe)."""


def ensure_photo_temp_dir(temp_dir: str | os.PathLike[str]) -> Path:
    """Create (0700) or validate the dedicated temp directory.

    The directory itself must not be a symlink and must be a real directory;
    the filesystem root is refused so a misconfiguration can never point the
    sweep at a shared location root.
    """
    path = Path(temp_dir)
    if not path.is_absolute():
        raise PhotoTempDirError("PHOTO_TEMP_DIR must be an absolute path")
    if path == Path(path.anchor):
        raise PhotoTempDirError("PHOTO_TEMP_DIR must not be a filesystem root")
    if path.is_symlink():
        raise PhotoTempDirError("PHOTO_TEMP_DIR must not be a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not stat.S_ISDIR(os.lstat(path).st_mode):
        raise PhotoTempDirError("PHOTO_TEMP_DIR is not a directory")
    return path


@contextmanager
def photo_workspace(temp_dir: str | os.PathLike[str]) -> Iterator[Path]:
    """Yield a private, prefixed workspace directory; always removed on exit
    (success and every failure path)."""
    base = ensure_photo_temp_dir(temp_dir)
    workspace = Path(tempfile.mkdtemp(prefix=PHOTO_TEMP_PREFIX, dir=base))
    try:
        yield workspace
    finally:
        _remove_entry(workspace)


def _remove_entry(path: Path) -> None:
    """Remove a workspace entry without following symlinks. shutil.rmtree
    never follows symlinks inside the tree (fd-based on Linux)."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode):
        os.unlink(path)  # remove the link itself, never its target
    elif stat.S_ISDIR(st.st_mode):
        shutil.rmtree(path)
    else:
        os.unlink(path)


@dataclass
class TempCleanupReport:
    removed: list[str] = field(default_factory=list)
    kept_fresh: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def cleanup_stale_photo_temp(
    temp_dir: str | os.PathLike[str],
    older_than_seconds: int,
    *,
    now: float | None = None,
) -> TempCleanupReport:
    """Delete abandoned Stage 14 temp entries older than `older_than_seconds`.

    Only direct children of `temp_dir` whose name starts with the Stage 14
    prefix are candidates. Symlinks are never followed (a prefixed symlink is
    skipped and left untouched); unprefixed entries are never touched; the
    directory itself is never emptied blindly. Per-entry failures are logged
    and reported, and never widen what gets deleted.
    """
    if older_than_seconds <= 0:
        raise ValueError("older_than_seconds must be positive")
    report = TempCleanupReport()
    path = Path(temp_dir)
    if not path.exists():
        return report
    base = ensure_photo_temp_dir(path)
    cutoff = (time.time() if now is None else now) - older_than_seconds
    with os.scandir(base) as entries:
        for entry in entries:
            if not entry.name.startswith(PHOTO_TEMP_PREFIX):
                continue
            try:
                st = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(st.st_mode) or not (
                    stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)
                ):
                    report.skipped.append(entry.name)
                    continue
                if st.st_mtime > cutoff:
                    report.kept_fresh.append(entry.name)
                    continue
                _remove_entry(Path(entry.path))
                report.removed.append(entry.name)
            except OSError as exc:
                logger.warning("photo temp cleanup failed for %s: %s", entry.name, type(exc).__name__)
                report.errors.append(entry.name)
    return report
