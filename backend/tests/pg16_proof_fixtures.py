"""Stage 14D.2D.4 — pytest fixtures for the opt-in PostgreSQL 16 proof.

Imported by the `test_stage14d2d4_pg16_*` modules. Session fixtures are
synchronous (psql / alembic subprocesses) so they work with the per-test
asyncio loops; seeding uses the application ORM models.
"""

import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.domain.photos.keys import PhotoFormat, build_photo_object_keys
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType
from app.models.project import Project
from app.models.user import User
from tests.pg16_proof_support import (
    REQUIRED_MAJOR,
    ProofConfigError,
    ProofServer,
    check_scratch_db,
    check_scratch_role,
    gate_enabled,
    major_of_tool_line,
    new_db_name,
    new_password,
    new_role_name,
    psql,
    tool_versions,
    write_passfile,
    write_report,
)

BACKEND = Path(__file__).resolve().parents[1]
MARKER_TABLE_SQL = (
    "CREATE TABLE pe_proof_marker (id integer PRIMARY KEY, value text NOT NULL);"
    " INSERT INTO pe_proof_marker VALUES (1, 'PE_PROOF_VALUE_A');"
)
ROLE_CASES = ("login_only", "explicit_tables", "explicit_tables_sequences", "pg_read_all_data")
CANDIDATE_CASES = ("explicit_tables_sequences", "pg_read_all_data")


class Cluster:
    """Tracks scratch databases / roles and drops them (databases first)."""

    def __init__(self, server: ProofServer, tmp_dir: Path) -> None:
        self.server = server
        self.tmp_dir = tmp_dir
        self.databases: list[str] = []
        self.roles: list[str] = []

    def sql(self, database: str, statement: str) -> str:
        """Run SQL via stdin (never argv, so role passwords never appear in a process list)."""
        target_env = self.server.superuser_env(database)
        completed = subprocess.run(
            ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At"],
            input=statement.encode(),
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", **target_env},
            capture_output=True, timeout=300, check=True,
        )
        return completed.stdout.decode().strip()

    def create_db(self, kind: str, *, template: str | None = None) -> str:
        name = new_db_name(kind)
        clause = f' TEMPLATE "{check_scratch_db(template)}"' if template else " TEMPLATE template0"
        self.sql("postgres", f'CREATE DATABASE "{name}"{clause};')
        self.databases.append(name)
        return name

    def migrate(self, database: str) -> None:
        env = dict(os.environ)
        env.update(self.server.superuser_env(database))
        env["DATABASE_URL"] = self.server.sqlalchemy_url(database)
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
                       capture_output=True, timeout=600)

    def create_role(self, kind: str, database: str, case: str) -> SimpleNamespace:
        """A scratch login role with exactly the grants of `case`; returns name + passfile."""
        name, password = new_role_name(kind), new_password()
        check_scratch_db(database)
        statements = [
            (
                f"CREATE ROLE {name} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE"
                " NOREPLICATION NOBYPASSRLS INHERIT;"
            )
        ]
        if case in ("explicit_tables", "explicit_tables_sequences"):
            statements += [
                f'GRANT CONNECT ON DATABASE "{database}" TO {name};',
                f"GRANT USAGE ON SCHEMA public TO {name};",
                f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {name};",
            ]
            if case == "explicit_tables_sequences":
                statements.append(f"GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {name};")
        elif case == "pg_read_all_data":
            statements += [f'GRANT CONNECT ON DATABASE "{database}" TO {name};', f"GRANT pg_read_all_data TO {name};"]
        elif case != "login_only":
            raise ProofConfigError("unknown role case")
        self.sql(database, "\n".join(statements))
        self.roles.append(name)
        passfile = write_passfile(self.tmp_dir / f"{name}.pgpass", self.server, database=database, user=name,
                                  password=password)
        return SimpleNamespace(name=name, case=case, database=database, passfile=passfile)

    def cleanup(self) -> None:
        for database in reversed(self.databases):
            self.sql("postgres", f'DROP DATABASE IF EXISTS "{check_scratch_db(database)}" WITH (FORCE);')
        for role in reversed(self.roles):
            self.sql("postgres", f"DROP ROLE IF EXISTS {check_scratch_role(role)};")


@pytest.fixture(scope="session")
def proof_server() -> ProofServer:
    if not gate_enabled():
        pytest.skip("opt-in: set TEST_REAL_POSTGRES=1 (owner-run PostgreSQL 16 proof, Stage 14D.2D.4)")
    try:
        server = ProofServer.from_env(os.environ)
    except ProofConfigError as exc:
        pytest.fail(f"proof configuration invalid: {exc}")
    versions = tool_versions()
    completed = psql(server, "postgres", "-c", "SHOW server_version_num")
    server_num = int(completed.stdout.decode().strip())
    server_version = psql(server, "postgres", "-c", "SHOW server_version").stdout.decode().strip()
    pg_dump_major = major_of_tool_line(versions["pg_dump"])
    write_report(server, "versions", {
        "server_version": server_version, "server_major": server_num // 10000, **versions,
        "pg_dump_major": pg_dump_major,
    })
    if server_num // 10000 != REQUIRED_MAJOR or pg_dump_major != REQUIRED_MAJOR:
        pytest.fail(f"proof requires PostgreSQL {REQUIRED_MAJOR} server and pg_dump "
                    f"(server major {server_num // 10000}, pg_dump major {pg_dump_major})")
    return server


@pytest.fixture(scope="session")
def cluster(proof_server: ProofServer, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Cluster]:
    tmp_dir = tmp_path_factory.mktemp("pg16-proof-secrets")
    os.chmod(tmp_dir, 0o700)
    state = Cluster(proof_server, tmp_dir)
    try:
        yield state
    finally:
        state.cleanup()


@pytest.fixture(scope="session")
def template_db(cluster: Cluster) -> str:
    """Migrated to the repository head once; per-test databases are cloned from it."""
    name = cluster.create_db("template")
    cluster.migrate(name)
    return name


@pytest.fixture
async def seeded(cluster: Cluster, template_db: str) -> Any:
    """A fresh migrated database with a marker table and photo assets (2 READY, 1 PENDING, 1 FAILED)."""
    name = cluster.create_db("db", template=template_db)
    cluster.sql(name, MARKER_TABLE_SQL)
    server = cluster.server
    connect_args: dict[str, Any] = {"passfile": str(server.superuser_passfile)}
    if server.sslmode == "disable":
        connect_args["ssl"] = False
    engine = create_async_engine(server.sqlalchemy_url(name), poolclass=NullPool, hide_parameters=True,
                                 connect_args=connect_args)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        user = User(telegram_user_id=int(uuid.uuid4().int % 10**12))
        s.add(user)
        await s.flush()
        project = Project(owner_id=user.id, name="14D.2D.4 proof", address="ul. Testowa 1", city="Warszawa",
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

    await add(PhotoAssetStatus.READY, 1)
    await add(PhotoAssetStatus.READY, 2)
    await add(PhotoAssetStatus.PENDING, 3)
    await add(PhotoAssetStatus.FAILED, 4)
    try:
        yield SimpleNamespace(name=name, add=add, server=server)
    finally:
        await engine.dispose()
