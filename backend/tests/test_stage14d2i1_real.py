"""Stage 14D.2I.1 — opt-in real proof: the restore chain with real age and real PostgreSQL 16.

Gate and environment: the 14D.2D.4 harness (`TEST_REAL_POSTGRES=1`, `TEST_PG16_*`, see tests/pg16_proof_support.py)
plus `age` and `age-keygen` on PATH (missing tools FAIL). Identities are generated per run into a private directory.

What it proves, with the production code on every step:

  real schema (Alembic head) + seeded assets -> `pg_dump --format=plain` -> `encrypt_dump_artifact` (14D.2B:
  gzip + age, two recipients) -> sealed manifest -> `restore_database` (14D.2I.1: real age, real psql) into a fresh
  scratch database -> the restored database is identical to the source, Alembic = manifest, READY set = manifest,
  PENDING / FAILED counts = manifest.

and, for every way the chain can break (wrong key, tampered / truncated ciphertext, a gzip member with a bad
CRC, a role the scratch server lacks, a target that is not empty): the report names the failure and the
target database is still EMPTY afterwards -- psql's single transaction was never committed.
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
import uuid
import zlib
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from app.backup import manifest as mf
from app.backup import restore_db as rd
from app.backup import target as tg
from app.backup.pg_connection import PgConnectionConfig
from app.backup.run_id import new_run_id
from app.backup.schema_revision import resolve_expected_head
from app.core.db_dump_encryption import ENCRYPTED_DUMP_NAME, encrypt_dump_artifact
from app.core.pg_snapshot_dump import READY_INVENTORY_SQL, SnapshotDumpResult
from app.domain.services.media_backup_ready_set import ReadyAsset, ready_set_digest
from tests.pg16_proof_fixtures import (  # noqa: F401
    Cluster,
    cluster,
    proof_server,
    seeded,
    template_db,
)
from tests.pg16_proof_support import gate_enabled, run_tool

pytestmark = pytest.mark.skipif(not gate_enabled(), reason="opt-in: TEST_REAL_POSTGRES=1 (Stage 14D.2I.1)")

T_START = "2026-10-04T12:00:00Z"
T_VERIFIED = "2026-10-04T12:05:00Z"
T_DONE = "2026-10-04T12:10:00Z"
SCRATCH_PREFIX = "pe_restore_scratch_"


def tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.fail(f"{name} is not on PATH (the real restore proof needs age and age-keygen)")
    return path


def make_identity(directory: Path, name: str) -> SimpleNamespace:
    path = directory / name
    subprocess.run([tool("age-keygen"), "-o", str(path)], check=True, capture_output=True)
    path.chmod(0o600)
    public = subprocess.run([tool("age-keygen"), "-y", str(path)], check=True, capture_output=True, text=True).stdout.strip()
    return SimpleNamespace(path=path, public=public)


@pytest.fixture
def keys(tmp_path: Path) -> SimpleNamespace:
    directory = tmp_path / "keys"
    directory.mkdir(mode=0o700)
    return SimpleNamespace(a=make_identity(directory, "a.txt"), b=make_identity(directory, "b.txt"), c=make_identity(directory, "c.txt"))


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    path = tmp_path / "scratch"
    path.mkdir(mode=0o700)
    return path


class Restore:
    """Helpers around one seeded source database and fresh scratch targets."""

    def __init__(self, pg_cluster: Cluster, source: str, tmp_path: Path, scratch_dir: Path) -> None:
        self.cluster = pg_cluster
        self.source = source
        self.tmp = tmp_path
        self.scratch_dir = scratch_dir
        self.targets: list[str] = []
        self.password = pg_cluster.server.superuser_passfile.read_text().strip().split(":")[-1]

    # -- database plumbing -------------------------------------------------------------------------

    def env_for(self, database: str) -> dict[str, str]:
        """libpq environment for ANY database name (the harness helpers only know its own prefix)."""
        server = self.cluster.server
        return {
            "PGHOST": server.host, "PGPORT": str(server.port), "PGDATABASE": database, "PGUSER": server.superuser,
            "PGPASSFILE": str(server.superuser_passfile), "PGSSLMODE": server.sslmode,
        }  # fmt: skip

    def sql(self, database: str, statement: str) -> str:
        completed = subprocess.run(
            ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At"], input=statement.encode(),
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", **self.env_for(database)},
            capture_output=True, timeout=120, check=True,
        )  # fmt: skip
        return completed.stdout.decode().strip()

    def new_target(self, name: str | None = None) -> PgConnectionConfig:
        database = name or f"{SCRATCH_PREFIX}{uuid.uuid4().hex[:8]}"
        self.cluster.sql("postgres", f'CREATE DATABASE "{database}" TEMPLATE template0;')
        self.targets.append(database)
        server = self.cluster.server
        passfile = self.tmp / f"{database}.pgpass"
        fd = os.open(passfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(f"{server.host}:{server.port}:{database}:{server.superuser}:{self.password}\n")
        return PgConnectionConfig(server.host, server.port, database, server.superuser, passfile, server.sslmode)

    def drop_targets(self) -> None:
        for database in self.targets:
            self.cluster.sql("postgres", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);')

    def relations(self, config: PgConnectionConfig) -> int:
        env = {**config.libpq_env()}
        out = run_tool(
            ["psql", "-X", "-At", "-c", rd.USER_RELATIONS_SQL], env, timeout=60
        ).stdout.decode().strip()
        return int(out)

    def table_digest(self, database: str) -> str:
        return self.sql(database, "SELECT md5(string_agg(t::text, E'\\n' ORDER BY id)) FROM photo_assets t;")

    # -- media consistent with the database -----------------------------------------------------------

    async def make_media(self) -> dict[str, bytes]:
        """Give every READY asset of the source database real bytes: the rows' sizes and the original's SHA-256
        are updated to describe them, so that the backup, the manifest and the database agree on content."""
        media: dict[str, bytes] = {}
        statements = []
        for asset in await self.ready_assets(self.source):
            original = os.urandom(3000) + str(asset.asset_id).encode()
            display, thumbnail = os.urandom(2000), os.urandom(1000)
            media[asset.key_original], media[asset.key_display], media[asset.key_thumbnail] = original, display, thumbnail
            statements.append(
                f"UPDATE photo_assets SET byte_size = {len(original)}, display_byte_size = {len(display)},"
                f" thumbnail_byte_size = {len(thumbnail)}, sha256 = '{hashlib.sha256(original).hexdigest()}'"
                f" WHERE id = '{asset.asset_id}';"
            )
        self.sql(self.source, "\n".join(statements))
        return media

    # -- backup side ---------------------------------------------------------------------------------

    def pg_dump(self, database: str) -> bytes:
        user = self.cluster.server.superuser
        argv = ["pg_dump", "--format=plain", "--no-password", f"--username={user}", f"--dbname={database}"]
        return run_tool(argv, self.env_for(database), timeout=300).stdout

    async def ready_assets(self, database: str) -> list[ReadyAsset]:
        conn = await asyncpg.connect(self.cluster.server.dsn(database))
        try:
            rows = await conn.fetch(READY_INVENTORY_SQL)
        finally:
            await conn.close()
        return [rd._ready_asset(row) for row in rows]

    async def seal(self, plain_sql: bytes, recipients: tuple[str, ...], *, mutate: Any = None, recipients_in_manifest: tuple[str, ...] | None = None, pending: int = 1, failed: int = 1, media: dict[str, bytes] | None = None) -> tuple[mf.VerifiedRun, tg.InMemoryBackupTarget]:
        """Encrypt `plain_sql` with the production primitive and seal a manifest around the artifact.
        `mutate(ciphertext) -> ciphertext` damages the artifact BEFORE the manifest records it, so the manifest still
        matches the (damaged) bytes and the restore must be stopped by age / gzip, not by the SHA-256 gate."""
        work = self.tmp / f"run-{uuid.uuid4().hex[:6]}"
        work.mkdir(mode=0o700)
        path = work / "plan-estimate.sql"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(plain_sql)
        dump = SnapshotDumpResult("00000003-0000001B-1", ready_set_digest([]), 16, path, len(plain_sql), hashlib.sha256(plain_sql).hexdigest())
        encrypted = await encrypt_dump_artifact(dump, ",".join(recipients), age_binary=tool("age"), timeout_seconds=300)
        artifact = encrypted.artifact_path.read_bytes()
        return await self.seal_artifact(artifact, recipients_in_manifest or recipients, pending=pending, failed=failed, mutate=mutate, media=media)

    async def seal_artifact(self, artifact: bytes, recipients: tuple[str, ...], *, mutate: Any = None, pending: int = 1, failed: int = 1, media: dict[str, bytes] | None = None) -> tuple[mf.VerifiedRun, tg.InMemoryBackupTarget]:
        if mutate is not None:
            artifact = mutate(artifact)
        assets = await self.ready_assets(self.source)
        run_id = new_run_id()
        objects = []
        for asset in assets:
            for role, key, size, sha in (
                (mf.Role.ORIGINAL, asset.key_original, asset.byte_size, asset.sha256),
                (mf.Role.DISPLAY, asset.key_display, asset.display_byte_size, hashlib.sha256(asset.key_display.encode()).hexdigest()),
                (mf.Role.THUMBNAIL, asset.key_thumbnail, asset.thumbnail_byte_size, hashlib.sha256(asset.key_thumbnail.encode()).hexdigest()),
            ):  # fmt: skip
                if media is not None:  # real bytes: the manifest records what the backup target really holds
                    size, sha = len(media[key]), hashlib.sha256(media[key]).hexdigest()
                objects.append(mf.ManifestObject(
                    asset_id=str(asset.asset_id), role=role, key=key, size=size, sha256=sha,
                    content_type=mf.expected_content_type(role, str(asset.asset_id), key), action=mf.Action.COPIED,
                    sha_provenance=mf.DOWNLOADED, verified_at=T_VERIFIED,
                ))  # fmt: skip
        digest = ready_set_digest(assets)
        header = mf.ManifestHeader(
            run_id=run_id, started_at=T_START, tool_commit="0" * 40,
            source=mf.SourceInfo("proof-source", "plan-estimate-media-drill-source"),
            target=mf.TargetInfo("plan-estimate-backup-drill"),
            db_dump=mf.DbDumpInfo(
                key=mf.db_dump_key(run_id), recipients=recipients, encrypted_sha256=hashlib.sha256(artifact).hexdigest(),
                encrypted_size=len(artifact), alembic_head=resolve_expected_head(), dumped_at=T_START,
            ),
            snapshot=mf.SnapshotInfo(digest.ready_count, digest.ready_set_sha256),
        )  # fmt: skip
        manifest = mf.build_manifest(header, objects, skipped_pending=pending, skipped_failed=failed, source_keys=3 * len(assets), orphan_candidates=0)
        from datetime import UTC, datetime

        complete = mf.build_complete(manifest, datetime(2026, 10, 4, 12, 10, tzinfo=UTC))
        run = mf.verify_run(complete.to_bytes(), manifest.to_bytes())
        target = tg.InMemoryBackupTarget()
        target.objects[header.db_dump.key] = artifact
        target.objects[mf.manifest_key(run_id)] = manifest.to_bytes()
        target.objects[mf.complete_key(run_id)] = complete.to_bytes()
        if media is not None:
            target.objects.update(media)
        return run, target

    async def restore(self, run: mf.VerifiedRun, target: tg.InMemoryBackupTarget, config: PgConnectionConfig, identity: Path, **kwargs: Any) -> rd.DbRestoreReport:
        return await rd.restore_database(
            target, run, database=config, identity_file=identity, scratch_dir=self.scratch_dir,
            allowed_hosts=[self.cluster.server.host], timeout_seconds=300.0, **kwargs,
        )  # fmt: skip


@pytest.fixture
def proof(cluster: Cluster, seeded: Any, tmp_path: Path, scratch: Path) -> Iterator[Restore]:  # noqa: F811 - fixture parameter
    state = Restore(cluster, seeded.name, tmp_path, scratch)
    try:
        yield state
    finally:
        state.drop_targets()


def flip(data: bytes, index: int) -> bytes:
    return data[:index] + bytes([data[index] ^ 0xFF]) + data[index + 1 :]


# --- the whole chain ---------------------------------------------------------------------------------------------


async def test_the_real_chain_restores_an_identical_database(proof: Restore, keys: SimpleNamespace):
    plain = proof.pg_dump(proof.source)
    assert plain.rstrip().endswith(b"-- PostgreSQL database dump complete") or b"-- PostgreSQL database dump complete" in plain[-4096:]
    run, target = await proof.seal(plain, (keys.a.public, keys.b.public))
    config = proof.new_target()
    assert proof.relations(config) == 0

    report = await proof.restore(run, target, config, keys.a.path)

    assert report.ok, report.report_bytes()
    assert report.alembic_revision == resolve_expected_head() and report.matches_repository_head is True
    assert report.ready_count == 2 and report.status_counts == {"FAILED": 1, "PENDING": 1, "READY": 2}
    assert report.plaintext_sha256 == hashlib.sha256(plain).hexdigest() and report.plaintext_bytes == len(plain)
    assert proof.relations(config) > 10, "the schema was restored"
    assert proof.table_digest(config.database) == proof.table_digest(proof.source), "photo_assets is byte-identical"
    assert proof.sql(config.database, "SELECT value FROM pe_proof_marker WHERE id = 1;") == "PE_PROOF_VALUE_A"
    assert list(proof.scratch_dir.iterdir()) == []


async def test_either_recipient_can_restore(proof: Restore, keys: SimpleNamespace):
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public, keys.b.public))
    for identity in (keys.a.path, keys.b.path):
        config = proof.new_target()
        assert (await proof.restore(run, target, config, identity)).ok


async def test_a_second_restore_into_the_same_database_is_refused(proof: Restore, keys: SimpleNamespace):
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,))
    config = proof.new_target()
    assert (await proof.restore(run, target, config, keys.a.path)).ok
    again = await proof.restore(run, target, config, keys.a.path)
    assert again.failure is rd.RestoreFailure.DATABASE_NOT_EMPTY and again.step is rd.RestoreStep.DATABASE


async def test_the_source_database_itself_is_refused_as_a_target(proof: Restore, keys: SimpleNamespace):
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,))
    server = proof.cluster.server
    passfile = proof.tmp / "source.pgpass"
    passfile.write_text(f"{server.host}:{server.port}:{proof.source}:{server.superuser}:{proof.password}\n")
    passfile.chmod(0o600)
    config = PgConnectionConfig(server.host, server.port, proof.source, server.superuser, passfile, server.sslmode)
    report = await proof.restore(run, target, config, keys.a.path)
    assert report.failure is rd.RestoreFailure.SCRATCH_UNSAFE and report.step is rd.RestoreStep.GUARDS, "the name marker refuses it"


# --- every failure leaves the target empty ----------------------------------------------------------------------------


async def test_an_identity_that_is_listed_but_cannot_decrypt_leaves_the_database_empty(proof: Restore, keys: SimpleNamespace):
    """The manifest names c as a recipient, but the artifact was encrypted for a and b only."""
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public, keys.b.public), recipients_in_manifest=(keys.a.public, keys.c.public))
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.c.path)
    assert (report.failure, report.step) == (rd.RestoreFailure.DECRYPT_FAILED, rd.RestoreStep.LOAD)
    assert proof.relations(config) == 0


async def test_an_identity_that_is_not_a_recipient_is_refused_before_anything_is_read(proof: Restore, keys: SimpleNamespace):
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public, keys.b.public))
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.c.path)
    assert report.failure is rd.RestoreFailure.IDENTITY_NOT_A_RECIPIENT and report.step is rd.RestoreStep.GUARDS
    assert target.calls == [] and proof.relations(config) == 0


@pytest.mark.parametrize("where", ["header", "middle", "tag"])
async def test_tampered_ciphertext_never_commits(proof: Restore, keys: SimpleNamespace, where: str):
    """The manifest records the tampered bytes, so only age's authentication can stop this."""
    index = {"header": lambda n: 60, "middle": lambda n: n // 2, "tag": lambda n: n - 5}[where]
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,), mutate=lambda c: flip(c, index(len(c))))
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.a.path)
    assert report.failure is rd.RestoreFailure.DECRYPT_FAILED, report.failure
    assert proof.relations(config) == 0, "psql's single transaction was never committed"


async def test_truncated_ciphertext_never_commits(proof: Restore, keys: SimpleNamespace):
    big = proof.pg_dump(proof.source) + b"".join(b"-- padding line %d to make the artifact span several age chunks\n" % n for n in range(60_000))
    big = big.replace(b"-- PostgreSQL database dump complete", b"-- padding\n") + b"\n-- PostgreSQL database dump complete\n"
    run, target = await proof.seal(big, (keys.a.public,), mutate=lambda c: c[: len(c) * 2 // 3])
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.a.path)
    assert report.failure is rd.RestoreFailure.DECRYPT_FAILED
    assert proof.relations(config) == 0


async def test_a_gzip_member_with_a_bad_crc_never_commits_although_psql_received_the_data(proof: Restore, keys: SimpleNamespace):
    """A valid age file around a damaged gzip member: age succeeds, zlib fails at the very end."""
    plain = proof.pg_dump(proof.source)
    compressor = zlib.compressobj(wbits=31)
    member = compressor.compress(plain) + compressor.flush()
    damaged = member[:-6] + bytes([member[-6] ^ 0xFF]) + member[-5:]
    encrypt = await asyncio.to_thread(
        subprocess.run, [tool("age"), "--encrypt", "-r", keys.a.public], input=damaged, capture_output=True, check=True
    )
    run, target = await proof.seal_artifact(encrypt.stdout, (keys.a.public,))
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.a.path)
    assert report.failure is rd.RestoreFailure.GZIP_INVALID
    assert proof.relations(config) == 0


async def test_a_dump_that_pg_dump_never_finished_never_commits(proof: Restore, keys: SimpleNamespace):
    plain = proof.pg_dump(proof.source).replace(b"-- PostgreSQL database dump complete", b"-- cut")
    run, target = await proof.seal(plain, (keys.a.public,))
    config = proof.new_target()
    assert (await proof.restore(run, target, config, keys.a.path)).failure is rd.RestoreFailure.DUMP_INCOMPLETE
    assert proof.relations(config) == 0


async def test_a_role_the_scratch_server_lacks_is_named_and_nothing_is_committed(proof: Restore, keys: SimpleNamespace):
    role = f"pe_restore_role_{uuid.uuid4().hex[:6]}"
    source = f"{SCRATCH_PREFIX}src_{uuid.uuid4().hex[:6]}"
    proof.cluster.sql("postgres", f"CREATE ROLE {role} NOLOGIN;")
    try:
        proof.cluster.sql("postgres", f'CREATE DATABASE "{source}" TEMPLATE template0;')
        proof.sql(source, f"CREATE TABLE owned_by_role (id integer PRIMARY KEY); ALTER TABLE owned_by_role OWNER TO {role};")
        plain = proof.pg_dump(source)
    finally:
        proof.cluster.sql("postgres", f'DROP DATABASE IF EXISTS "{source}" WITH (FORCE);')
        proof.cluster.sql("postgres", f"DROP ROLE IF EXISTS {role};")
    assert f"OWNER TO {role}".encode() in plain
    run, target = await proof.seal(plain, (keys.a.public,))
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.a.path)
    assert report.failure is rd.RestoreFailure.ROLE_MISSING and report.missing_role == role
    assert proof.relations(config) == 0


async def test_a_manifest_that_does_not_describe_the_restored_database_is_reported(proof: Restore, keys: SimpleNamespace):
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,), pending=0)  # the database has one PENDING asset
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.a.path)
    assert (report.failure, report.step) == (rd.RestoreFailure.STATUS_COUNTS_MISMATCH, rd.RestoreStep.CHECKS)
    assert report.ready_count == 2 and report.alembic_revision == resolve_expected_head()
    assert proof.relations(config) > 10, "the load itself succeeded; the mismatch is a finding about the backup"


async def test_a_dump_of_an_older_schema_is_reported_not_silently_accepted(proof: Restore, keys: SimpleNamespace):
    plain = proof.pg_dump(proof.source)
    head = resolve_expected_head().encode()
    assert head in plain
    older = plain.replace(b"\n" + head + b"\n", b"\n0001_older\n", 1)
    assert older != plain
    run, target = await proof.seal(older, (keys.a.public,))
    config = proof.new_target()
    report = await proof.restore(run, target, config, keys.a.path)
    assert report.failure is rd.RestoreFailure.ALEMBIC_MISMATCH and report.alembic_revision == "0001_older"


async def test_the_real_tools_leave_no_plaintext_behind(proof: Restore, keys: SimpleNamespace):
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,))
    config = proof.new_target()
    before = set(proof.tmp.rglob("*"))
    assert (await proof.restore(run, target, config, keys.a.path)).ok
    created = {p for p in set(proof.tmp.rglob("*")) - before if p.is_file()}
    assert all(p.suffix == ".pgpass" or p.name == ENCRYPTED_DUMP_NAME for p in created), created
    assert list(proof.scratch_dir.iterdir()) == []


async def test_cancellation_during_a_real_restore_leaves_the_database_empty(proof: Restore, keys: SimpleNamespace):
    body = b"".join(b"-- padding line %d to make the restore take a moment\n" % n for n in range(2_500_000))
    plain = proof.pg_dump(proof.source)
    marker = b"-- PostgreSQL database dump complete"
    plain = plain.replace(marker, b"") + body + marker + b"\n"
    run, target = await proof.seal(plain, (keys.a.public,))
    config = proof.new_target()
    task = asyncio.ensure_future(proof.restore(run, target, config, keys.a.path))
    await asyncio.sleep(1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proof.relations(config) == 0
    assert list(proof.scratch_dir.iterdir()) == []
