"""Stage 14C.3 owner follow-up — concurrent resume / finalize convergence
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §11, §12, §11a).

Interleavings are deterministic: the "other" request runs at a hooked point
with its own session (the test engine shares one SQLite connection). Raw
status updates in a second session model a parallel request that is
mid-flight (claimed or failed) at that exact point.
"""

import uuid

from sqlalchemy import update

from app.domain.exceptions import MediaStorageUnavailable, PhotoAssetTransitionConflictError
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_upload_service import PhotoUploadOutcome
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment
from tests import test_stage14c3_upload_service as harness
from tests.conftest import TestingSessionLocal
from tests.test_stage14c3_upload_service import (
    VARIANTS,
    counts,
    image_file,
    integrity,
    key_of,
    kinds,
    pending_with_all_objects,
    req,
    run_parallel,
    status_of,
    suffix,
)

env = harness.env  # shared pytest fixture
P, R, F = PhotoAssetStatus.PENDING, PhotoAssetStatus.READY, PhotoAssetStatus.FAILED


async def set_status(asset_id: uuid.UUID, status: PhotoAssetStatus) -> None:
    """A parallel request's committed transition, as seen by everyone else."""
    async with TestingSessionLocal() as other:
        await other.execute(update(PhotoAsset).where(PhotoAsset.id == asset_id).values(status=status))
        await other.commit()


async def assert_single_original_attachment(e, asset_id) -> None:
    rows = (await e.db.execute(
        PhotoAttachment.__table__.select().where(PhotoAttachment.asset_id == asset_id)
    )).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.context.value if hasattr(row.context, "value") else row.context) == "ROOM"
    assert row.room_id == e.room and row.caption is None and row.position == 0


def record_cas(monkeypatch) -> list[tuple[PhotoAssetStatus, PhotoAssetStatus, str]]:
    """Log every CAS attempt of this process: (expected, target, won|lost)."""
    log: list[tuple[PhotoAssetStatus, PhotoAssetStatus, str]] = []
    original = PhotoAssetService.compare_and_set_status

    async def spy(self, asset_id, owner_id, *, expected, target):
        try:
            result = await original(self, asset_id, owner_id, expected=expected, target=target)
        except PhotoAssetTransitionConflictError:
            log.append((expected, target, "lost"))
            raise
        log.append((expected, target, "won"))
        return result

    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", spy)
    return log


async def pending_missing(e, monkeypatch, missing: tuple[str, ...]):
    path = image_file(e.tmp)
    upload_id = str(uuid.uuid4())
    asset = await pending_with_all_objects(e, monkeypatch, path, upload_id)
    stored = {v: e.storage.inner.get_bytes(key_of(asset, v)) for v in VARIANTS}
    for variant in missing:
        e.storage.drop(key_of(asset, variant))
    e.storage.puts.clear()
    return path, upload_id, asset, stored


# ---------------------------------------------------------------------------
# A. PENDING + two concurrent resumes
# ---------------------------------------------------------------------------


async def test_pending_two_concurrent_resumes_write_once_and_converge(env, monkeypatch):
    path, upload_id, asset, stored = await pending_missing(env, monkeypatch, ("display", "thumbnail"))
    parallel = {}

    async def other_request_finishes_first(key, source):
        # A has HEADed and regenerated; B now does the same and finalizes.
        parallel["b"] = await run_parallel(env, path, upload_id)

    env.storage.before_put = other_request_finishes_first
    a = await env.service().upload(req(env, path, upload_id=upload_id, caption="changed"))
    assert parallel["b"].outcome is PhotoUploadOutcome.RESUMED
    assert a.outcome is PhotoUploadOutcome.CONCURRENTLY_FINALIZED and a.asset.status is R
    # Both requests PUT both derivatives; identical bytes make the second a no-op.
    display, thumb = key_of(asset, "display"), key_of(asset, "thumbnail")
    assert sorted(env.storage.puts) == sorted([display, thumb, display, thumb])
    assert env.storage.keys() == {key_of(asset, v) for v in VARIANTS}  # nothing deleted
    assert {v: env.storage.inner.get_bytes(key_of(asset, v)) for v in VARIANTS} == stored
    await assert_single_original_attachment(env, asset.id)
    assert (await integrity(env)).findings == []


async def test_concurrent_resume_never_overwrites_a_stored_object(env, monkeypatch):
    path, upload_id, asset, stored = await pending_missing(env, monkeypatch, ("display",))

    async def other_request_finishes_then_bytes_differ(key, source):
        await run_parallel(env, path, upload_id)  # B writes display and finalizes READY
        source.write_bytes(b"different derivative bytes")  # A's PUT now carries other bytes

    env.storage.before_put = other_request_finishes_then_bytes_differ
    a = await env.service().upload(req(env, path, upload_id=upload_id))
    # A's PUT hits write-once (MediaObjectConflict); its FAILED CAS loses to READY.
    assert a.outcome is PhotoUploadOutcome.CONCURRENTLY_FINALIZED
    assert await status_of(env.db, asset.id) is R
    assert env.storage.inner.get_bytes(key_of(asset, "display")) == stored["display"]
    await assert_single_original_attachment(env, asset.id)


# ---------------------------------------------------------------------------
# B. FAILED + two concurrent resumes
# ---------------------------------------------------------------------------


async def failed_asset(e, path, upload_id) -> uuid.UUID:
    e.storage.put_faults[suffix("thumbnail")] = MediaStorageUnavailable("timeout")
    try:
        await e.service().upload(req(e, path, upload_id=upload_id))
    except MediaStorageUnavailable:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected the thumbnail PUT to fail")
    e.storage.put_faults.clear()
    e.storage.puts.clear()
    asset_id = uuid.UUID(upload_id)
    assert await status_of(e.db, asset_id) is F
    return asset_id


async def test_failed_claim_loser_rereads_pending_and_resumes_without_claiming(env, monkeypatch):
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    asset_id = await failed_asset(env, path, upload_id)
    log = record_cas(monkeypatch)
    original = PhotoAssetService.compare_and_set_status
    state = {"done": False}

    async def other_request_claims_first(self, asset_id_, owner_id, *, expected, target):
        if expected is F and not state["done"]:
            state["done"] = True
            await set_status(asset_id, P)  # B won FAILED -> PENDING and is still working
        return await original(self, asset_id_, owner_id, expected=expected, target=target)

    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", other_request_claims_first)
    a = await env.service().upload(req(env, path, upload_id=upload_id, caption="changed"))
    # A lost the claim, re-read PENDING and resumed from it without a second claim.
    assert log == [(F, P, "lost"), (P, R, "won")]
    assert a.outcome is PhotoUploadOutcome.RESUMED and a.asset.status is R
    assert env.storage.puts == [key_of(a.asset, "thumbnail")]
    # B's stale continuation can neither finalize again nor regress READY.
    async with TestingSessionLocal() as b_db:
        for expected, target in ((P, R), (P, F)):
            try:
                await PhotoAssetService(b_db).compare_and_set_status(
                    asset_id, env.me, expected=expected, target=target
                )
            except PhotoAssetTransitionConflictError as lost:
                assert lost.current_status is R
            else:  # pragma: no cover
                raise AssertionError("stale CAS must lose")
    assert await status_of(env.db, asset_id) is R
    await assert_single_original_attachment(env, asset_id)


async def test_failed_claim_loser_sees_failed_again_and_claims_once_more(env, monkeypatch):
    """B claims, then B fails, both between A's read and A's re-read: A's
    claim loses, A re-reads FAILED (a NEW failure) and claims successfully."""
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    asset_id = await failed_asset(env, path, upload_id)
    log = record_cas(monkeypatch)
    spied = PhotoAssetService.compare_and_set_status
    original_reload = PhotoAssetService._reload
    state = {"claim": False, "fail": False}

    async def b_claims(self, asset_id_, owner_id, *, expected, target):
        if expected is F and not state["claim"]:
            state["claim"] = True
            await set_status(asset_id, P)  # B claims before A's UPDATE
            state["fail"] = True
        return await spied(self, asset_id_, owner_id, expected=expected, target=target)

    async def b_fails_before_a_rereads(self, asset_id_, owner_id):
        if state["fail"]:
            state["fail"] = False
            await set_status(asset_id, F)  # B's recovery failed after A's UPDATE lost
        return await original_reload(self, asset_id_, owner_id)

    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", b_claims)
    monkeypatch.setattr(PhotoAssetService, "_reload", b_fails_before_a_rereads)
    a = await env.service().upload(req(env, path, upload_id=upload_id))
    assert log == [(F, P, "lost"), (F, P, "won"), (P, R, "won")]
    assert a.outcome is PhotoUploadOutcome.RESUMED and a.asset.status is R
    await assert_single_original_attachment(env, asset_id)


# ---------------------------------------------------------------------------
# C. Finalize / failure interleavings; READY never regresses
# ---------------------------------------------------------------------------


async def test_finalize_lost_to_parallel_failure_reidentifies_and_finalizes(env, monkeypatch):
    """A writes everything; meanwhile a stale B records FAILED. A's READY CAS
    loses to FAILED -> step 8 -> claim FAILED -> PENDING -> all objects present
    with expected sizes -> READY."""
    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    log = record_cas(monkeypatch)

    async def b_records_failed(key, source):
        if key.endswith("/thumb.jpg"):
            await set_status(uuid.UUID(upload_id), F)
        else:
            env.storage.before_put = b_records_failed

    env.storage.before_put = b_records_failed
    a = await env.service().upload(req(env, path, upload_id=upload_id))
    assert log == [(P, R, "lost"), (F, P, "won"), (P, R, "won")]
    assert a.outcome is PhotoUploadOutcome.RESUMED and a.asset.status is R
    assert len(env.storage.puts) == 3  # the resume round found every object and wrote nothing
    await assert_single_original_attachment(env, a.asset.id)
    assert (await integrity(env)).findings == []


async def test_resume_put_failure_after_parallel_ready_keeps_ready(env, monkeypatch):
    path, upload_id, asset, stored = await pending_missing(env, monkeypatch, ("thumbnail",))
    log = record_cas(monkeypatch)

    async def b_finalizes_then_storage_fails(key, source):
        await run_parallel(env, path, upload_id)
        env.storage.put_faults[suffix("thumbnail")] = MediaStorageUnavailable("timeout")

    env.storage.before_put = b_finalizes_then_storage_fails
    a = await env.service().upload(req(env, path, upload_id=upload_id))
    assert a.outcome is PhotoUploadOutcome.CONCURRENTLY_FINALIZED
    assert log[-1] == (P, F, "lost")  # the stale FAILED could not be recorded
    assert await status_of(env.db, asset.id) is R
    assert env.storage.inner.get_bytes(key_of(asset, "thumbnail")) == stored["thumbnail"]
    await assert_single_original_attachment(env, asset.id)


async def test_resume_head_failure_after_parallel_ready_keeps_ready(env, monkeypatch):
    path, upload_id, asset, _ = await pending_missing(env, monkeypatch, ())

    async def b_finalizes_then_head_fails(key):
        await run_parallel(env, path, upload_id)
        env.storage.head_fault = MediaStorageUnavailable("timeout")

    env.storage.before_head = b_finalizes_then_head_fails
    a = await env.service().upload(req(env, path, upload_id=upload_id))
    assert a.outcome is PhotoUploadOutcome.CONCURRENTLY_FINALIZED
    assert await status_of(env.db, asset.id) is R
    await assert_single_original_attachment(env, asset.id)


async def test_no_transition_leaves_ready(env, monkeypatch):
    result = await env.service().upload(req(env, image_file(env.tmp)))
    asset_id = result.asset.id
    for expected in (P, F, R):
        for target in (P, F, R):
            try:
                await PhotoAssetService(env.db).compare_and_set_status(
                    asset_id, env.me, expected=expected, target=target
                )
            except Exception as exc:  # StateError (not allowed) or TransitionConflict (stale)
                assert type(exc).__name__ in {"PhotoAssetStateError", "PhotoAssetTransitionConflictError"}
            else:  # pragma: no cover
                raise AssertionError(f"{expected}->{target} must not apply to READY")
            assert await status_of(env.db, asset_id) is R


# ---------------------------------------------------------------------------
# FAILED-commit failure: the row stays PENDING and a retry recovers it
# ---------------------------------------------------------------------------


async def test_failed_commit_failure_is_recovered_by_retry(env, monkeypatch):
    from sqlalchemy.exc import OperationalError

    path = image_file(env.tmp)
    upload_id = str(uuid.uuid4())
    asset_id = uuid.UUID(upload_id)
    original_cas = PhotoAssetService.compare_and_set_status

    async def failed_commit_fails(self, asset_id_, owner_id, *, expected, target):
        if target is F:
            raise OperationalError("UPDATE photo_assets", {}, Exception("db down"))
        return await original_cas(self, asset_id_, owner_id, expected=expected, target=target)

    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", failed_commit_fails)
    env.storage.put_faults[suffix("display")] = MediaStorageUnavailable("timeout")
    try:
        await env.service().upload(req(env, path, upload_id=upload_id))
    except MediaStorageUnavailable:
        pass  # the storage error is the outcome, not the DB error
    else:  # pragma: no cover
        raise AssertionError("expected the storage error")
    assert await status_of(env.db, asset_id) is P
    assert kinds(await integrity(env)) == ["PENDING_INCOMPLETE"]  # 1/3 present, not ORPHAN_CANDIDATE
    monkeypatch.setattr(PhotoAssetService, "compare_and_set_status", original_cas)
    env.storage.put_faults.clear()
    env.storage.puts.clear()
    retry = await env.service().upload(req(env, path, upload_id=upload_id, caption="changed"))
    assert retry.outcome is PhotoUploadOutcome.RESUMED and retry.asset.status is R
    asset = retry.asset
    assert env.storage.puts == [key_of(asset, "display"), key_of(asset, "thumbnail")]
    assert (await integrity(env)).findings == []
    await assert_single_original_attachment(env, asset_id)
    assert await counts(env.db) == (1, 1)
