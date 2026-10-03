"""Stage 14D.2D.4 Parts A–C — exported / imported snapshot semantics on real PostgreSQL 16.

Opt-in (`TEST_REAL_POSTGRES=1`, see tests/pg16_proof_support.py). Real
transactions only:

A  exporter T1 exports S; importer T2 imports S; writer T3 commits a
   mutation; T2 and the production metadata reader (importing S after T3)
   still see the pre-T3 state, a new ordinary transaction sees post-T3.
B  the 14D.2A primitive dumps with `pg_dump --snapshot` while its exporter
   is open and T3 commits inside the hook; the dump is RESTORED into a fresh
   database and queried: pre-T3 marker, READY set and alembic revision.
C  after the exporter ends, importing S and `pg_dump --snapshot=S` fail
   (SQLSTATE 22023 for the import).
"""

import hashlib

import asyncpg
import pytest

from app.backup.schema_revision import resolve_expected_head
from app.backup.snapshot_metadata import read_snapshot_metadata
from app.core.pg_snapshot_dump import PgDumpCommand, snapshot_bound_dump
from app.models.photo_asset import PhotoAssetStatus
from tests.pg16_proof_support import gate_enabled, restore_file, run_tool, write_report

pytestmark = pytest.mark.skipif(not gate_enabled(), reason="opt-in: TEST_REAL_POSTGRES=1 (Stage 14D.2D.4)")

TAG = "pe-proof-snapshot-01"
MUTATED_REVISION = "zz_proof_mutation"
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
STATE_SQL = "SELECT (SELECT value FROM pe_proof_marker WHERE id = 1), (SELECT version_num FROM alembic_version)"


async def connect(server, database: str) -> asyncpg.Connection:
    return await asyncpg.connect(server.dsn(database))


async def state(conn: asyncpg.Connection) -> tuple[str, str, int, str]:
    marker, revision = await conn.fetchrow(STATE_SQL)
    ready, digest = await conn.fetchrow(SQL_DIGEST)
    return marker, revision, ready, digest


async def mutate(server, database: str, seeded_db) -> None:
    """Writer T3: committed changes to the marker, the READY set and alembic_version."""
    writer = await connect(server, database)
    try:
        async with writer.transaction():
            await writer.execute("UPDATE pe_proof_marker SET value = 'PE_PROOF_VALUE_B' WHERE id = 1")
            await writer.execute("UPDATE alembic_version SET version_num = $1", MUTATED_REVISION)
    finally:
        await writer.close()
    await seeded_db.add(PhotoAssetStatus.READY, 99)


async def test_a_imported_snapshot_is_isolated_from_later_commits(seeded):
    server, db = seeded.server, seeded.name
    head = resolve_expected_head()
    exporter = await connect(server, db)
    importer = await connect(server, db)
    try:
        await exporter.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot_id = await exporter.fetchval("SELECT pg_export_snapshot()")
        await importer.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        await importer.execute(f"SET TRANSACTION SNAPSHOT '{snapshot_id}'")
        before = await state(importer)

        await mutate(server, db, seeded)

        imported_after = await state(importer)
        exporter_after = await state(exporter)
        # production reader, importing S only now (after T3 committed) while T1 is still open
        meta = await read_snapshot_metadata(server.dsn(db), snapshot_id, TAG)
        fresh = await connect(server, db)
        try:
            live = await state(fresh)
        finally:
            await fresh.close()
    finally:
        await importer.close()
        await exporter.close()

    assert before[0] == "PE_PROOF_VALUE_A" and before[1] == head and before[2] == 2
    assert imported_after == before == exporter_after
    assert meta.alembic_revision == head
    assert meta.photo_asset_status_counts == {"FAILED": 1, "PENDING": 1, "READY": 2}
    assert live[0] == "PE_PROOF_VALUE_B" and live[1] == MUTATED_REVISION and live[2] == 3 and live[3] != before[3]
    write_report(server, "part_a_snapshot_import", {
        "snapshot_import": "PASS", "concurrent_mutation_isolation": "PASS",
        "imported_marker": imported_after[0], "live_marker": live[0],
        "imported_ready_count": imported_after[2], "live_ready_count": live[2],
        "metadata_reader_revision": meta.alembic_revision, "live_revision": live[1],
    })


async def test_b_pg_dump_snapshot_content_is_the_exported_state(seeded, cluster, tmp_path, monkeypatch):
    server, db = seeded.server, seeded.name
    head = resolve_expected_head()
    for key, value in server.superuser_env(db).items():
        monkeypatch.setenv(key, value)
    observed: dict = {}

    async def after_export(snapshot_id: str) -> None:
        observed["metadata"] = await read_snapshot_metadata(server.dsn(db), snapshot_id, TAG)
        await mutate(server, db, seeded)  # T3 commits while the exporter is open, before pg_dump starts

    output = tmp_path / "plan-estimate.sql"
    result = await snapshot_bound_dump(
        server.dsn(db), PgDumpCommand(prefix=(), username=server.superuser, dbname=db), output,
        timeout_seconds=600, session_tag="pe-proof-dump-01", after_export=after_export,
    )
    assert result.ready.ready_count == 2
    assert result.dump_sha256 == hashlib.sha256(output.read_bytes()).hexdigest()

    verify = cluster.create_db("verify")
    restore_file(server, verify, output)
    restored = await connect(server, verify)
    try:
        marker, revision, ready, digest = await state(restored)
    finally:
        await restored.close()
    live = await connect(server, db)
    try:
        live_state = await state(live)
    finally:
        await live.close()

    assert marker == "PE_PROOF_VALUE_A" and revision == head
    assert ready == result.ready.ready_count == 2 and digest == result.ready.ready_set_sha256
    assert observed["metadata"].alembic_revision == head
    assert live_state[0] == "PE_PROOF_VALUE_B" and live_state[2] == 3
    write_report(server, "part_b_pg_dump_snapshot", {
        "pg_dump_snapshot_content": "PASS", "method": "restore into fresh database and query",
        "restored_marker": marker, "restored_revision": revision, "restored_ready_count": ready,
        "restored_ready_digest_equals_exporter": digest == result.ready.ready_set_sha256,
        "live_marker_after_commit": live_state[0],
    })


async def test_c_snapshot_dies_with_its_exporter(seeded, tmp_path):
    server, db = seeded.server, seeded.name
    exporter = await connect(server, db)
    await exporter.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    snapshot_id = await exporter.fetchval("SELECT pg_export_snapshot()")
    await exporter.execute("ROLLBACK")
    await exporter.close()

    importer = await connect(server, db)
    try:
        await importer.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        with pytest.raises(asyncpg.PostgresError) as exc:
            await importer.execute(f"SET TRANSACTION SNAPSHOT '{snapshot_id}'")
    finally:
        await importer.close()
    with pytest.raises(asyncpg.PostgresError) as reader_exc:
        await read_snapshot_metadata(server.dsn(db), snapshot_id, TAG)
    dump = run_tool(
        ["pg_dump", "--format=plain", "--no-password", f"--snapshot={snapshot_id}", f"--dbname={db}",
         f"--file={tmp_path / 'stale.sql'}"],
        server.superuser_env(db), check=False,
    )
    assert exc.value.sqlstate == "22023"
    assert reader_exc.value.sqlstate == "22023"
    assert dump.returncode != 0
    write_report(server, "part_c_dead_exporter", {
        "dead_exporter_negative": "PASS", "import_sqlstate": exc.value.sqlstate,
        "metadata_reader_sqlstate": reader_exc.value.sqlstate, "pg_dump_returncode": dump.returncode,
    })
