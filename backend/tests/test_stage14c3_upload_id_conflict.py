"""Stage 14C.3 — uniform PHOTO_UPLOAD_ID_CONFLICT (contract §14, R-1).

A foreign upload_id, an own upload_id of another project and an own
upload_id with different bytes produce the identical error. The foreign and
other-project paths never compare SHA-256 and never reach processing,
storage or state transitions.
"""

import uuid

import pytest

from app.domain.exceptions import PHOTO_UPLOAD_ID_CONFLICT_MESSAGE, PhotoUploadIdConflictError
from app.domain.services import photo_upload_service as ups
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import AttachmentTarget
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachmentContext
from tests import test_stage14c3_upload_service as harness
from tests.test_stage14c3_upload_service import image_file, req

C = PhotoAttachmentContext
env = harness.env  # shared pytest fixture


async def existing(env, *, owner=None, project=None, color=(200, 30, 30)) -> tuple[str, object]:
    """A READY asset uploaded by `owner` into `project`."""
    owner = owner or env.me
    project = project or env.project
    target = AttachmentTarget(context=C.PROJECT)
    upload_id = str(uuid.uuid4())
    path = image_file(env.tmp, f"{upload_id}.jpg", color)
    await env.service().upload(req(env, path, upload_id=upload_id, owner=owner, project=project, target=target))
    return upload_id, path


class Spies:
    def __init__(self, env, monkeypatch):
        self.sha_compares = 0
        self.processed = 0
        self.cas = 0
        original_same = ups.same_original
        original_cas = PhotoAssetService.compare_and_set_status

        def spy_same(a, b):
            self.sha_compares += 1
            return original_same(a, b)

        async def spy_run(*a, **k):
            self.processed += 1
            raise AssertionError("processing must not run")

        async def spy_cas(svc, *a, **k):
            self.cas += 1
            return await original_cas(svc, *a, **k)

        monkeypatch.setattr(ups, "same_original", spy_same)
        monkeypatch.setattr(env.processor, "run_in_slot", spy_run)
        monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", spy_cas)
        env.storage.puts.clear()
        env.storage.heads.clear()


async def snapshot(env, upload_id: str):
    asset = await env.db.get(PhotoAsset, uuid.UUID(upload_id), populate_existing=True)
    return (asset.owner_id, asset.project_id, asset.status, asset.sha256, asset.updated_at)


async def conflict(env, request) -> PhotoUploadIdConflictError:
    with pytest.raises(PhotoUploadIdConflictError) as exc:
        await env.service().upload(request)
    return exc.value


async def test_foreign_upload_id_conflicts_without_sha_comparison(env, monkeypatch):
    upload_id, path = await existing(env, owner=env.other, project=env.foreign_project)
    before = await snapshot(env, upload_id)
    spies = Spies(env, monkeypatch)
    # Same bytes as the foreign asset: still a conflict, and never compared.
    await conflict(env, req(env, path, upload_id=upload_id))
    assert (spies.sha_compares, spies.processed, spies.cas) == (0, 0, 0)
    assert env.storage.puts == [] and env.storage.heads == []
    assert await snapshot(env, upload_id) == before


async def test_own_upload_id_in_other_project_conflicts_without_sha_comparison(env, monkeypatch):
    upload_id, path = await existing(env, project=env.project2)
    spies = Spies(env, monkeypatch)
    await conflict(env, req(env, path, upload_id=upload_id, target=AttachmentTarget(context=C.PROJECT)))
    assert (spies.sha_compares, spies.processed, spies.cas) == (0, 0, 0)
    assert env.storage.puts == [] and env.storage.heads == []


async def test_own_upload_id_with_different_bytes_conflicts(env, monkeypatch):
    upload_id, _ = await existing(env)
    before = await snapshot(env, upload_id)
    spies = Spies(env, monkeypatch)
    other_bytes = image_file(env.tmp, "different.jpg", (1, 200, 1))
    await conflict(env, req(env, other_bytes, upload_id=upload_id))
    assert spies.sha_compares == 1 and (spies.processed, spies.cas) == (0, 0)
    assert env.storage.puts == [] and env.storage.heads == []
    assert await snapshot(env, upload_id) == before


@pytest.mark.parametrize("status", [PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED])
async def test_foreign_not_ready_asset_is_the_same_conflict(env, monkeypatch, status):
    upload_id, path = await existing(env, owner=env.other, project=env.foreign_project)
    asset = await env.db.get(PhotoAsset, uuid.UUID(upload_id))
    asset.status = status
    await env.db.commit()
    spies = Spies(env, monkeypatch)
    await conflict(env, req(env, path, upload_id=upload_id))
    assert (spies.sha_compares, spies.processed, spies.cas) == (0, 0, 0)
    assert env.storage.heads == []  # no object-existence probe for a foreign asset


async def test_all_three_conflicts_are_indistinguishable(env):
    foreign_id, foreign_path = await existing(env, owner=env.other, project=env.foreign_project)
    other_project_id, other_project_path = await existing(env, project=env.project2, color=(5, 5, 5))
    own_id, _ = await existing(env, color=(9, 90, 9))
    errors = [
        await conflict(env, req(env, foreign_path, upload_id=foreign_id)),
        await conflict(env, req(env, other_project_path, upload_id=other_project_id)),
        await conflict(env, req(env, image_file(env.tmp, "x.jpg", (77, 1, 1)), upload_id=own_id)),
    ]
    rendered = {(type(e), e.code, str(e), e.args) for e in errors}
    assert rendered == {
        (PhotoUploadIdConflictError, "PHOTO_UPLOAD_ID_CONFLICT", PHOTO_UPLOAD_ID_CONFLICT_MESSAGE,
         (PHOTO_UPLOAD_ID_CONFLICT_MESSAGE,))
    }
    for e in errors:
        assert vars(e) == {}  # no attached metadata (owner, project, status, sha, keys)
        assert e.__cause__ is None and e.__context__ is None
