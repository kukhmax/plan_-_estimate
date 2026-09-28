"""Stage 14B.3 — bounded temporary storage + stale cleanup (plan §5.1)."""

import os
import time
from pathlib import Path

import pytest

from app.domain.photos.temp import (
    PHOTO_TEMP_PREFIX,
    PhotoTempDirError,
    cleanup_stale_photo_temp,
    ensure_photo_temp_dir,
    photo_workspace,
)

DAY = 86400


def age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t), follow_symlinks=False)


def test_workspace_removed_on_success(tmp_path):
    base = tmp_path / "photos"
    with photo_workspace(base) as ws:
        assert ws.name.startswith(PHOTO_TEMP_PREFIX)
        assert ws.parent == base
        (ws / "display.jpg").write_bytes(b"x")
    assert not ws.exists()
    assert list(base.iterdir()) == []
    assert oct(base.stat().st_mode & 0o777) == oct(0o700)


def test_workspace_removed_on_failure(tmp_path):
    base = tmp_path / "photos"
    with pytest.raises(RuntimeError):
        with photo_workspace(base) as ws:
            (ws / "partial").write_bytes(b"x")
            raise RuntimeError("pipeline failed")
    assert not ws.exists()


def test_workspace_cleanup_does_not_follow_symlinks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    with photo_workspace(tmp_path / "photos") as ws:
        (ws / "link").symlink_to(outside, target_is_directory=True)
    assert (outside / "keep.txt").read_text() == "keep"


def test_stale_cleanup_is_prefix_and_age_based(tmp_path):
    base = ensure_photo_temp_dir(tmp_path / "photos")
    stale_dir = base / f"{PHOTO_TEMP_PREFIX}old"
    stale_dir.mkdir()
    (stale_dir / "display.jpg").write_bytes(b"x")
    stale_file = base / f"{PHOTO_TEMP_PREFIX}old.bin"
    stale_file.write_bytes(b"x")
    fresh_dir = base / f"{PHOTO_TEMP_PREFIX}fresh"
    fresh_dir.mkdir()
    unrelated_old = base / "someone-elses-file.bin"
    unrelated_old.write_bytes(b"keep")
    for p in (stale_dir, stale_file, unrelated_old):
        age(p, 2 * DAY)

    report = cleanup_stale_photo_temp(base, DAY)

    assert not stale_dir.exists()
    assert not stale_file.exists()
    assert fresh_dir.exists()
    assert unrelated_old.read_bytes() == b"keep"
    assert sorted(report.removed) == sorted([stale_dir.name, stale_file.name])
    assert report.kept_fresh == [fresh_dir.name]
    assert report.errors == []


def test_stale_cleanup_never_follows_prefixed_symlinks(tmp_path):
    base = ensure_photo_temp_dir(tmp_path / "photos")
    victim_dir = tmp_path / "important"
    victim_dir.mkdir()
    (victim_dir / "data.txt").write_text("precious")
    age(victim_dir, 10 * DAY)
    link = base / f"{PHOTO_TEMP_PREFIX}evil"
    link.symlink_to(victim_dir, target_is_directory=True)
    age(link, 10 * DAY)
    victim_file = tmp_path / "important.txt"
    victim_file.write_text("precious")
    file_link = base / f"{PHOTO_TEMP_PREFIX}evil-file"
    file_link.symlink_to(victim_file)
    age(file_link, 10 * DAY)

    report = cleanup_stale_photo_temp(base, DAY)

    assert (victim_dir / "data.txt").read_text() == "precious"
    assert victim_file.read_text() == "precious"
    assert link.is_symlink() and file_link.is_symlink()
    assert sorted(report.skipped) == sorted([link.name, file_link.name])
    assert report.removed == []


def test_stale_dir_with_inner_symlink_removes_link_not_target(tmp_path):
    base = ensure_photo_temp_dir(tmp_path / "photos")
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "data.txt").write_text("precious")
    stale = base / f"{PHOTO_TEMP_PREFIX}stale"
    stale.mkdir()
    (stale / "inner").symlink_to(victim, target_is_directory=True)
    age(stale, 2 * DAY)
    cleanup_stale_photo_temp(base, DAY)
    assert not stale.exists()
    assert (victim / "data.txt").read_text() == "precious"


def test_temp_dir_itself_must_not_be_a_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / f"{PHOTO_TEMP_PREFIX}old").write_bytes(b"x")
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(PhotoTempDirError):
        cleanup_stale_photo_temp(link, DAY)
    with pytest.raises(PhotoTempDirError):
        with photo_workspace(link):
            pass
    assert (real / f"{PHOTO_TEMP_PREFIX}old").exists()


@pytest.mark.parametrize("bad", ["/", "relative/dir"])
def test_unsafe_temp_dir_rejected(bad):
    with pytest.raises(PhotoTempDirError):
        ensure_photo_temp_dir(bad)


def test_missing_temp_dir_is_a_no_op(tmp_path):
    report = cleanup_stale_photo_temp(tmp_path / "does-not-exist", DAY)
    assert report.removed == [] and not (tmp_path / "does-not-exist").exists()


def test_cleanup_error_is_reported_and_does_not_widen_deletion(tmp_path, monkeypatch):
    import app.domain.photos.temp as mod

    base = ensure_photo_temp_dir(tmp_path / "photos")
    bad = base / f"{PHOTO_TEMP_PREFIX}bad"
    bad.mkdir()
    good = base / f"{PHOTO_TEMP_PREFIX}good"
    good.mkdir()
    other = base / "other"
    other.mkdir()
    for p in (bad, good, other):
        age(p, 2 * DAY)
    real_remove = mod._remove_entry

    def flaky(path):
        if path.name == bad.name:
            raise PermissionError("denied")
        real_remove(path)

    monkeypatch.setattr(mod, "_remove_entry", flaky)
    report = cleanup_stale_photo_temp(base, DAY)
    assert report.errors == [bad.name]
    assert report.removed == [good.name]
    assert bad.exists() and other.exists()


def test_older_than_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        cleanup_stale_photo_temp(tmp_path, 0)
