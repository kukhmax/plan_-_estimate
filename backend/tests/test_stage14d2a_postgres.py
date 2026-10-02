"""Stage 14D.2A — real PostgreSQL proof of the snapshot-bound dump (OPT-IN).

Runs only with BOTH:
- TEST_PG_URL: a loopback `pe_scratch_test` database (tests/pg_scratch_guard.py);
- TEST_PG_TOOL_PREFIX: `docker exec -i <container with 'scratch' in its name>`,
  i.e. pg_dump / psql of the SAME disposable PostgreSQL container (the
  production design also takes pg_dump from the server's own container).

Otherwise the module is skipped. Every test creates its own source database
(name derived from the scratch database, so it carries the scratch marker),
migrates it with `alembic upgrade head`, and drops it (and every restore
database) afterwards. Run with `-rA -s` to see the evidence lines.

Proofs: A happy path dump -> restore -> independent READY digest (Python and
plain SQL); B a concurrent committed insert + PENDING->READY transition
after the export is in neither the inventory nor the dump; C an exported
snapshot cannot be imported after its exporter ends (while an importer that
imported earlier keeps it), and pg_dump with such an id fails; D pg_dump
failure cleanup; E timeout and cancellation while pg_dump is blocked
(exporter alive during the dump, both sessions gone afterwards); F zero READY
assets; G digest independence from query order (SQL ORDER BY COLLATE "C" vs
Python sort).
"""

import asyncio
import hashlib
import os
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.pg_snapshot_dump import (
    PgDumpCommand,
    PgDumpFailedError,
    PgDumpTimeoutError,
    SnapshotDumpError,
    pg_dump_major_version,
    run_dump_process,
    snapshot_bound_dump,
)
from app.domain.photos.keys import PhotoFormat, build_photo_object_keys
from app.domain.services.media_backup_ready_set import ReadyAsset, ready_set_digest
from app.domain.services.photo_asset_service import PhotoAssetService
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType
from app.models.project import Project
from app.models.user import User
from tests.pg_scratch_guard import scratch_tool_prefix, scratch_url

_URL = scratch_url()
_PREFIX = scratch_tool_prefix()
pytestmark = pytest.mark.skipif(
    _URL is None or _PREFIX is None,
    reason="opt-in: set TEST_PG_URL (pe_scratch_test) and TEST_PG_TOOL_PREFIX (docker exec -i <scratch container>)",
)

# Typed placeholders only so the skipped module imports cleanly; never used when skipped.
URL = _URL if _URL is not None else make_url("postgresql+asyncpg://unused@127.0.0.1/pe_scratch_test_unused")
PREFIX = _PREFIX if _PREFIX is not None else ("docker", "exec", "-i", "unused-scratch")

BACKEND = Path(__file__).resolve().parents[1]
EMPTY_DIGEST = hashlib.sha256(b"plan-estimate/ready-set/v1\n").hexdigest()
R, P, F = PhotoAssetStatus.READY, PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED

SQL_DIGEST = """
SELECT count(*) AS n,
       encode(sha256(convert_to(
         'plan-estimate/ready-set/v1' || E'\\n' || coalesce(string_agg(
           id::text || '|' || storage_key_original || '|' || storage_key_display || '|' || storage_key_thumbnail
           || '|' || byte_size::text || '|' || display_byte_size::text || '|' || thumbnail_byte_size::text
           || '|' || sha256 || E'\\n', '' ORDER BY id::text COLLATE "C"), ''),
         'UTF8')), 'hex') AS digest
FROM photo_assets WHERE status = 'READY'
"""


# --- helpers ------------------------------------------------------------------------------


def dsn(db: str) -> str:
    return URL.set(drivername="postgresql", database=db).render_as_string(hide_password=False)


def psql(db: str, *args: str, stdin=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*PREFIX, "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", f"--username={URL.username}", f"--dbname={db}", *args],
        stdin=stdin, capture_output=True, check=True, timeout=300,
    )


ADMIN_DB = str(URL.database)  # the scratch database itself (guarded: contains pe_scratch_test)


def new_db_name(kind: str) -> str:
    return f"{ADMIN_DB}_{kind}_{secrets.token_hex(4)}"


def create_db(name: str) -> None:
    psql(ADMIN_DB, "-c", f'CREATE DATABASE "{name}" TEMPLATE template0')


def drop_db(name: str) -> None:
    psql(ADMIN_DB, "-c", f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def migrate(name: str) -> None:
    env = dict(os.environ, DATABASE_URL=URL.set(database=name).render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
                   capture_output=True, timeout=300)


def command(db: str, **kw) -> PgDumpCommand:
    return PgDumpCommand(prefix=PREFIX, username=kw.pop("username", URL.username), dbname=db, **kw)


def child_pids() -> list[int]:
    found = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open(f"/proc/{entry}/stat") as fh:
                    if int(fh.read().rsplit(")", 1)[1].split()[1]) == os.getpid():
                        found.append(int(entry))
            except OSError:
                continue
    return found


async def sessions_tagged(db: str, tag: str) -> list[tuple[str, str | None, str | None]]:
    conn = await asyncpg.connect(dsn(db))
    try:
        rows = await conn.fetch(
            "SELECT application_name, state, wait_event_type FROM pg_stat_activity WHERE application_name LIKE $1",
            f"{tag}%",
        )
        return [(r["application_name"], r["state"], r["wait_event_type"]) for r in rows]
    finally:
        await conn.close()


async def wait_until_no_sessions(db: str, tag: str, seconds: float = 15.0) -> None:
    for _ in range(int(seconds * 10)):
        if not await sessions_tagged(db, tag):
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"sessions still present: {await sessions_tagged(db, tag)}")


async def python_digest(db: str):
    conn = await asyncpg.connect(dsn(db))
    try:
        rows = await conn.fetch(
            "SELECT id, storage_key_original, storage_key_display, storage_key_thumbnail, byte_size,"
            " display_byte_size, thumbnail_byte_size, sha256 FROM photo_assets WHERE status = 'READY'"
        )
    finally:
        await conn.close()
    return ready_set_digest(
        ReadyAsset(uuid.UUID(str(r["id"])), r["storage_key_original"], r["storage_key_display"],
                   r["storage_key_thumbnail"], r["byte_size"], r["display_byte_size"], r["thumbnail_byte_size"],
                   r["sha256"])
        for r in rows
    )


async def sql_digest(db: str) -> tuple[int, str]:
    conn = await asyncpg.connect(dsn(db))
    try:
        row = await conn.fetchrow(SQL_DIGEST)
        return row["n"], row["digest"]
    finally:
        await conn.close()


async def status_of(db: str, asset_id: uuid.UUID) -> str | None:
    conn = await asyncpg.connect(dsn(db))
    try:
        return await conn.fetchval("SELECT status::text FROM photo_assets WHERE id = $1", asset_id)
    finally:
        await conn.close()


# --- fixtures -------------------------------------------------------------------------------


@pytest.fixture
def dbs():
    created: list[str] = []

    def make(kind: str, *, migrated: bool) -> str:
        name = new_db_name(kind)
        create_db(name)
        created.append(name)
        if migrated:
            migrate(name)
        return name

    yield make
    for name in created:
        drop_db(name)


@pytest.fixture
async def source(dbs):
    name = dbs("src", migrated=True)
    engine = create_async_engine(URL.set(database=name), poolclass=NullPool, hide_parameters=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        user = User(telegram_user_id=int(uuid.uuid4().int % 10**12))
        s.add(user)
        await s.flush()
        project = Project(owner_id=user.id, name="14D.2A scratch", address="ul. Testowa 1", city="Warszawa",
                          postal_code="00-001")
        s.add(project)
        await s.commit()
        owner, project_id = user.id, project.id

    async def add(status: PhotoAssetStatus, n: int) -> uuid.UUID:
        asset_id = uuid.uuid4()
        keys = build_photo_object_keys(asset_id, PhotoFormat.JPEG)
        async with sessions() as s:
            s.add(PhotoAsset(
                id=asset_id, owner_id=owner, project_id=project_id, status=status, storage_name="r2-primary",
                storage_key_original=keys.original, storage_key_display=keys.display,
                storage_key_thumbnail=keys.thumbnail, content_type=PhotoContentType.JPEG,
                byte_size=10_000 + n, display_byte_size=5_000 + n, thumbnail_byte_size=500 + n,
                width=640, height=480, sha256=hashlib.sha256(f"asset-{asset_id}".encode()).hexdigest(),
            ))
            await s.commit()
        return asset_id

    yield SimpleNamespace(name=name, sessions=sessions, owner=owner, project=project_id, add=add, make_db=dbs)
    await engine.dispose()


def restore(dbs, dump: Path) -> str:
    target = dbs("restore", migrated=False)
    with open(dump, "rb") as fh:
        psql(target, stdin=fh)
    return target


# --- proofs ---------------------------------------------------------------------------------


async def test_a_happy_path_dump_and_inventory_are_the_same_snapshot(source, tmp_path):
    for n, status in enumerate([R, P, R, F, R]):
        await source.add(status, n)
    tag = "pe-snapshot-14d2a-a"
    result = await snapshot_bound_dump(dsn(source.name), command(source.name), tmp_path / "a.sql", session_tag=tag)
    assert result.ready.ready_count == 3
    assert result.dump_size > 0 and len(result.dump_sha256) == 64
    tool_major = await pg_dump_major_version(command(source.name))
    assert tool_major == result.server_major_version
    restored = restore(source.make_db, result.dump_path)
    assert await python_digest(restored) == result.ready
    assert await sql_digest(restored) == (3, result.ready.ready_set_sha256)
    assert await sql_digest(source.name) == (3, result.ready.ready_set_sha256)
    await wait_until_no_sessions(source.name, tag)
    assert child_pids() == []
    print(f"\n[14D.2A-A] server/pg_dump major {result.server_major_version}/{tool_major};"
          f" snapshot {result.snapshot_id}; ready_count {result.ready.ready_count};"
          f" ready_set_sha256 {result.ready.ready_set_sha256}; dump {result.dump_size} B sha256 {result.dump_sha256}")


async def test_b_concurrent_commit_after_export_is_in_neither_side(source, tmp_path):
    for n in range(2):
        await source.add(R, n)
    pending = await source.add(P, 9)
    seen: dict[str, object] = {}

    async def mutate(snapshot_id: str) -> None:
        inserted = await source.add(R, 50)  # separate session, committed
        async with source.sessions() as s:  # real CAS transition PENDING -> READY, committed
            await PhotoAssetService(s).compare_and_set_status(pending, source.owner, expected=P, target=R)
        seen["inserted"] = inserted
        seen["live_after_commit"] = await sql_digest(source.name)  # a NEW connection sees the commits

    tag = "pe-snapshot-14d2a-b"
    result = await snapshot_bound_dump(dsn(source.name), command(source.name), tmp_path / "b.sql", session_tag=tag,
                                       after_export=mutate)
    assert seen["live_after_commit"][0] == 4  # the commits are real and visible outside the snapshot
    assert result.ready.ready_count == 2  # ...but not to the exporter
    restored = restore(source.make_db, result.dump_path)
    assert await python_digest(restored) == result.ready
    assert await sql_digest(restored) == (2, result.ready.ready_set_sha256)
    assert await status_of(restored, seen["inserted"]) is None  # inserted row absent from the dump
    assert await status_of(restored, pending) == "PENDING"  # transition absent from the dump
    assert await status_of(source.name, pending) == "READY"  # ...though committed live
    live = await sql_digest(source.name)
    assert live[0] == 4 and live[1] != result.ready.ready_set_sha256
    await wait_until_no_sessions(source.name, tag)
    print(f"\n[14D.2A-B] snapshot ready_count 2 (live 4 after concurrent commit);"
          f" digest {result.ready.ready_set_sha256} == restored; live digest {live[1]} differs")


async def test_c_exported_snapshot_is_unusable_after_its_exporter_ends(source, tmp_path):
    await source.add(R, 1)
    exporter = await asyncpg.connect(dsn(source.name))
    early = await asyncpg.connect(dsn(source.name))
    late = await asyncpg.connect(dsn(source.name))
    try:
        await exporter.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot_id = await exporter.fetchval("SELECT pg_export_snapshot()")
        await early.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        await early.execute(f"SET TRANSACTION SNAPSHOT '{snapshot_id}'")  # imported while the exporter lives
        await source.add(R, 2)  # committed after the export
        await exporter.execute("ROLLBACK")  # exporter ends
        # an importer that imported in time keeps the snapshot:
        assert await early.fetchval("SELECT count(*) FROM photo_assets WHERE status = 'READY'") == 1
        await early.execute("ROLLBACK")
        # a new import after the exporter ended is rejected by PostgreSQL itself:
        await late.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        with pytest.raises(asyncpg.PostgresError) as exc:
            await late.execute(f"SET TRANSACTION SNAPSHOT '{snapshot_id}'")
        assert "invalid snapshot identifier" in str(exc.value)
        await late.execute("ROLLBACK")
    finally:
        for c in (exporter, early, late):
            await c.close()
    # pg_dump with the stale id fails, leaving nothing behind:
    out = tmp_path / "c.sql"
    with pytest.raises(PgDumpFailedError) as dump_exc:
        await run_dump_process(command(source.name).dump_argv(snapshot_id, "pe-snapshot-14d2a-c-dump"), out, 120)
    assert "invalid snapshot identifier" in dump_exc.value.stderr_tail
    assert not out.exists() and not (tmp_path / "c.sql.partial").exists()
    print(f"\n[14D.2A-C] stale snapshot {snapshot_id}: SET TRANSACTION SNAPSHOT -> {exc.value.sqlstate}"
          f" '{str(exc.value).strip()}'; pg_dump rc {dump_exc.value.returncode}")


async def test_d_pg_dump_failure_is_controlled_and_cleans_up(source, tmp_path):
    await source.add(R, 1)
    tag = "pe-snapshot-14d2a-d"
    out = tmp_path / "d.sql"
    with pytest.raises(PgDumpFailedError) as exc:
        await snapshot_bound_dump(dsn(source.name), command(source.name, username="pe_no_such_role_14d2a"), out,
                                  session_tag=tag)
    assert exc.value.returncode not in (0, None)
    assert not out.exists() and not (tmp_path / "d.sql.partial").exists()
    await wait_until_no_sessions(source.name, tag)  # exporter rolled back and closed
    assert child_pids() == []
    print(f"\n[14D.2A-D] pg_dump rc {exc.value.returncode}: {exc.value.stderr_tail.strip()[-160:]}")


async def _blocked_dump(source, tmp_path, tag: str, *, timeout: float):
    """Start a dump that blocks on an ACCESS EXCLUSIVE lock on `projects`
    (pg_dump needs ACCESS SHARE on every table; the exporter reads only
    photo_assets) and wait until pg_dump is lock-waiting while the exporter
    is idle in transaction."""
    blocker = await asyncpg.connect(dsn(source.name))
    await blocker.execute("BEGIN")
    await blocker.execute("LOCK TABLE projects IN ACCESS EXCLUSIVE MODE")
    task = asyncio.create_task(snapshot_bound_dump(
        dsn(source.name), command(source.name), tmp_path / f"{tag}.sql", session_tag=tag, timeout_seconds=timeout))
    observed = None
    for _ in range(200):
        rows = {name: (state, wait) for name, state, wait in await sessions_tagged(source.name, tag)}
        if rows.get(f"{tag}-dump", (None, None))[1] == "Lock" and f"{tag}-exp" in rows:
            observed = rows
            break
        await asyncio.sleep(0.05)
    return blocker, task, observed


async def test_e1_timeout_while_pg_dump_is_blocked_cleans_up(source, tmp_path):
    await source.add(R, 1)
    tag = "pe-snapshot-14d2a-e1"
    blocker, task, observed = await _blocked_dump(source, tmp_path, tag, timeout=6.0)
    try:
        assert observed is not None, "pg_dump never reached the lock wait"
        assert observed[f"{tag}-exp"][0] == "idle in transaction"  # exporter alive during the dump
        with pytest.raises(PgDumpTimeoutError):
            await task
        await wait_until_no_sessions(source.name, tag)  # pg_dump backend terminated, exporter closed
    finally:
        await blocker.execute("ROLLBACK")
        await blocker.close()
    assert child_pids() == []
    assert not (tmp_path / f"{tag}.sql").exists() and not (tmp_path / f"{tag}.sql.partial").exists()
    print(f"\n[14D.2A-E1] observed during dump: {observed}; after timeout: no tagged sessions")


async def test_e2_cancellation_while_pg_dump_is_blocked_cleans_up(source, tmp_path):
    await source.add(R, 1)
    tag = "pe-snapshot-14d2a-e2"
    blocker, task, observed = await _blocked_dump(source, tmp_path, tag, timeout=120.0)
    try:
        assert observed is not None, "pg_dump never reached the lock wait"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await wait_until_no_sessions(source.name, tag)
    finally:
        await blocker.execute("ROLLBACK")
        await blocker.close()
    assert child_pids() == []
    assert not (tmp_path / f"{tag}.sql").exists() and not (tmp_path / f"{tag}.sql.partial").exists()
    print(f"\n[14D.2A-E2] observed during dump: {observed}; after cancel: no tagged sessions")


async def test_f_zero_ready_assets(source, tmp_path):
    await source.add(P, 1)
    await source.add(F, 2)
    tag = "pe-snapshot-14d2a-f"
    result = await snapshot_bound_dump(dsn(source.name), command(source.name), tmp_path / "f.sql", session_tag=tag)
    assert result.ready.ready_count == 0 and result.ready.ready_set_sha256 == EMPTY_DIGEST
    restored = restore(source.make_db, result.dump_path)
    assert await sql_digest(restored) == (0, EMPTY_DIGEST)
    assert await python_digest(restored) == result.ready
    await wait_until_no_sessions(source.name, tag)
    print(f"\n[14D.2A-F] ready_count 0, ready_set_sha256 {EMPTY_DIGEST}, restore verified")


async def test_g_sql_and_python_digests_agree_regardless_of_order(source, tmp_path):
    for n in range(25):
        await source.add(R, n)
    conn = await asyncpg.connect(dsn(source.name))
    try:
        orders = ["ORDER BY id DESC", "ORDER BY byte_size", "ORDER BY random()"]
        digests = set()
        for order in orders:
            rows = await conn.fetch(
                "SELECT id, storage_key_original, storage_key_display, storage_key_thumbnail, byte_size,"
                " display_byte_size, thumbnail_byte_size, sha256 FROM photo_assets WHERE status = 'READY' " + order)
            digests.add(ready_set_digest(
                ReadyAsset(uuid.UUID(str(r["id"])), r["storage_key_original"], r["storage_key_display"],
                           r["storage_key_thumbnail"], r["byte_size"], r["display_byte_size"],
                           r["thumbnail_byte_size"], r["sha256"]) for r in rows))
    finally:
        await conn.close()
    assert len(digests) == 1
    (digest,) = digests
    assert await sql_digest(source.name) == (25, digest.ready_set_sha256)


async def test_version_mismatch_is_refused_before_export(source, tmp_path, monkeypatch):
    from app.core import pg_snapshot_dump as mod

    async def fake_major(cmd, timeout_seconds=30.0):
        return 1

    monkeypatch.setattr(mod, "pg_dump_major_version", fake_major)
    with pytest.raises(SnapshotDumpError):
        await snapshot_bound_dump(dsn(source.name), command(source.name), tmp_path / "v.sql",
                                  session_tag="pe-snapshot-14d2a-v")
    await wait_until_no_sessions(source.name, "pe-snapshot-14d2a-v")
