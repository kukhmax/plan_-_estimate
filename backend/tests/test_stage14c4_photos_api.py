"""Stage 14C.4 — POST /api/projects/{project_id}/photos (HTTP boundary)
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §9–§11, §11b, §14, §17, §19–§21).

Requests are driven at the raw ASGI level with a spy `receive`, so the tests
can prove how many body messages were consumed, send a false Content-Length,
stream multi-message bodies and simulate a client disconnect. Storage is the
recording InMemoryMediaStorage from the 14C.3 harness.
"""

import io
import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.api import deps
from app.api.upload_guard import MAX_CONCURRENT_UPLOAD_REQUESTS, UploadAdmission
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.domain.exceptions import MediaStorageMisconfigured, MediaStorageUnavailable, PhotoInvalidImageError
from app.domain.photos.image_processing import ImagePipelineConfig, ImageProcessor
from app.domain.photos.temp import PHOTO_TEMP_PREFIX
from app.domain.services.photo_upload_service import PhotoUploadService
from app.main import app
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment
from tests.conftest import TestingSessionLocal
from tests.test_estimates import _make_opening, _make_project, _make_room, _make_surface, _make_user
from tests.test_stage14c3_upload_service import RecordingStorage, make_config, req

BOUNDARY = "testBOUNDARYx7"


# ---------------------------------------------------------------------------
# Raw ASGI harness
# ---------------------------------------------------------------------------


def multipart(parts: list[tuple[str, object]], boundary: str = BOUNDARY) -> bytes:
    """parts: (name, str) for scalars, (name, (filename, content_type, bytes)) for files."""
    out = io.BytesIO()
    for name, value in parts:
        out.write(f"--{boundary}\r\n".encode())
        if isinstance(value, tuple):
            filename, ctype, data = value
            out.write(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
            out.write(f"Content-Type: {ctype}\r\n\r\n".encode())
            out.write(data)
        else:
            out.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            out.write(str(value).encode())
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue()


class Call(SimpleNamespace):
    def json(self):
        return json.loads(self.body)


async def call(
    path: str,
    *,
    token: str | None,
    body: bytes = b"",
    chunk: int = 64 * 1024,
    content_type: str | None = f"multipart/form-data; boundary={BOUNDARY}",
    content_length: str | None = "auto",
    disconnect_after: int | None = None,
) -> Call:
    headers = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    if content_type:
        headers.append((b"content-type", content_type.encode()))
    if content_length == "auto":
        headers.append((b"content-length", str(len(body)).encode()))
    elif content_length is not None:
        headers.append((b"content-length", content_length.encode()))
    chunks = [body[i:i + chunk] for i in range(0, len(body), chunk)] or [b""]
    state = {"body_messages": 0}

    async def receive():
        if disconnect_after is not None and state["body_messages"] >= disconnect_after:
            return {"type": "http.disconnect"}
        if state["body_messages"] < len(chunks):
            i = state["body_messages"]
            state["body_messages"] += 1
            return {"type": "http.request", "body": chunks[i], "more_body": i < len(chunks) - 1}
        return {"type": "http.disconnect"}

    sent: dict = {"status": None, "headers": {}, "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]
            sent["headers"] = {k.decode().lower(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            sent["body"] += message.get("body", b"")

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
        "headers": headers, "client": ("127.0.0.1", 1), "server": ("test", 80), "root_path": "",
    }
    raised = None
    try:
        await app(scope, receive, send)
    except Exception as exc:  # ServerErrorMiddleware re-raises after sending 500
        raised = exc
    return Call(status=sent["status"], headers=sent["headers"], body=sent["body"],
                body_messages=state["body_messages"], raised=raised)


def image_bytes(fmt="JPEG", color=(200, 30, 30), size=(64, 48), **save) -> bytes:
    buf = io.BytesIO()
    image = Image.new("RGB", size, color)
    image.putpixel((1, 1), (0, 0, 0))
    image.save(buf, format=fmt, **save)
    return buf.getvalue()


@pytest.fixture
async def api(db_session, tmp_path, monkeypatch):
    me = await _make_user(db_session, 7401)
    other = await _make_user(db_session, 7402)
    project = await _make_project(db_session, me.id)
    project2 = await _make_project(db_session, me.id, name="Drugi")
    foreign_project = await _make_project(db_session, other.id, name="Obcy")
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    opening = await _make_opening(db_session, surface.id)
    foreign_room = await _make_room(db_session, foreign_project.id)
    temp_dir = tmp_path / "photo-temp"
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", True)
    monkeypatch.setattr(settings, "MEDIA_STORAGE_BACKEND", "s3")
    monkeypatch.setattr(settings, "PHOTO_TEMP_DIR", str(temp_dir))
    monkeypatch.setattr(settings, "PHOTO_PROCESSING_WAIT_SECONDS", 30.0)
    storage = RecordingStorage()
    runtime = deps.PhotoRuntime(
        processor=ImageProcessor(ImagePipelineConfig(), wait_seconds=5),
        storage=storage,
        admission=UploadAdmission(MAX_CONCURRENT_UPLOAD_REQUESTS),
    )

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[deps.get_photo_runtime] = lambda: runtime
    yield SimpleNamespace(
        db=db_session, tmp=tmp_path, temp_dir=temp_dir, runtime=runtime, storage=storage,
        me=me.id, other=other.id, project=project.id, project2=project2.id, foreign_project=foreign_project.id,
        room=room.id, surface=surface.id, opening=opening.id, foreign_room=foreign_room.id,
        token=create_access_token(me.id), other_token=create_access_token(other.id),
    )
    app.dependency_overrides.clear()


def path_for(project) -> str:
    return f"/api/projects/{project}/photos"


def form(a, *, upload_id=None, context="ROOM", file=None, extra=(), drop=(), target=None):
    parts: list[tuple[str, object]] = [("upload_id", upload_id or str(uuid.uuid4())), ("context", context)]
    if target is not None:
        parts.append(target)
    elif context == "ROOM":
        parts.append(("room_id", str(a.room)))
    parts.extend(extra)
    parts.append(("file", file or ("IMG_1.JPG", "image/jpeg", image_bytes())))
    return multipart([p for p in parts if p[0] not in drop])


async def counts(db) -> tuple[int, int]:
    a = (await db.execute(select(func.count()).select_from(PhotoAsset))).scalar_one()
    b = (await db.execute(select(func.count()).select_from(PhotoAttachment))).scalar_one()
    return a, b


def temp_clean(a) -> bool:
    return not a.temp_dir.exists() or not any(p.name.startswith(PHOTO_TEMP_PREFIX) for p in a.temp_dir.iterdir())


def detail(c: Call) -> dict:
    return c.json()["detail"]


# ---------------------------------------------------------------------------
# Auth and upload gate: no body consumed
# ---------------------------------------------------------------------------


async def test_unauthenticated_reads_no_body(api):
    c = await call(path_for(api.project), token=None, body=form(api))
    assert c.status == 401 and c.body_messages == 0


@pytest.mark.parametrize(
    "overrides",
    [{"PHOTO_UPLOADS_ENABLED": False}, {"MEDIA_STORAGE_BACKEND": "disabled"}],
    ids=["flag-off", "storage-disabled"],
)
async def test_disabled_gate_reads_no_body_and_writes_nothing(api, monkeypatch, overrides):
    for key, value in overrides.items():
        monkeypatch.setattr(settings, key, value)
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 503 and detail(c)["code"] == "PHOTO_UPLOADS_DISABLED"
    assert "retry-after" not in c.headers
    assert c.body_messages == 0
    assert await counts(api.db) == (0, 0) and api.storage.puts == [] and api.storage.heads == []
    assert api.runtime.admission.in_use == 0


async def test_gate_precedes_project_ownership(api, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", False)
    c = await call(path_for(api.foreign_project), token=api.token, body=form(api))
    assert c.status == 503 and c.body_messages == 0


async def test_foreign_project_404_before_body(api):
    c = await call(path_for(api.foreign_project), token=api.token, body=form(api))
    assert c.status == 404 and detail(c)["code"] == "PROJECT_NOT_FOUND" and c.body_messages == 0


# ---------------------------------------------------------------------------
# Request limit (27 000 000 actual bytes)
# ---------------------------------------------------------------------------


async def test_declared_oversize_rejected_before_body(api):
    c = await call(path_for(api.project), token=api.token, body=form(api), content_length="27000001")
    assert c.status == 413 and detail(c)["code"] == "PHOTO_TOO_LARGE" and c.body_messages == 0


@pytest.mark.parametrize("raw", ["abc", "-5", "1,2"])
async def test_malformed_content_length_rejected_before_body(api, raw):
    c = await call(path_for(api.project), token=api.token, body=form(api), content_length=raw)
    assert c.status == 422 and detail(c)["code"] == "PHOTO_UPLOAD_MALFORMED" and c.body_messages == 0


def oversized_body(a) -> bytes:
    return form(a, file=("big.jpg", "image/jpeg", b"\xff" * 40_000_000))


@pytest.mark.parametrize(
    "content_length", [None, "1000"], ids=["missing-content-length", "false-small-content-length"]
)
async def test_actual_body_over_request_limit_is_cut_off(api, content_length):
    body = oversized_body(api)
    c = await call(path_for(api.project), token=api.token, body=body, chunk=1024 * 1024,
                   content_length=content_length)
    assert c.status == 413 and detail(c)["code"] == "PHOTO_TOO_LARGE"
    assert c.body_messages == math.ceil(27_000_001 / (1024 * 1024))  # stopped at the crossing message
    assert c.body_messages < math.ceil(len(body) / (1024 * 1024))
    assert temp_clean(api) and api.runtime.admission.in_use == 0 and await counts(api.db) == (0, 0)


async def test_multi_message_small_chunks_cannot_bypass(api, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_MAX_REQUEST_BYTES", 30_000)
    monkeypatch.setattr(settings, "PHOTO_MAX_UPLOAD_BYTES", 20_000)
    body = form(api, file=("a.jpg", "image/jpeg", b"\x00" * 40_000))
    c = await call(path_for(api.project), token=api.token, body=body, chunk=7, content_length=None)
    assert c.status == 413 and c.body_messages == math.ceil(30_001 / 7)


async def test_request_exactly_at_limit_passes_the_request_guard(api, monkeypatch):
    """A body of exactly PHOTO_MAX_REQUEST_BYTES is fully read; what happens
    next is decided by the file / image checks, not by the request guard."""
    probe = form(api, upload_id="00000000-0000-4000-8000-000000000000", file=("a.jpg", "image/jpeg", b""))
    file_len = 10_000 - len(probe)
    body = form(api, upload_id="00000000-0000-4000-8000-000000000000",
                file=("a.jpg", "image/jpeg", b"\x00" * file_len))
    assert len(body) == 10_000
    monkeypatch.setattr(settings, "PHOTO_MAX_REQUEST_BYTES", 10_000)
    monkeypatch.setattr(settings, "PHOTO_MAX_UPLOAD_BYTES", 9_900)
    c = await call(path_for(api.project), token=api.token, body=body, chunk=1000)
    assert c.status == 415  # parsed completely, file accepted, image unsupported
    assert c.body_messages == 10


# ---------------------------------------------------------------------------
# File limit (25 000 000 actual bytes)
# ---------------------------------------------------------------------------


def stub_pipeline(api, monkeypatch) -> list[int]:
    seen: list[int] = []

    def process(source: Path, workspace: Path, config):
        seen.append(source.stat().st_size)
        raise PhotoInvalidImageError("stub")

    api.runtime.processor = ImageProcessor(ImagePipelineConfig(), wait_seconds=5, process_fn=process)
    return seen


async def test_file_of_exactly_25_000_000_bytes_reaches_the_pipeline(api, monkeypatch):
    seen = stub_pipeline(api, monkeypatch)
    body = form(api, file=("a.jpg", "image/jpeg", b"\x01" * 25_000_000))
    c = await call(path_for(api.project), token=api.token, body=body, chunk=1024 * 1024)
    assert c.status == 422 and detail(c)["code"] == "PHOTO_INVALID_IMAGE"
    assert seen == [25_000_000]
    assert temp_clean(api)


async def test_file_of_25_000_001_bytes_is_rejected(api, monkeypatch):
    seen = stub_pipeline(api, monkeypatch)
    body = form(api, file=("a.jpg", "image/jpeg", b"\x01" * 25_000_001))
    c = await call(path_for(api.project), token=api.token, body=body, chunk=1024 * 1024)
    assert c.status == 413 and detail(c)["code"] == "PHOTO_TOO_LARGE"
    assert seen == [] and temp_clean(api) and await counts(api.db) == (0, 0)


# ---------------------------------------------------------------------------
# Multipart validation
# ---------------------------------------------------------------------------


async def test_wrong_content_type_rejected_without_reading_body(api):
    c = await call(path_for(api.project), token=api.token, body=b'{"a": 1}', content_type="application/json")
    assert c.status == 422 and detail(c)["code"] == "PHOTO_UPLOAD_MALFORMED" and c.body_messages == 0


@pytest.mark.parametrize(
    ("label", "body_fn", "content_type"),
    [
        ("garbage", lambda a: b"this is not multipart at all", None),
        ("missing-boundary", lambda a: form(a), "multipart/form-data"),
        ("two-files", lambda a: form(a, extra=[("file2", ("b.jpg", "image/jpeg", image_bytes()))]), None),
        ("duplicate-file", lambda a: form(a, extra=[("file", ("b.jpg", "image/jpeg", image_bytes()))]), None),
        ("duplicate-scalar", lambda a: form(a, extra=[("caption", "a"), ("caption", "b")]), None),
        ("unknown-field", lambda a: form(a, extra=[("position", "3")]), None),
        ("too-many-fields", lambda a: form(a, extra=[("caption", "x")] * 5), None),
        ("oversized-scalar", lambda a: form(a, extra=[("caption", "c" * 8193)]), None),
        ("missing-file", lambda a: form(a, drop=("file",)), None),
        ("missing-upload-id", lambda a: form(a, drop=("upload_id",)), None),
        ("scalar-sent-as-file", lambda a: form(a, extra=[("caption", ("c.txt", "text/plain", b"x"))]), None),
        ("file-sent-as-scalar", lambda a: multipart(
            [("upload_id", str(uuid.uuid4())), ("context", "PROJECT"), ("file", "not-a-file")]), None),
        ("bad-upload-id", lambda a: form(a, upload_id=str(uuid.uuid4()).upper()), None),
        ("bad-context", lambda a: form(a, context="GALLERY"), None),
        ("bad-category", lambda a: form(a, extra=[("category", "SELFIE")]), None),
        ("bad-include", lambda a: form(a, extra=[("include_in_report", "yes")]), None),
        ("bad-target-uuid", lambda a: form(a, target=("room_id", "not-a-uuid")), None),
        ("target-missing", lambda a: form(a, target=("caption", "no room id")), None),
        ("caption-too-long", lambda a: form(a, extra=[("caption", "c" * 1001)]), None),
    ],
)
async def test_malformed_multipart_is_422(api, label, body_fn, content_type):
    c = await call(path_for(api.project), token=api.token, body=body_fn(api),
                   content_type=content_type or f"multipart/form-data; boundary={BOUNDARY}")
    assert c.status == 422, (label, c.status, c.body)
    assert detail(c) == {"code": "PHOTO_UPLOAD_MALFORMED", "message": "The upload request is malformed"}
    assert await counts(api.db) == (0, 0) and temp_clean(api) and api.runtime.admission.in_use == 0


async def test_work_without_surface_and_occurrence_is_malformed(api):
    # WORK is enabled since 14H.1; without its surface and occurrence the form is a shape error (no context is unsupported).
    c = await call(path_for(api.project), token=api.token,
                   body=form(api, context="WORK", target=("caption", "x")))
    assert c.status == 422 and detail(c)["code"] == "PHOTO_UPLOAD_MALFORMED"


async def test_foreign_target_is_404(api):
    c = await call(path_for(api.project), token=api.token, body=form(api, target=("room_id", str(api.foreign_room))))
    assert c.status == 404 and detail(c)["code"] == "ROOM_NOT_FOUND"


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("fmt", "ctype"), [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
async def test_supported_formats_created(api, fmt, ctype):
    c = await call(path_for(api.project), token=api.token,
                   body=form(api, file=("photo.bin", "application/octet-stream", image_bytes(fmt))))
    assert c.status == 201, c.body
    assert c.json()["asset"]["content_type"] == ctype


async def test_declared_mime_is_ignored_decoded_format_wins(api):
    c = await call(path_for(api.project), token=api.token,
                   body=form(api, file=("x.jpg", "image/jpeg", image_bytes("PNG"))))
    assert c.status == 201 and c.json()["asset"]["content_type"] == "image/png"


async def test_unsupported_format_415(api):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, format="GIF")
    c = await call(path_for(api.project), token=api.token, body=form(api, file=("a.gif", "image/gif", buf.getvalue())))
    assert c.status == 415 and detail(c)["code"] == "PHOTO_UNSUPPORTED_FORMAT"
    assert await counts(api.db) == (0, 0) and temp_clean(api)


async def test_over_60_megapixels_422(api):
    buf = io.BytesIO()
    Image.new("1", (8000, 8000)).save(buf, format="PNG")  # 64 MP, tiny file
    body = form(api, file=("big.png", "image/png", buf.getvalue()))
    c = await call(path_for(api.project), token=api.token, body=body)
    assert c.status == 422 and detail(c)["code"] == "PHOTO_TOO_MANY_PIXELS"


async def test_animated_image_422(api):
    frames = [Image.new("RGB", (16, 16), (i * 80, 0, 0)) for i in range(3)]
    buf = io.BytesIO()
    frames[0].save(buf, format="PNG", save_all=True, append_images=frames[1:])
    c = await call(path_for(api.project), token=api.token, body=form(api, file=("a.png", "image/png", buf.getvalue())))
    assert c.status == 422 and detail(c)["code"] == "PHOTO_ANIMATED_NOT_SUPPORTED"


# ---------------------------------------------------------------------------
# Responses, outcomes, presigned URLs
# ---------------------------------------------------------------------------


ASSET_KEYS = {"id", "project_id", "status", "content_type", "byte_size", "width", "height", "original_filename",
              "captured_at", "capture_source", "uploaded_at", "archived_at"}  # capture_source: 14E.2 (D11)


async def test_created_201_with_presigned_urls_and_no_internal_fields(api, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_SIGNED_URL_TTL_SECONDS", 120)
    upload_id = str(uuid.uuid4())
    before = datetime.now(UTC)
    c = await call(path_for(api.project), token=api.token,
                   body=form(api, upload_id=upload_id, extra=[("caption", " przed "), ("category", "BEFORE"),
                                                              ("include_in_report", "true")]))
    assert c.status == 201, c.body
    data = c.json()
    assert set(data["asset"]) == ASSET_KEYS
    assert data["asset"]["id"] == upload_id and data["asset"]["status"] == "READY"
    assert data["asset"]["original_filename"] == "IMG_1.JPG"
    att = data["attachment"]
    assert (att["context"], att["room_id"], att["caption"], att["category"], att["include_in_report"]) == (
        "ROOM", str(api.room), "przed", "BEFORE", True,
    )
    asset = await api.db.get(PhotoAsset, uuid.UUID(upload_id))
    assert data["thumbnail_url"] == f"memory://media/{quote(asset.storage_key_thumbnail)}?expires=120"
    assert data["display_url"] == f"memory://media/{quote(asset.storage_key_display)}?expires=120"
    expires = datetime.fromisoformat(data["urls_expire_at"])
    assert before + timedelta(seconds=119) <= expires <= datetime.now(UTC) + timedelta(seconds=121)
    assert data["storage"] == {"state": "OK"}
    raw = c.body.decode()
    assert "sha256" not in raw and asset.sha256 not in raw and "storage_key" not in raw
    assert str(api.temp_dir) not in raw
    assert temp_clean(api) and api.runtime.admission.in_use == 0


async def test_replayed_200_and_metadata_ignored(api):
    upload_id = str(uuid.uuid4())
    file = ("a.jpg", "image/jpeg", image_bytes())
    first = await call(path_for(api.project), token=api.token, body=form(api, upload_id=upload_id, file=file))
    api.storage.puts.clear()
    again = await call(path_for(api.project), token=api.token,
                       body=form(api, upload_id=upload_id, file=file, extra=[("caption", "new")]))
    assert (first.status, again.status) == (201, 200)
    assert again.json()["attachment"]["id"] == first.json()["attachment"]["id"]
    assert again.json()["attachment"]["caption"] is None
    assert api.storage.puts == [] and await counts(api.db) == (1, 1)


async def test_resumed_201_after_storage_failure(api):
    upload_id = str(uuid.uuid4())
    file = ("a.jpg", "image/jpeg", image_bytes())
    api.storage.put_faults["/thumb.jpg"] = MediaStorageUnavailable("timeout")
    failed = await call(path_for(api.project), token=api.token, body=form(api, upload_id=upload_id, file=file))
    assert failed.status == 503 and detail(failed)["code"] == "PHOTO_STORAGE_UNAVAILABLE"
    assert "retry-after" not in failed.headers
    api.storage.put_faults.clear()
    api.storage.puts.clear()
    resumed = await call(path_for(api.project), token=api.token, body=form(api, upload_id=upload_id, file=file))
    assert resumed.status == 201 and resumed.json()["asset"]["status"] == "READY"
    assert len(api.storage.puts) == 1 and api.storage.puts[0].endswith("/thumb.jpg")


async def test_concurrently_finalized_200(api):
    upload_id = str(uuid.uuid4())
    data = image_bytes()
    source = api.tmp / "parallel.jpg"
    source.write_bytes(data)

    async def parallel_request_finishes_first(key, _source):
        async with TestingSessionLocal() as other_db:
            service = PhotoUploadService(
                other_db, api.storage, ImageProcessor(ImagePipelineConfig(), wait_seconds=5),
                make_config(api.tmp, temp_dir=str(api.temp_dir)),
            )
            e = SimpleNamespace(me=api.me, project=api.project, room=api.room)
            await service.upload(req(e, source, upload_id=upload_id))

    api.storage.before_put = parallel_request_finishes_first
    c = await call(path_for(api.project), token=api.token,
                   body=form(api, upload_id=upload_id, file=("a.jpg", "image/jpeg", data)))
    assert c.status == 200 and c.json()["asset"]["status"] == "READY"
    assert await counts(api.db) == (1, 1)


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [(MediaStorageMisconfigured("403"), 500, "PHOTO_STORAGE_ERROR")],
)
async def test_storage_misconfigured_is_generic_500(api, error, status_code, code):
    api.storage.put_faults["/original.jpg"] = error
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == status_code and detail(c) == {"code": code, "message": "Photo storage error"}
    assert "403" not in c.body.decode()


async def test_quota_409(api, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_STORAGE_WARNING_BYTES", 1)
    monkeypatch.setattr(settings, "PHOTO_STORAGE_SOFT_CAP_BYTES", 10)
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 409 and detail(c)["code"] == "PHOTO_STORAGE_QUOTA_EXCEEDED"
    assert await counts(api.db) == (0, 0) and temp_clean(api)


# ---------------------------------------------------------------------------
# Uniform upload_id conflict (privacy)
# ---------------------------------------------------------------------------


async def test_conflict_bodies_are_byte_identical(api):
    foreign_id, own_other_project_id, own_id = (str(uuid.uuid4()) for _ in range(3))
    foreign_bytes = image_bytes(color=(1, 2, 3))
    other_project_bytes = image_bytes(color=(4, 5, 6))
    own_bytes = image_bytes(color=(7, 8, 9))
    assert (await call(path_for(api.foreign_project), token=api.other_token, body=form(
        api, upload_id=foreign_id, context="PROJECT", file=("a.jpg", "image/jpeg", foreign_bytes)))).status == 201
    assert (await call(path_for(api.project2), token=api.token, body=form(
        api, upload_id=own_other_project_id, context="PROJECT",
        file=("a.jpg", "image/jpeg", other_project_bytes)))).status == 201
    assert (await call(path_for(api.project), token=api.token, body=form(
        api, upload_id=own_id, file=("a.jpg", "image/jpeg", own_bytes)))).status == 201
    conflicts = [
        await call(path_for(api.project), token=api.token,
                   body=form(api, upload_id=foreign_id, file=("a.jpg", "image/jpeg", foreign_bytes))),
        await call(path_for(api.project), token=api.token,
                   body=form(api, upload_id=own_other_project_id, file=("a.jpg", "image/jpeg", other_project_bytes))),
        await call(path_for(api.project), token=api.token,
                   body=form(api, upload_id=own_id, file=("a.jpg", "image/jpeg", image_bytes(color=(0, 0, 1))))),
    ]
    assert {c.status for c in conflicts} == {409}
    assert len({c.body for c in conflicts}) == 1
    assert detail(conflicts[0]) == {
        "code": "PHOTO_UPLOAD_ID_CONFLICT",
        "message": "upload_id cannot be used for this upload; generate a new one",
    }
    assert {tuple(sorted(c.headers.items())) for c in conflicts} == {tuple(sorted(conflicts[0].headers.items()))}
    assert temp_clean(api) and api.runtime.admission.in_use == 0


# ---------------------------------------------------------------------------
# Admission (2 in flight, independent of the processing slot)
# ---------------------------------------------------------------------------


async def test_third_request_rejected_before_body_when_two_in_flight(api):
    assert api.runtime.admission.try_acquire() and api.runtime.admission.try_acquire()
    try:
        c = await call(path_for(api.project), token=api.token, body=form(api))
    finally:
        api.runtime.admission.release()
        api.runtime.admission.release()
    assert c.status == 503 and detail(c)["code"] == "PHOTO_PROCESSING_BUSY"
    assert c.headers["retry-after"] == "30"  # = ceil(PHOTO_PROCESSING_WAIT_SECONDS)
    assert c.body_messages == 0 and await counts(api.db) == (0, 0)


async def test_one_free_admission_slot_is_enough(api):
    assert api.runtime.admission.try_acquire()
    try:
        c = await call(path_for(api.project), token=api.token, body=form(api))
    finally:
        api.runtime.admission.release()
    assert c.status == 201


async def test_retry_after_follows_the_processing_wait_setting(api, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_PROCESSING_WAIT_SECONDS", 12.5)
    api.runtime.admission.try_acquire()
    api.runtime.admission.try_acquire()
    try:
        c = await call(path_for(api.project), token=api.token, body=form(api))
    finally:
        api.runtime.admission.release()
        api.runtime.admission.release()
    assert c.headers["retry-after"] == "13"


async def test_processing_slot_busy_is_independent_of_admission(api):
    api.runtime.processor = ImageProcessor(ImagePipelineConfig(), wait_seconds=0.05)
    async with api.runtime.processor.slot():
        c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 503 and detail(c)["code"] == "PHOTO_PROCESSING_BUSY"
    assert c.headers["retry-after"] == "30"
    assert c.body_messages > 0  # admitted: the body was received, then processing was busy
    assert api.runtime.admission.in_use == 0 and temp_clean(api) and await counts(api.db) == (0, 0)


# ---------------------------------------------------------------------------
# Cleanup on every controlled exit
# ---------------------------------------------------------------------------


async def test_client_disconnect_mid_body_cleans_up(api):
    body = form(api, file=("a.jpg", "image/jpeg", b"\x02" * 300_000))
    c = await call(path_for(api.project), token=api.token, body=body, chunk=64 * 1024, disconnect_after=2)
    assert c.body_messages == 2
    assert temp_clean(api) and api.runtime.admission.in_use == 0 and await counts(api.db) == (0, 0)


async def test_unexpected_domain_exception_cleans_up(api, monkeypatch):
    async def boom(self, request):
        assert Path(request.original_path).exists()
        raise RuntimeError("unexpected")

    monkeypatch.setattr(PhotoUploadService, "upload", boom)
    monkeypatch.setattr(app, "debug", False)  # production: DEBUG=false (no traceback page)
    monkeypatch.setattr(app, "middleware_stack", None)  # rebuilt with debug=False
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 500 and isinstance(c.raised, RuntimeError)
    assert "unexpected" not in c.body.decode()
    assert temp_clean(api) and api.runtime.admission.in_use == 0


async def test_spool_is_closed_before_the_domain_call(api, monkeypatch):
    seen = {}
    original_upload = PhotoUploadService.upload

    async def spy(self, request):
        # The multipart file part was copied and its spool closed already.
        seen["original_exists"] = Path(request.original_path).exists()
        import gc

        from starlette.datastructures import UploadFile
        seen["open_uploads"] = [o for o in gc.get_objects() if isinstance(o, UploadFile) and not o.file.closed]
        return await original_upload(self, request)

    monkeypatch.setattr(PhotoUploadService, "upload", spy)
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 201 and seen["original_exists"] is True and seen["open_uploads"] == []


async def test_status_ready_rows_after_success(api):
    c = await call(path_for(api.project), token=api.token, body=form(api))
    asset = await api.db.get(PhotoAsset, uuid.UUID(c.json()["asset"]["id"]))
    assert asset.status is PhotoAssetStatus.READY


# ---------------------------------------------------------------------------
# Owner follow-up: field counts, exception boundary, post-READY presign
# failure, gate ordering
# ---------------------------------------------------------------------------

ALL_OPTIONAL = [
    ("category", "DEFECT"), ("caption", "pełny opis"), ("include_in_report", "true"),
    ("source", "CAMERA"),  # 14E.2 (owner decision D11): the optional client-declared entry path
]


@pytest.mark.parametrize(
    ("context", "target"),
    [("PROJECT", None), ("ROOM", "room_id"), ("SURFACE", "surface_id"), ("OPENING", "opening_id")],
)
async def test_every_maximal_valid_field_set_is_accepted(api, context, target):
    scalars = [("upload_id", str(uuid.uuid4())), ("context", context)]
    if target:
        scalars.append((target, str(getattr(api, target.removesuffix("_id")))))
    scalars += ALL_OPTIONAL
    assert len(scalars) == (6 if context == "PROJECT" else 7)  # MAX_FIELDS = 7; the file is a file, not a field
    c = await call(path_for(api.project), token=api.token,
                   body=multipart([*scalars, ("file", ("a.jpg", "image/jpeg", image_bytes()))]))
    assert c.status == 201, c.body
    att = c.json()["attachment"]
    assert (att["context"], att["category"], att["caption"], att["include_in_report"]) == (
        context, "DEFECT", "pełny opis", True,
    )
    assert c.json()["asset"]["capture_source"] == "CAMERA"


async def test_eighth_distinct_scalar_field_is_rejected(api):
    body = form(api, extra=[*ALL_OPTIONAL, ("surface_id", str(api.surface))])  # 8 scalar fields
    c = await call(path_for(api.project), token=api.token, body=body)
    assert c.status == 422 and detail(c)["code"] == "PHOTO_UPLOAD_MALFORMED"
    assert await counts(api.db) == (0, 0)


@pytest.mark.parametrize(
    "parts",
    [
        # unknown field in place of upload_id (within max_fields)
        lambda a: [("context", "PROJECT"), ("uploadid", str(uuid.uuid4())), *ALL_OPTIONAL],
        # unknown field in place of context
        lambda a: [("upload_id", str(uuid.uuid4())), ("ctx", "PROJECT"), *ALL_OPTIONAL],
        # unknown field in place of the required room_id
        lambda a: [("upload_id", str(uuid.uuid4())), ("context", "ROOM"), ("room", str(a.room)), *ALL_OPTIONAL],
    ],
    ids=["no-upload-id", "no-context", "no-room-id"],
)
async def test_unknown_field_cannot_displace_a_required_one(api, parts):
    body = multipart([*parts(api), ("file", ("a.jpg", "image/jpeg", image_bytes()))])
    c = await call(path_for(api.project), token=api.token, body=body)
    assert c.status == 422 and detail(c)["code"] == "PHOTO_UPLOAD_MALFORMED"
    assert await counts(api.db) == (0, 0)


async def test_http_400_raised_after_parsing_is_not_remapped(api, monkeypatch):
    """The malformed remap is local to multipart parsing: an unrelated
    HTTPException(400) from later code keeps its own status and body."""
    from fastapi import HTTPException

    async def unrelated(self, request):
        raise HTTPException(status_code=400, detail={"code": "SOMETHING_ELSE", "message": "x"})

    monkeypatch.setattr(PhotoUploadService, "upload", unrelated)
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 400 and detail(c) == {"code": "SOMETHING_ELSE", "message": "x"}
    assert temp_clean(api) and api.runtime.admission.in_use == 0


async def test_domain_errors_after_parsing_keep_their_own_codes(api):
    c = await call(path_for(api.project), token=api.token, body=form(api, target=("room_id", str(uuid.uuid4()))))
    assert c.status == 404 and detail(c)["code"] == "ROOM_NOT_FOUND"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (MediaStorageUnavailable("presign: endpoint unreachable 10.0.0.7"), 503, "PHOTO_STORAGE_UNAVAILABLE"),
        (MediaStorageMisconfigured("presign: bad credentials AKIAEXAMPLE"), 500, "PHOTO_STORAGE_ERROR"),
    ],
    ids=["unavailable", "misconfigured"],
)
async def test_presign_failure_after_ready_leaves_the_upload_intact(api, monkeypatch, error, status_code, code):
    upload_id = str(uuid.uuid4())
    file = ("a.jpg", "image/jpeg", image_bytes())
    domain_calls = []
    original_upload = PhotoUploadService.upload

    async def counting_upload(self, request):
        domain_calls.append(request.upload_id)
        return await original_upload(self, request)

    async def failing_presign(key, ttl_seconds):
        raise error

    original_presign = api.storage.presign_get
    monkeypatch.setattr(PhotoUploadService, "upload", counting_upload)
    monkeypatch.setattr(api.storage, "presign_get", failing_presign)
    c = await call(path_for(api.project), token=api.token, body=form(api, upload_id=upload_id, file=file))
    assert c.status == status_code and detail(c)["code"] == code
    assert "retry-after" not in c.headers
    raw = c.body.decode()
    for secret in ("10.0.0.7", "AKIAEXAMPLE", "photos/v1", "sha256", str(api.temp_dir)):
        assert secret not in raw
    asset = await api.db.get(PhotoAsset, uuid.UUID(upload_id), populate_existing=True)
    assert asset.status is PhotoAssetStatus.READY  # no CAS back to FAILED
    assert raw.find(asset.sha256) == -1
    assert await counts(api.db) == (1, 1)  # exactly one first attachment
    assert len(api.storage.keys()) == 3 and domain_calls == [upload_id]  # no delete, no second run
    assert temp_clean(api) and api.runtime.admission.in_use == 0
    # The client's retry with the same upload_id is a plain replay.
    monkeypatch.setattr(api.storage, "presign_get", original_presign)
    replay = await call(path_for(api.project), token=api.token, body=form(api, upload_id=upload_id, file=file))
    assert replay.status == 200 and replay.json()["thumbnail_url"].startswith("memory://media/")
    assert await counts(api.db) == (1, 1) and domain_calls == [upload_id, upload_id]


async def test_unauthenticated_is_401_even_when_uploads_are_disabled(api, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", False)
    c = await call(path_for(api.project), token=None, body=form(api))
    assert c.status == 401 and c.body_messages == 0


async def test_disabled_gate_touches_no_project_admission_workspace_or_storage(api, monkeypatch):
    from app.domain.services.project_service import ProjectService

    calls = {"project": 0, "admission": 0}
    original_get = ProjectService.get_project
    original_acquire = api.runtime.admission.try_acquire

    async def spy_get(self, *a, **k):
        calls["project"] += 1
        return await original_get(self, *a, **k)

    def spy_acquire():
        calls["admission"] += 1
        return original_acquire()

    monkeypatch.setattr(ProjectService, "get_project", spy_get)
    monkeypatch.setattr(api.runtime.admission, "try_acquire", spy_acquire)
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", False)
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 503 and detail(c)["code"] == "PHOTO_UPLOADS_DISABLED" and c.body_messages == 0
    assert calls == {"project": 0, "admission": 0}
    assert not api.temp_dir.exists()  # no workspace (the temp dir was never even created)
    assert api.storage.puts == [] and api.storage.heads == [] and await counts(api.db) == (0, 0)


async def test_admission_is_taken_before_the_body_and_workspace_lives_through_the_domain_call(api, monkeypatch):
    seen = {}
    original_acquire = api.runtime.admission.try_acquire
    original_upload = PhotoUploadService.upload
    state: dict = {}

    def spy_acquire():
        state["acquired"] = True
        return original_acquire()

    async def spy_upload(self, request):
        seen["in_use"] = api.runtime.admission.in_use
        seen["workspace_alive"] = Path(request.original_path).parent.exists()
        return await original_upload(self, request)

    monkeypatch.setattr(api.runtime.admission, "try_acquire", spy_acquire)
    monkeypatch.setattr(PhotoUploadService, "upload", spy_upload)
    c = await call(path_for(api.project), token=api.token, body=form(api))
    assert c.status == 201 and state["acquired"]
    assert seen == {"in_use": 1, "workspace_alive": True}
    assert api.runtime.admission.in_use == 0 and temp_clean(api)
