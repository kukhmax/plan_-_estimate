"""Stage 14D.2D.4 Part E — backup-role privilege experiment on real PostgreSQL 16.

Opt-in (`TEST_REAL_POSTGRES=1`). Scratch roles only, created with exactly
one grant set each:

    login_only                 LOGIN (PostgreSQL defaults: PUBLIC CONNECT, USAGE on public)
    explicit_tables            + CONNECT, USAGE public, SELECT on all tables
    explicit_tables_sequences  + SELECT on all sequences
    pg_read_all_data           + CONNECT, member of pg_read_all_data

The matrix RECORDS what each role can actually do (it does not assume an
outcome); the report is the experiment result. Hard assertions are limited
to: the harness itself worked, a LOGIN-only role cannot dump application
data, and the two candidate grant sets cannot write, alter, drop, create
tables / databases / roles and carry no dangerous role attributes.
`pg_database_size()` is probed as a diagnostic only.
"""

import secrets
from typing import Any

import asyncpg
import pytest

from app.backup.snapshot_metadata import read_snapshot_metadata
from app.core.pg_snapshot_dump import (
    READY_INVENTORY_SQL,
    PgDumpCommand,
    snapshot_bound_dump,
)
from tests.pg16_proof_fixtures import CANDIDATE_CASES, ROLE_CASES
from tests.pg16_proof_support import (
    gate_enabled,
    new_db_name,
    new_role_name,
    run_tool,
    write_report,
)

pytestmark = pytest.mark.skipif(not gate_enabled(), reason="opt-in: TEST_REAL_POSTGRES=1 (Stage 14D.2D.4)")

DENIED = "42501"


def outcome(exc: BaseException | None) -> str:
    if exc is None:
        return "ok"
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate == DENIED:
        return "denied (42501)"
    return f"error ({sqlstate or type(exc).__name__})"


async def attempt(coro: Any) -> tuple[str, Any]:
    try:
        return "ok", await coro
    except (asyncpg.PostgresError, OSError, TimeoutError) as exc:
        return outcome(exc), None


async def probe_role(server, role, monkeypatch, tmp_path) -> dict[str, str]:
    """Each capability in isolation, then the real 14D.2A + metadata pipeline."""
    db, dsn = role.database, server.dsn(role.database, user=role.name, passfile=role.passfile)
    results: dict[str, str] = {}

    status, conn = await attempt(asyncpg.connect(dsn))
    results["connect"] = status
    if conn is None:
        return results
    second = None
    try:
        await conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        results["repeatable_read_read_only"] = "ok"
        status, snapshot_id = await attempt(conn.fetchval("SELECT pg_export_snapshot()"))
        results["pg_export_snapshot"] = status
        if snapshot_id:
            second = await asyncpg.connect(dsn)
            await second.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            status, _ = await attempt(second.execute(f"SET TRANSACTION SNAPSHOT '{snapshot_id}'"))
            results["import_snapshot_same_role"] = status
            for name, sql in (
                ("read_alembic_version", "SELECT version_num FROM alembic_version"),
                ("photo_asset_status_counts", "SELECT status::text, count(*) FROM photo_assets GROUP BY status"),
                ("ready_inventory", READY_INVENTORY_SQL),
            ):
                await second.execute("SAVEPOINT probe")
                status, _ = await attempt(second.fetch(sql))
                results[name] = status
                await second.execute("ROLLBACK TO SAVEPOINT probe")
            dump = run_tool(
                ["pg_dump", "--format=plain", "--no-password", f"--snapshot={snapshot_id}",
                 f"--file={tmp_path / f'{role.case}-raw.sql'}"],
                server.libpq_env(db, user=role.name, passfile=role.passfile), check=False,
            )
            stderr = dump.stderr.decode("utf-8", "replace")
            results["pg_dump_snapshot"] = "ok" if dump.returncode == 0 else (
                "denied (permission denied)" if "permission denied" in stderr else f"error (rc={dump.returncode})"
            )
            results["pg_dump_needs_sequence_select"] = (
                "yes" if "permission denied for sequence" in stderr else "no evidence"
            )
        await conn.execute("ROLLBACK")
        status, _ = await attempt(conn.fetchval("SELECT pg_database_size(current_database())"))
        results["pg_database_size (diagnostic only)"] = status
        victim_app = f"pe-proof-victim-{secrets.token_hex(3)}"
        victim = await asyncpg.connect(dsn, server_settings={"application_name": victim_app})
        status, terminated = await attempt(conn.fetchval(
            "SELECT bool_or(pg_terminate_backend(pid)) FROM pg_stat_activity WHERE application_name = $1",
            victim_app,
        ))
        if status == "ok" and not terminated:
            status = "not terminated"
        results["terminate_own_tagged_session"] = status
        victim.terminate()
    finally:
        if second is not None:
            await second.close()
        await conn.close()

    # the real pipeline: 14D.2A exporter + metadata hook (snapshot import) + READY + pg_dump
    for key, value in server.libpq_env(db, user=role.name, passfile=role.passfile).items():
        monkeypatch.setenv(key, value)

    async def hook(snapshot_id: str) -> None:
        await read_snapshot_metadata(dsn, snapshot_id, f"pe-proof-{role.case[:8].replace('_', '-')}-meta")

    try:
        await snapshot_bound_dump(
            dsn, PgDumpCommand(prefix=(), username=role.name, dbname=db), tmp_path / f"{role.case}.sql",
            timeout_seconds=600, session_tag=f"pe-proof-{secrets.token_hex(4)}", after_export=hook,
        )
        results["full_pipeline_14d2a_plus_metadata"] = "ok"
    except Exception as exc:  # noqa: BLE001 - experiment records the failure class
        results["full_pipeline_14d2a_plus_metadata"] = f"failed ({type(exc).__name__})"
    return results


async def test_e_role_matrix(seeded, cluster, tmp_path, monkeypatch):
    server = seeded.server
    rls = cluster.sql(seeded.name, (
        "SELECT count(*) FILTER (WHERE c.relrowsecurity), count(*) FILTER (WHERE c.relforcerowsecurity),"
        " (SELECT count(*) FROM pg_policy) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p');"
    ))
    sequences = cluster.sql(seeded.name, "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                                         " WHERE n.nspname = 'public' AND c.relkind = 'S';")
    matrix: dict[str, dict[str, str]] = {}
    roles = {}
    for case in ROLE_CASES:
        roles[case] = cluster.create_role(case.replace("_", "")[:12], seeded.name, case)
        case_dir = tmp_path / case
        case_dir.mkdir()
        matrix[case] = await probe_role(server, roles[case], monkeypatch, case_dir)

    # schema evolution: a table created AFTER the grants, as a future migration would;
    # the SAME candidate roles (grants taken earlier) dump again
    cluster.sql(seeded.name, "CREATE TABLE pe_proof_late_table (id integer PRIMARY KEY);"
                             " INSERT INTO pe_proof_late_table VALUES (1);")
    evolution: dict[str, str] = {}
    for case in CANDIDATE_CASES:
        role = roles[case]
        dump = run_tool(["pg_dump", "--format=plain", "--no-password", f"--file={tmp_path / f'late-{case}.sql'}"],
                        server.libpq_env(seeded.name, user=role.name, passfile=role.passfile), check=False)
        stderr = dump.stderr.decode("utf-8", "replace")
        evolution[case] = "ok" if dump.returncode == 0 else (
            "denied (new table not covered by earlier grants)" if "permission denied" in stderr
            else f"error (rc={dump.returncode})"
        )

    write_report(server, "part_e_role_matrix", {
        "row_level_security": {"tables_with_rls": rls.split("|")[0], "tables_forcing_rls": rls.split("|")[1],
                               "policies": rls.split("|")[2]},
        "public_sequences": sequences,
        "matrix": matrix,
        "schema_evolution_table_created_after_grants": evolution,
    })
    assert set(matrix) == set(ROLE_CASES)
    assert matrix["login_only"].get("pg_dump_snapshot") != "ok"
    assert matrix["login_only"].get("full_pipeline_14d2a_plus_metadata") != "ok"


NEGATIVE_STATEMENTS = (
    ("insert", "INSERT INTO photo_assets DEFAULT VALUES", True),
    ("update", "UPDATE photo_assets SET status = status WHERE false", True),
    ("delete", "DELETE FROM photo_assets WHERE false", True),
    ("truncate", "TRUNCATE photo_assets", True),
    ("create_table", "CREATE TABLE public.pe_proof_negative (x integer)", True),
    ("alter_table", "ALTER TABLE photo_assets ADD COLUMN pe_proof_x integer", True),
    ("drop_table", "DROP TABLE photo_assets", True),
)


@pytest.mark.parametrize("case", CANDIDATE_CASES)
async def test_e_candidate_roles_cannot_write_or_escalate(seeded, cluster, case):
    server = seeded.server
    role = cluster.create_role("neg" + case[:6].replace("_", ""), seeded.name, case)
    conn = await asyncpg.connect(server.dsn(seeded.name, user=role.name, passfile=role.passfile))
    results: dict[str, str] = {}
    try:
        for name, sql, transactional in NEGATIVE_STATEMENTS:
            if transactional:
                await conn.execute("BEGIN")
            try:
                await conn.execute(sql)
                results[name] = "ALLOWED"
            except asyncpg.PostgresError as exc:
                results[name] = outcome(exc)
            finally:
                if transactional:
                    await conn.execute("ROLLBACK")
        db_name, role_name = new_db_name("negdb"), new_role_name("negrole")
        for name, sql in (("create_database", f'CREATE DATABASE "{db_name}"'),
                          ("create_role", f"CREATE ROLE {role_name}")):
            try:
                await conn.execute(sql)
                results[name] = "ALLOWED"
                # would be a finding; make sure cleanup removes it
                (cluster.databases if name == "create_database" else cluster.roles).append(
                    db_name if name == "create_database" else role_name)
            except asyncpg.PostgresError as exc:
                results[name] = outcome(exc)
        attributes = await conn.fetchrow(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles"
            " WHERE rolname = current_user"
        )
    finally:
        await conn.close()
    write_report(server, f"part_e_negative_{case}", {"case": case, "denials": results,
                                                     "role_attributes": dict(attributes)})
    assert all(value == "denied (42501)" for value in results.values()), results
    assert not any(attributes.values())
