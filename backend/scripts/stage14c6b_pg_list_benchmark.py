#!/usr/bin/env python3
"""Stage 14C.6B — opt-in PostgreSQL large-list benchmark for GET .../photos.

Runs ONLY against TEST_PG_URL validated by tests/pg_scratch_guard.py
(loopback host, database name containing `pe_scratch_test`). Never touches
production. For each size it seeds one owner/project with N attachments
(mixed: ~30 % ROOM context, ~10 % archived attachments, ~5 % archived assets),
then measures the REAL PhotoQueryService.list_photos query for:

  normal first page, archive-view first page, ROOM-filtered first page and a
  deep cursor page (cursor at the middle of the normal view),

recording the median wall time of 5 runs and EXPLAIN (ANALYZE, BUFFERS) of the
exact SQL the service emitted (captured via a cursor-execute event). Seeded
rows are deleted at the end of each size.

Usage (from backend/):
    TEST_PG_URL=postgresql+asyncpg://...@127.0.0.1:55432/pe_scratch_test_14c6b \\
        .venv/bin/python scripts/stage14c6b_pg_list_benchmark.py --sizes 100 1000 10000 50000
"""

import argparse
import asyncio
import os
import random
import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import delete, event, insert, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.domain.services.photo_query_service import (  # noqa: E402
    PhotoListFilters,
    PhotoQueryService,
    encode_cursor,
)
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType  # noqa: E402
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.room import Room  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.pg_scratch_guard import scratch_url  # noqa: E402

BATCH = 5000
RUNS = 5
PLAN_KEYS = ("Sort Method", "Execution Time", "Planning Time", "Index Scan", "Index Only Scan", "Bitmap",
             "Seq Scan", "Rows Removed", "Buffers", "Limit", "Hash Join", "Nested Loop", "Merge Join")


async def seed(sessions, size: int):
    rnd = random.Random(size)
    async with sessions() as s:
        user = User(telegram_user_id=10**11 + size + rnd.randint(0, 10**6))
        s.add(user)
        await s.flush()
        project = Project(owner_id=user.id, name=f"bench {size}", address="x", city="x", postal_code="00-000")
        s.add(project)
        await s.flush()
        room = Room(project_id=project.id, name="Salon")
        s.add(room)
        await s.commit()
        owner, project_id, room_id = user.id, project.id, room.id
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for start in range(0, size, BATCH):
        assets, atts = [], []
        for i in range(start, min(size, start + BATCH)):
            asset_id = uuid.uuid4()
            assets.append(dict(
                id=asset_id, owner_id=owner, project_id=project_id, status=PhotoAssetStatus.READY,
                storage_name="r2-primary", storage_key_original=f"photos/v1/{asset_id}/original.jpg",
                storage_key_display=f"photos/v1/{asset_id}/display.jpg",
                storage_key_thumbnail=f"photos/v1/{asset_id}/thumb.jpg", content_type=PhotoContentType.JPEG,
                byte_size=2_000_000, display_byte_size=500_000, thumbnail_byte_size=20_000, width=4000,
                height=3000, sha256="ab" * 32, uploaded_at=base + timedelta(seconds=i),
                archived_at=base if rnd.random() < 0.05 else None))
            room_ctx = rnd.random() < 0.30
            atts.append(dict(
                id=uuid.uuid4(), asset_id=asset_id, project_id=project_id,
                context=PhotoAttachmentContext.ROOM if room_ctx else PhotoAttachmentContext.PROJECT,
                room_id=room_id if room_ctx else None, category=PhotoCategory.GENERAL,
                position=rnd.choice((0, 0, 0, 1, 2)), archived_at=base if rnd.random() < 0.10 else None))
        async with sessions() as s:
            await s.execute(insert(PhotoAsset), assets)
            await s.execute(insert(PhotoAttachment), atts)
            await s.commit()
    async with sessions() as s:  # fresh planner statistics (one statement per call for asyncpg)
        conn = await s.connection()
        await conn.exec_driver_sql("ANALYZE photo_attachments")
        await conn.exec_driver_sql("ANALYZE photo_assets")
        await s.commit()
    return owner, project_id, room_id


async def cleanup(sessions, owner, project_id):
    async with sessions() as s:
        await s.execute(delete(PhotoAttachment).where(PhotoAttachment.project_id == project_id))
        await s.execute(delete(PhotoAsset).where(PhotoAsset.owner_id == owner))
        await s.execute(delete(Room).where(Room.project_id == project_id))
        await s.execute(delete(Project).where(Project.id == project_id))
        await s.execute(delete(User).where(User.id == owner))
        await s.commit()


async def middle_cursor(sessions, owner, project_id, size: int) -> str:
    async with sessions() as s:
        row = (await s.execute(
            select(PhotoAttachment, PhotoAsset).join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .where(PhotoAttachment.project_id == project_id, PhotoAttachment.archived_at.is_(None),
                   PhotoAsset.archived_at.is_(None))
            .order_by(PhotoAttachment.position, PhotoAsset.uploaded_at, PhotoAttachment.id)
            .offset(max(0, size // 2 - 1)).limit(1))).first()
    return encode_cursor(row[0], row[1], PhotoListFilters().fingerprint(owner, project_id))


async def measure(engine, sessions, label, owner, project_id, filters, cursor=None):
    captured: list[tuple[str, object]] = []

    def capture(conn, cur, statement, parameters, context, executemany):
        if "FROM photo_attachments JOIN photo_assets" in statement:
            captured.append((statement, parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    times = []
    try:
        for _ in range(RUNS):
            async with sessions() as s:
                t = time.perf_counter()
                page = await PhotoQueryService(s).list_photos(owner, project_id, filters, limit=30, cursor=cursor)
                times.append((time.perf_counter() - t) * 1000)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    statement, parameters = captured[-1]
    async with sessions() as s:
        conn = await s.connection()
        plan = (await conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS) " + statement, parameters)).scalars().all()
    print(f"  {label:<22} items={len(page.items):>3}  median {statistics.median(times):7.2f} ms "
          f"(min {min(times):.2f}, max {max(times):.2f})")
    for line in plan:
        if any(key in line for key in PLAN_KEYS):
            print(f"      {line.strip()}")


async def main(sizes: list[int]) -> None:
    url = scratch_url()
    if url is None:
        raise SystemExit("TEST_PG_URL is not set (opt-in benchmark)")
    env = dict(os.environ, DATABASE_URL=url.render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
                   capture_output=True)
    engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for size in sizes:
            print(f"\n=== {size} attachment rows ===")
            t = time.perf_counter()
            owner, project_id, room_id = await seed(sessions, size)
            print(f"  seeded in {time.perf_counter() - t:.1f} s")
            try:
                await measure(engine, sessions, "normal first page", owner, project_id, PhotoListFilters())
                await measure(engine, sessions, "archive first page", owner, project_id,
                              PhotoListFilters(archived=True))
                await measure(engine, sessions, "room first page", owner, project_id,
                              PhotoListFilters(context=PhotoAttachmentContext.ROOM, room_id=room_id))
                await measure(engine, sessions, "deep cursor page", owner, project_id, PhotoListFilters(),
                              cursor=await middle_cursor(sessions, owner, project_id, size))
            finally:
                await cleanup(sessions, owner, project_id)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000, 50000])
    asyncio.run(main(parser.parse_args().sizes))
