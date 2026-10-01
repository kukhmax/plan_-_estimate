"""Stage 14C.4 — stale photo temp cleanup: startup (lifespan) and per upload
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §11 step 6, §20.2)."""

import logging
import os
import time

from app.api import upload_guard
from app.api.upload_guard import sweep_stale_photo_temp
from app.core.config import settings
from app.domain.photos.temp import PHOTO_TEMP_PREFIX
from app.main import app, lifespan


def make_entries(base, *, stale_age: float):
    base.mkdir(parents=True, exist_ok=True)
    stale = base / f"{PHOTO_TEMP_PREFIX}stale"
    fresh = base / f"{PHOTO_TEMP_PREFIX}fresh"
    foreign = base / "not-ours"
    for path in (stale, fresh, foreign):
        path.mkdir()
        (path / "original").write_bytes(b"x")
    old = time.time() - stale_age
    os.utime(stale, (old, old))
    os.utime(foreign, (old, old))
    return stale, fresh, foreign


async def test_startup_sweep_removes_only_stale_workspaces(tmp_path, monkeypatch):
    base = tmp_path / "photo-temp"
    stale, fresh, foreign = make_entries(base, stale_age=86400 + 60)
    monkeypatch.setattr(settings, "PHOTO_TEMP_DIR", str(base))
    monkeypatch.setattr(settings, "PHOTO_TEMP_STALE_AFTER_SECONDS", 86400)
    async with lifespan(app):
        pass
    assert not stale.exists() and fresh.exists() and foreign.exists()


async def test_workspace_younger_than_threshold_is_kept(tmp_path, monkeypatch):
    base = tmp_path / "photo-temp"
    stale, fresh, _ = make_entries(base, stale_age=86400 - 60)
    sweep_stale_photo_temp(str(base), 86400)
    assert stale.exists() and fresh.exists()


async def test_missing_temp_dir_is_nothing_to_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_TEMP_DIR", str(tmp_path / "absent"))
    async with lifespan(app):
        pass
    assert not (tmp_path / "absent").exists()  # the sweep never creates it


async def test_sweep_failure_is_logged_and_startup_continues(tmp_path, monkeypatch, caplog):
    base = tmp_path / "photo-temp"
    base.mkdir()
    monkeypatch.setattr(settings, "PHOTO_TEMP_DIR", str(base))

    def broken(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(upload_guard, "cleanup_stale_photo_temp", broken)
    started = False
    with caplog.at_level(logging.ERROR, logger="app.api.upload_guard"):
        async with lifespan(app):
            started = True
    assert started
    assert any("photo temp sweep failed: PermissionError" in r.getMessage() for r in caplog.records)


async def test_unusable_temp_dir_is_logged_not_raised(tmp_path, caplog):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    with caplog.at_level(logging.ERROR, logger="app.api.upload_guard"):
        sweep_stale_photo_temp(str(link), 86400)
    assert any("PhotoTempDirError" in r.getMessage() for r in caplog.records)
