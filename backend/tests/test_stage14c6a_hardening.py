"""Stage 14C.6A hardening: F1 SQL parameter redaction, F2 60 s inter-chunk
idle receive timeout, F3 read transaction closed before body reception.

Uploads are driven at raw ASGI level with a controllable `receive` (stall at
message k, per-message gaps, a probe at the first body receive). The idle
timeout is shortened for tests by patching the module constant; the
production default stays exactly 60 s.
"""

import asyncio
import gc
import json
import logging
import math
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.datastructures import UploadFile

import app.models  # noqa: F401
from app.api import upload_guard
from app.api.upload_guard import RequestBodyIdleTimeoutError, limited_receive
from app.core.database import Base, create_app_engine
from app.main import app
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import BOUNDARY, form, image_bytes, path_for, temp_clean

api = c4.api  # shared fixture: uploads enabled, InMemory recording storage, shared session


# ---------------------------------------------------------------------------
# Controllable raw ASGI client
# ---------------------------------------------------------------------------


async def call(
    path: str,
    *,
    token: str | None,
    body: bytes,
    chunk: int = 64 * 1024,
    stall_after: int | None = None,
    gap: float = 0.0,
    on_first_receive=None,
) -> SimpleNamespace:
    headers = [(b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode()),
               (b"content-length", str(len(body)).encode())]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    chunks = [body[i:i + chunk] for i in range(0, len(body), chunk)] or [b""]
    state = {"delivered": 0, "receive_calls": 0}
    never = asyncio.Event()

    async def receive():
        state["receive_calls"] += 1
        if state["receive_calls"] == 1 and on_first_receive is not None:
            on_first_receive()
        if stall_after is not None and state["delivered"] >= stall_after:
            await never.wait()  # the client stops sending
        if state["delivered"] < len(chunks):
            if gap:
                await asyncio.sleep(gap)
            i = state["delivered"]
            state["delivered"] += 1
            return {"type": "http.request", "body": chunks[i], "more_body": i < len(chunks) - 1}
        await never.wait()
        return {"type": "http.disconnect"}  # pragma: no cover

    sent = {"status": None, "headers": {}, "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]
            sent["headers"] = {k.decode().lower(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            sent["body"] += message.get("body", b"")

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
             "headers": headers, "client": ("127.0.0.1", 1), "server": ("test", 80), "root_path": ""}
    await app(scope, receive, send)
    return SimpleNamespace(status=sent["status"], headers=sent["headers"], body=sent["body"],
                           delivered=state["delivered"])


def detail(c) -> dict:
    return json.loads(c.body)["detail"]


async def counts(db) -> tuple[int, int]:
    a = (await db.execute(select(func.count()).select_from(PhotoAsset))).scalar_one()
    b = (await db.execute(select(func.count()).select_from(PhotoAttachment))).scalar_one()
    return a, b


def open_uploads() -> list[UploadFile]:
    gc.collect()
    return [o for o in gc.get_objects() if isinstance(o, UploadFile) and not o.file.closed]


def assert_clean(a) -> None:
    assert a.runtime.admission.in_use == 0
    assert not a.runtime.processor._slot.locked()
    assert temp_clean(a)
    assert a.storage.puts == [] and a.storage.heads == []
    assert open_uploads() == []


# ---------------------------------------------------------------------------
# F1 — SQL bound parameters hidden
# ---------------------------------------------------------------------------

FAKE_SHA = "c0ffee" * 10 + "abcd"
FAKE_KEY = "photos/v1/11111111-2222-4333-8444-555555555555/original.jpg"
PRIVATE_FILENAME = "Kowalski_mieszkanie_PRYWATNE.jpg"
PRIVATE_CAPTION = "Pęknięcie u pana Nowaka, ul. Tajna 7"
SENSITIVE = (FAKE_SHA, FAKE_KEY, PRIVATE_FILENAME, PRIVATE_CAPTION)


async def failing_inserts(engine) -> list[IntegrityError]:
    """A CHECK-violating asset INSERT (sha256 / key / filename bound) and a
    CHECK-violating attachment INSERT (caption bound)."""
    from app.models.photo_asset import PhotoAsset as A

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    errors = []
    asset_row = dict(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), project_id=uuid.uuid4(), status=PhotoAssetStatus.READY,
        storage_name="r2-primary", storage_key_original=FAKE_KEY, storage_key_display=FAKE_KEY + ".d",
        storage_key_thumbnail=FAKE_KEY + ".t", content_type=PhotoContentType.JPEG, byte_size=0,  # CHECK > 0
        display_byte_size=1, thumbnail_byte_size=1, width=1, height=1, sha256=FAKE_SHA,
        original_filename=PRIVATE_FILENAME,
    )
    attachment_row = dict(
        id=uuid.uuid4(), asset_id=uuid.uuid4(), project_id=uuid.uuid4(), context=PhotoAttachmentContext.PROJECT,
        room_id=uuid.uuid4(),  # CHECK: PROJECT must not carry a room
        category=PhotoCategory.GENERAL, caption=PRIVATE_CAPTION,
    )
    for table, row in ((A.__table__, asset_row), (PhotoAttachment.__table__, attachment_row)):
        try:
            async with engine.begin() as conn:
                await conn.execute(table.insert().values(**row))
        except IntegrityError as exc:
            errors.append(exc)
    await engine.dispose()
    return errors


async def test_f1_app_engine_hides_bound_parameters_in_errors_and_logs(caplog):
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    errors = await failing_inserts(create_app_engine("sqlite+aiosqlite://"))
    assert len(errors) == 2
    texts = [str(e) for e in errors] + [repr(e) for e in errors] + [caplog.text]
    for text in texts:
        for value in SENSITIVE:
            assert value not in text
    for e in errors:
        assert "[SQL parameters hidden due to hide_parameters=True]" in str(e)
        assert e.hide_parameters is True


async def test_f1_control_without_hide_parameters_would_leak():
    """Proves the F1 test is sensitive: the same failures on an engine
    without hide_parameters expose every value."""
    errors = await failing_inserts(create_async_engine("sqlite+aiosqlite://"))
    joined = " ".join(str(e) for e in errors)
    for value in SENSITIVE:
        assert value in joined


def test_f1_the_application_engine_is_configured():
    from app.core.database import engine

    assert engine.sync_engine.hide_parameters is True


# ---------------------------------------------------------------------------
# F2 — inter-chunk idle receive timeout
# ---------------------------------------------------------------------------


def test_f2_production_default_is_exactly_60_seconds():
    assert upload_guard.UPLOAD_IDLE_TIMEOUT_SECONDS == 60.0
    assert c4.settings.PHOTO_UPLOADS_ENABLED in (True, False)  # module wiring sanity


async def test_f2_unit_each_receive_has_its_own_window():
    """5 messages, 0.1 s apart (0.5 s total) under a 0.3 s idle window: passes.
    The window is per receive, not cumulative."""
    async def slow():
        await asyncio.sleep(0.1)
        return {"type": "http.request", "body": b"x", "more_body": True}

    guarded = limited_receive(slow, 10**6, idle_timeout_seconds=0.3)
    for _ in range(5):
        assert (await guarded())["body"] == b"x"


async def test_f2_unit_stall_raises_idle_timeout():
    async def stalled():
        await asyncio.Event().wait()

    with pytest.raises(RequestBodyIdleTimeoutError):
        await limited_receive(stalled, 10**6, idle_timeout_seconds=0.05)()
    with pytest.raises(ValueError):
        limited_receive(stalled, 10**6, idle_timeout_seconds=0)


@pytest.fixture
def short_idle(monkeypatch):
    monkeypatch.setattr(upload_guard, "UPLOAD_IDLE_TIMEOUT_SECONDS", 0.2)


@pytest.mark.parametrize("stall_after", [0, 2], ids=["stall-first-receive", "stall-later-receive"])
async def test_f2_stalled_body_is_408_and_fully_cleaned_up(api, short_idle, stall_after):
    body = form(api, file=("a.jpg", "image/jpeg", b"\x03" * (3 * 1024 * 1024)))  # spool rolls to disk
    c = await call(path_for(api.project), token=api.token, body=body, chunk=1024 * 1024, stall_after=stall_after)
    assert c.status == 408
    assert detail(c) == {"code": "PHOTO_UPLOAD_TIMEOUT", "message": "The upload stalled; no data was received in time"}
    assert c.delivered == stall_after
    assert "timeout" not in c.body.decode().lower().replace("photo_upload_timeout", "")  # no internal text
    assert await counts(api.db) == (0, 0)
    assert_clean(api)


async def test_f2_slow_but_progressing_upload_succeeds(api, monkeypatch):
    monkeypatch.setattr(upload_guard, "UPLOAD_IDLE_TIMEOUT_SECONDS", 0.3)
    body = form(api, file=("a.jpg", "image/jpeg", image_bytes(size=(320, 240))))
    chunk = max(1, math.ceil(len(body) / 8))
    started = asyncio.get_running_loop().time()
    c = await call(path_for(api.project), token=api.token, body=body, chunk=chunk, gap=0.1)
    elapsed = asyncio.get_running_loop().time() - started
    assert c.status == 201, c.body
    assert c.delivered >= 8 and elapsed > 0.3 * 2  # total well beyond one idle window
    assert await counts(api.db) == (1, 1)


async def test_f2_capacity_is_available_again_after_timeouts(api, short_idle):
    for _ in range(3):  # more stalls than the admission capacity (2)
        c = await call(path_for(api.project), token=api.token, body=form(api), stall_after=0)
        assert c.status == 408
    ok = await call(path_for(api.project), token=api.token, body=form(api))
    assert ok.status == 201


# ---------------------------------------------------------------------------
# F3 — no transaction while the body is received; authorization still first
# ---------------------------------------------------------------------------


async def test_f3_no_transaction_at_first_body_receive_and_upload_succeeds(api):
    seen = {}
    c = await call(path_for(api.project), token=api.token, body=form(api),
                   on_first_receive=lambda: seen.setdefault("in_transaction", api.db.in_transaction()))
    assert seen == {"in_transaction": False}
    assert c.status == 201
    asset = await api.db.get(PhotoAsset, uuid.UUID(json.loads(c.body)["asset"]["id"]))
    assert asset.status is PhotoAssetStatus.READY and await counts(api.db) == (1, 1)


@pytest.mark.parametrize(
    ("target", "token_key", "status", "expected_code"),
    [("foreign", "token", 404, "PROJECT_NOT_FOUND"), ("missing", "token", 404, "PROJECT_NOT_FOUND"),
     ("own", None, 401, None)],
    ids=["foreign-project", "missing-project", "no-auth"],
)
async def test_f3_rejections_happen_before_any_body_receive(api, target, token_key, status, expected_code):
    project = {"foreign": api.foreign_project, "missing": uuid.uuid4(), "own": api.project}[target]
    probe = {"called": False}
    c = await call(path_for(project), token=getattr(api, token_key) if token_key else None, body=form(api),
                   on_first_receive=lambda: probe.update(called=True))
    assert c.status == status and c.delivered == 0 and probe["called"] is False
    if expected_code:
        assert detail(c)["code"] == expected_code
    assert api.runtime.admission.in_use == 0 and await counts(api.db) == (0, 0)


# ---------------------------------------------------------------------------
# F2 + F3 combined failure path
# ---------------------------------------------------------------------------


async def test_f2_f3_ownership_then_closed_txn_then_stall_then_408(api, short_idle):
    seen = {}
    body = form(api)
    c = await call(path_for(api.project), token=api.token, body=body, chunk=256, stall_after=1,
                   on_first_receive=lambda: seen.setdefault("in_transaction", api.db.in_transaction()))
    assert len(body) > 256 and c.delivered == 1  # stalled mid-body
    assert seen == {"in_transaction": False}  # ownership read done, transaction already closed
    assert c.status == 408 and detail(c)["code"] == "PHOTO_UPLOAD_TIMEOUT"
    assert api.db.in_transaction() is False  # nothing lingering from the aborted upload
    assert_clean(api)
    assert await counts(api.db) == (0, 0)
    assert api.runtime.admission.try_acquire() and api.runtime.admission.try_acquire()  # full capacity back
    api.runtime.admission.release()
    api.runtime.admission.release()
