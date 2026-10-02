"""Stage 14C.6B — temp-disk probe for concurrent upload reception.

Measures (and bounds) the real on-disk temp footprint at the worst moment:
two admitted uploads whose multipart spool AND workspace copy coexist
(the copy runs while the form is still open). A thread barrier inside the
bounded copy holds both requests at that moment. Footprint =
files under PHOTO_TEMP_DIR + Starlette's unnamed spool files (deleted-but-
open fds in the system temp dir). A second probe measures one valid upload
during processing (spool closed; workspace copy + derivatives).

Run with `-s` to see the measured numbers.
"""

import asyncio
import io
import os
import random
import tempfile
import threading
import uuid
from pathlib import Path

from PIL import Image

from app.api.v1.endpoints import photos as photos_endpoint
from app.core.database import get_db
from app.main import app
from tests.conftest import TestingSessionLocal
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import path_for
from tests.test_stage14c6a_hardening import assert_clean, counts
from tests.test_stage14c6b_http_adversarial import call_stream, prefix, streamed_body, suffix

api = c4.api

FILE_BYTES = 24_000_000  # just under the 25 000 000-byte photo limit


def workspace_bytes(temp_dir: Path) -> int:
    return sum(f.stat().st_size for f in temp_dir.rglob("*") if f.is_file()) if temp_dir.exists() else 0


def _deleted_temp_files() -> dict[tuple[int, int], int]:
    """(device, inode) -> size of every unnamed (deleted-but-open) file in the
    system temp dir held by this process."""
    tmp = tempfile.gettempdir()
    found: dict[tuple[int, int], int] = {}
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
            if target.startswith(tmp) and target.endswith("(deleted)"):
                st = os.fstat(int(fd))
                found[(st.st_dev, st.st_ino)] = st.st_size
        except (FileNotFoundError, OSError):
            continue
    return found


def open_fds() -> set[tuple[int, int]]:
    """Identities of the unnamed temp files that existed before the probe
    (e.g. pytest's own output-capture files); keyed by inode, not fd number,
    because fd numbers are reused."""
    return set(_deleted_temp_files())


def spool_bytes(ignore: set[tuple[int, int]] = frozenset()) -> int:
    return sum(size for ident, size in _deleted_temp_files().items() if ident not in ignore)


async def test_two_admitted_uploads_peak_temp_disk(api, monkeypatch):
    async def per_request_session():  # like production get_db: one session per request
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = per_request_session
    baseline_fds = open_fds()
    real_copy = photos_endpoint.copy_bounded
    barrier = threading.Barrier(2, timeout=60)
    measured: dict[str, int] = {}
    lock = threading.Lock()

    def copy_then_hold(source, destination, max_bytes):
        n = real_copy(source, destination, max_bytes)
        barrier.wait()  # both requests now hold spool + workspace copy
        with lock:
            if not measured:
                measured["workspace"] = workspace_bytes(api.temp_dir)
                measured["spool"] = spool_bytes(baseline_fds)
        barrier.wait()
        return n

    monkeypatch.setattr(photos_endpoint, "copy_bounded", copy_then_hold)
    bodies = []
    for _ in range(2):
        head, tail = prefix(api, upload_id=str(uuid.uuid4())), suffix()
        bodies.append(streamed_body(head, FILE_BYTES, tail))
    results = await asyncio.gather(*(call_stream(path_for(api.project), token=api.token, chunks=b) for b in bodies))
    total = measured["workspace"] + measured["spool"]
    print(f"\n[temp-disk] 2 admitted uploads of {FILE_BYTES:,} B: workspace copies {measured['workspace']:,} B "
          f"+ multipart spools {measured['spool']:,} B = {total:,} B")
    assert measured["workspace"] == 2 * FILE_BYTES
    assert 2 * FILE_BYTES <= measured["spool"] <= 2 * 27_000_000
    assert total <= 2 * (27_000_000 + 25_000_000)  # the audit bound (104 MB) holds
    assert {r.status for r in results} == {415}  # zero bytes: unidentifiable image, rejected after the copy
    assert await counts(api.db) == (0, 0)
    assert_clean(api)
    assert spool_bytes(baseline_fds) == 0 and workspace_bytes(api.temp_dir) == 0  # everything released


async def test_processing_phase_footprint_is_copy_plus_derivatives(api):
    rnd = random.Random(7)
    image = Image.frombytes("RGB", (2400, 1800), bytes(rnd.getrandbits(8) for _ in range(2400 * 1800 * 3)))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95)
    data = buf.getvalue()
    measured: dict[str, int] = {}
    baseline_fds = open_fds()

    async def at_first_put(key, source):
        measured["workspace"] = workspace_bytes(api.temp_dir)
        measured["spool"] = spool_bytes(baseline_fds)

    api.storage.before_put = at_first_put
    head, tail = prefix(api, upload_id=str(uuid.uuid4())), suffix()
    r = await call_stream(path_for(api.project), token=api.token, chunks=iter([head + data + tail]))
    assert r.status == 201
    print(f"\n[temp-disk] processing phase, {len(data):,} B JPEG: workspace {measured['workspace']:,} B "
          f"(copy + derivatives), spool {measured['spool']:,} B")
    assert measured["spool"] == 0  # the multipart spool was closed before processing
    assert len(data) < measured["workspace"] <= len(data) + 3_000_000
    assert workspace_bytes(api.temp_dir) == 0
