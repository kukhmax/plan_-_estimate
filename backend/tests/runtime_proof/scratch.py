"""Stage 14D.2D.5 — scratch tooling in a separate tool container (NOT the backup service).

Run with `docker run ... --entrypoint python plan-estimate-backup:local -m tests.runtime_proof.scratch <cmd>`
on the proof network, as the scratch superuser (passfile). Scaffolding only (owner correction C3):
it prepares and independently verifies; the backup itself runs through the real Compose service.

    setup                    create pe_scratch_test_14d2d5, migrate to the repository head, seed
                             2 READY / 1 PENDING / 1 FAILED photo assets and pe_proof_block, create the
                             backup role with the frozen 14D.2D.4 policy (password read from the backup
                             pgpass; never printed)
    verify-run --run-id ID   artifact SHA / size = evidence; decrypt (disposable identity) -> gunzip ->
                             plaintext SHA = evidence -> restore into a fresh scratch DB -> READY digest
                             and revision = source + evidence
    block --seconds N        hold ACCESS EXCLUSIVE on pe_proof_block (makes pg_dump wait; SIGTERM test)
    sessions                 count backup-tagged server sessions (expect 0 after cleanup)

Configuration: TEST_PG16_HOST (must contain "proof"), TEST_PG16_PORT, TEST_PG16_SUPERUSER,
TEST_PG16_SUPERUSER_PASSFILE, TEST_PG16_SSLMODE (same validation as 14D.2D.4) plus
PE_PROOF_BACKUP_PASSFILE, PE_PROOF_DATA (read-only data root), PE_PROOF_IDENTITY.
"""

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

import asyncpg

from tests.pg16_proof_support import ProofConfigError, ProofServer

DATABASE = "pe_scratch_test_14d2d5"
BACKUP_ROLE = "pe_scratch_role_backup14d2d5"
BLOCK_TABLE = "pe_proof_block"
BACKEND = Path(__file__).resolve().parents[2]
_HEX48 = re.compile(r"^[0-9a-f]{48}$")
_SCRATCH_DB = re.compile(r"^pe_scratch_test_14d2d5(_[a-z0-9_]{1,40})?$")
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


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


def scratch_db(name: str) -> str:
    if name != "postgres" and not _SCRATCH_DB.match(name):
        raise ProofConfigError("refusing a non-14D.2D.5 scratch database")
    return name


def dsn(server: ProofServer, database: str) -> str:
    scratch_db(database)
    return (f"postgresql://{quote(server.superuser, safe='')}@{server.host}:{server.port}/{database}"
            f"?sslmode={server.sslmode}&passfile={quote(str(server.superuser_passfile), safe='')}")


def libpq_env(server: ProofServer, database: str) -> dict[str, str]:
    scratch_db(database)
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "PGHOST": server.host,
            "PGPORT": str(server.port), "PGDATABASE": database, "PGUSER": server.superuser,
            "PGPASSFILE": str(server.superuser_passfile), "PGSSLMODE": server.sslmode}


def backup_password(passfile: Path, server: ProofServer) -> str:
    """The backup role's password from its 14D.2C-format pgpass (exactly one matching entry, 48 hex)."""
    lines = [line for line in passfile.read_text().splitlines() if line and not line.startswith("#")]
    if len(lines) != 1:
        raise ProofConfigError("backup pgpass must hold exactly one entry")
    fields = lines[0].split(":")
    if fields[:4] != [server.host, str(server.port), DATABASE, BACKUP_ROLE] or len(fields) != 5:
        raise ProofConfigError("backup pgpass entry does not match the proof host / database / role")
    if not _HEX48.match(fields[4]):
        raise ProofConfigError("backup pgpass password must be 48 lowercase hex characters")
    return fields[4]


async def setup(server: ProofServer, backup_passfile: Path) -> dict[str, Any]:
    password = backup_password(backup_passfile, server)
    admin = await asyncpg.connect(dsn(server, "postgres"))
    try:
        if await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", DATABASE):
            raise ProofConfigError(f"{DATABASE} already exists; this proof expects a fresh scratch server")
        await admin.execute(f'CREATE DATABASE "{DATABASE}" TEMPLATE template0')
    finally:
        await admin.close()
    env = dict(os.environ, **libpq_env(server, DATABASE),
               DATABASE_URL=f"postgresql+asyncpg://{server.superuser}@{server.host}:{server.port}/{DATABASE}")
    await asyncio.to_thread(subprocess.run, [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND,
                            env=env, check=True, capture_output=True, timeout=600)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.models  # noqa: F401
    from app.domain.photos.keys import PhotoFormat, build_photo_object_keys
    from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType
    from app.models.project import Project
    from app.models.user import User

    connect_args: dict[str, Any] = {"passfile": str(server.superuser_passfile)}
    if server.sslmode == "disable":
        connect_args["ssl"] = False
    engine = create_async_engine(f"postgresql+asyncpg://{server.superuser}@{server.host}:{server.port}/{DATABASE}",
                                 poolclass=NullPool, hide_parameters=True, connect_args=connect_args)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as s:
            user = User(telegram_user_id=int(uuid.uuid4().int % 10**12))
            s.add(user)
            await s.flush()
            project = Project(owner_id=user.id, name="14D.2D.5 proof", address="ul. Testowa 1", city="Warszawa",
                              postal_code="00-001")
            s.add(project)
            await s.flush()
            for n, status in enumerate((PhotoAssetStatus.READY, PhotoAssetStatus.READY, PhotoAssetStatus.PENDING,
                                        PhotoAssetStatus.FAILED), start=1):
                asset_id = uuid.uuid4()
                keys = build_photo_object_keys(asset_id, PhotoFormat.JPEG)
                s.add(PhotoAsset(
                    id=asset_id, owner_id=user.id, project_id=project.id, status=status, storage_name="r2-primary",
                    storage_key_original=keys.original, storage_key_display=keys.display,
                    storage_key_thumbnail=keys.thumbnail, content_type=PhotoContentType.JPEG,
                    byte_size=10_000 + n, display_byte_size=5_000 + n, thumbnail_byte_size=500 + n,
                    width=640, height=480, sha256=hashlib.sha256(f"asset-{asset_id}".encode()).hexdigest(),
                ))
            await s.commit()
    finally:
        await engine.dispose()

    conn = await asyncpg.connect(dsn(server, DATABASE))
    try:
        await conn.execute(f"CREATE TABLE {BLOCK_TABLE} (id integer PRIMARY KEY); INSERT INTO {BLOCK_TABLE} VALUES (1)")
        # frozen 14D.2D.4 policy; the password is random hex (validated) -> safe literal, never logged
        await conn.execute(
            f"CREATE ROLE {BACKUP_ROLE} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE"
            " NOREPLICATION NOBYPASSRLS INHERIT"
        )
        await conn.execute(f'GRANT CONNECT ON DATABASE "{DATABASE}" TO {BACKUP_ROLE}')
        await conn.execute(f"GRANT pg_read_all_data TO {BACKUP_ROLE}")
        attributes = dict(await conn.fetchrow(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname = $1",
            BACKUP_ROLE,
        ))
        ready, digest = await conn.fetchrow(SQL_DIGEST)
        revision = await conn.fetchval("SELECT version_num FROM alembic_version")
        version = await conn.fetchval("SHOW server_version")
    finally:
        await conn.close()
    return {"database": DATABASE, "backup_role": BACKUP_ROLE, "role_attributes": attributes, "server_version": version,
            "revision": revision, "ready_count": ready, "ready_set_sha256": digest,
            "pass": not any(attributes.values()) and ready == 2}


async def verify_run(server: ProofServer, data_root: Path, identity: Path, run_id: str) -> dict[str, Any]:
    from app.backup.run_id import validate_run_id
    from app.backup.run_sidecars import SIDECAR_NAMES
    from app.backup.schema_revision import resolve_expected_head

    run_dir = data_root / "encrypted" / validate_run_id(run_id)
    names = sorted(p.name for p in run_dir.iterdir())
    evidence = json.loads((run_dir / "local-run.json").read_bytes())
    artifact = (run_dir / "plan-estimate.sql.gz.age").read_bytes()
    decrypted = await asyncio.to_thread(subprocess.run, ["age", "--decrypt", "-i", str(identity)], input=artifact,
                                        capture_output=True, check=True, timeout=600)
    plaintext = gzip.decompress(decrypted.stdout)
    head = resolve_expected_head()

    source = await asyncpg.connect(dsn(server, DATABASE))
    try:
        source_ready, source_digest = await source.fetchrow(SQL_DIGEST)
    finally:
        await source.close()
    verify_db = scratch_db(f"{DATABASE}_verify_{secrets.token_hex(4)}")
    admin = await asyncpg.connect(dsn(server, "postgres"))
    try:
        await admin.execute(f'CREATE DATABASE "{verify_db}" TEMPLATE template0')
    finally:
        await admin.close()
    try:
        await asyncio.to_thread(subprocess.run, ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], input=plaintext,
                                env=libpq_env(server, verify_db), check=True, capture_output=True, timeout=600)
        restored = await asyncpg.connect(dsn(server, verify_db))
        try:
            restored_ready, restored_digest = await restored.fetchrow(SQL_DIGEST)
            restored_revision = await restored.fetchval("SELECT version_num FROM alembic_version")
        finally:
            await restored.close()
    finally:
        admin = await asyncpg.connect(dsn(server, "postgres"))
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{verify_db}" WITH (FORCE)')
        finally:
            await admin.close()

    checks = {
        "files": names == sorted({"local-run.json", "plan-estimate.sql.gz.age"} | SIDECAR_NAMES),
        "status_complete": evidence.get("status") == "complete" and evidence.get("run_id") == run_id,
        "artifact_sha256": hashlib.sha256(artifact).hexdigest() == evidence["artifact"]["sha256"],
        "artifact_size": len(artifact) == evidence["artifact"]["size"],
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest() == evidence["dump"]["plaintext_sha256"],
        "revision_is_head": evidence["database"]["alembic_revision"] == evidence["database"]["expected_alembic_head"]
        == head == restored_revision,
        "ready_matches_source": evidence["snapshot"]["ready_count"] == source_ready == restored_ready,
        "digest_matches_source": evidence["snapshot"]["ready_set_sha256"] == source_digest == restored_digest,
    }
    return {"run_id": run_id, "checks": checks, "revision": head, "ready_count": source_ready,
            "age_version": evidence["artifact"]["age_version"], "pg_dump_version": evidence["dump"]["pg_dump_version"],
            "pass": all(checks.values())}


async def block(server: ProofServer, seconds: float) -> dict[str, Any]:
    conn = await asyncpg.connect(dsn(server, DATABASE))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await conn.execute("BEGIN")
        await conn.execute(f"LOCK TABLE {BLOCK_TABLE} IN ACCESS EXCLUSIVE MODE")
        emit({"state": "BLOCKING", "table": BLOCK_TABLE})
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            pass
        await conn.execute("ROLLBACK")
    finally:
        await conn.close()
    return {"state": "RELEASED", "pass": True}


async def sessions(server: ProofServer) -> dict[str, Any]:
    conn = await asyncpg.connect(dsn(server, "postgres"))
    try:
        rows = await conn.fetch(
            "SELECT application_name, state FROM pg_stat_activity"
            " WHERE application_name LIKE 'pe-snapshot-%' AND pid <> pg_backend_pid()"
        )
    finally:
        await conn.close()
    return {"tagged_sessions": [dict(r) for r in rows], "pass": not rows}


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.runtime_proof.scratch")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup")
    verify = commands.add_parser("verify-run")
    verify.add_argument("--run-id", required=True)
    blocker = commands.add_parser("block")
    blocker.add_argument("--seconds", type=float, default=300.0)
    commands.add_parser("sessions")
    args = parser.parse_args(argv)
    environment = os.environ if env is None else env
    server = ProofServer.from_env(environment)
    if args.command == "setup":
        result = asyncio.run(setup(server, Path(environment["PE_PROOF_BACKUP_PASSFILE"])))
    elif args.command == "verify-run":
        result = asyncio.run(verify_run(server, Path(environment["PE_PROOF_DATA"]),
                                        Path(environment["PE_PROOF_IDENTITY"]), args.run_id))
    elif args.command == "block":
        result = asyncio.run(block(server, args.seconds))
    else:
        result = asyncio.run(sessions(server))
    emit({"check": args.command, **result})
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
