"""Stage 14D.2I.1 — restore of the encrypted database dump (fake age / psql / PostgreSQL).

The pipeline runs real child processes: scripts that behave like age, age-keygen and psql, driven by JSON files
next to them. The real tools are exercised separately (test_stage14d2i1_real.py, opt-in).
"""

import asyncio
import gzip
import hashlib
import json
import os
import sys
import uuid
import zlib
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from app.backup import manifest as mf
from app.backup import restore_db as rd
from app.backup import target as tg
from app.backup.pg_connection import PgConnectionConfig
from app.domain.exceptions import (
    MediaObjectNotFound,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from tests.test_stage14d2e_manifest import RECIPIENT_A
from tests.test_stage14d2g_media_sync import (
    NO_RETRY,
    RETRY_3,
    RUN_1,
    Sleeps,
    World,
    sealed,
)

KEY_LINE = "AGE-SECRET-KEY-1" + "Q" * 58
ALEMBIC_HEAD = "0032_photo_attachments"  # what make_header() records
MARKER = b"-- PostgreSQL database dump complete\n"
DATABASE = "pe_restore_scratch_01"

AGE_SCRIPT = """#!{python}
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "age.json")))
open(os.path.join(here, "age.argv"), "w").write(json.dumps(sys.argv[1:]))
open(os.path.join(here, "age.pid"), "w").write(str(os.getpid()))
if cfg.get("sleep"):
    time.sleep(cfg["sleep"])
data = open(cfg["stdout_file"], "rb").read()
step = cfg.get("step", 65536)
out = sys.stdout.buffer
for i in range(0, len(data), step):
    out.write(data[i:i + step])
    out.flush()
    if cfg.get("pause"):
        time.sleep(cfg["pause"])
if cfg.get("stderr"):
    sys.stderr.write(cfg["stderr"])
sys.exit(cfg.get("exit", 0))
"""

AGE_KEYGEN_SCRIPT = """#!{python}
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "keygen.json")))
open(os.path.join(here, "keygen.argv"), "w").write(json.dumps(sys.argv[1:]))
if cfg.get("output"):
    print(cfg["output"])
sys.exit(cfg.get("exit", 0))
"""

PSQL_SCRIPT = """#!{python}
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "psql.json")))
open(os.path.join(here, "psql.argv"), "w").write(json.dumps(sys.argv[1:]))
open(os.path.join(here, "psql.env"), "w").write(json.dumps({{k: v for k, v in os.environ.items() if k.startswith("PG")}}))
open(os.path.join(here, "psql.pid"), "w").write(str(os.getpid()))
if cfg.get("start_delay"):
    time.sleep(cfg["start_delay"])   # a psql that is not reading: the pipeline backs up
die_after = cfg.get("die_after")
received = 0
capture = open(os.path.join(here, "psql.stdin"), "wb")
while True:
    chunk = os.read(0, 65536)
    if not chunk:
        break
    capture.write(chunk)
    capture.flush()
    received += len(chunk)
    if die_after is not None and received >= die_after:
        sys.stderr.write(cfg.get("die_stderr", "psql: ERROR:  boom\\n"))
        sys.stderr.flush()
        sys.exit(3)
open(os.path.join(here, "psql.eof"), "w").write("1")   # EOF seen == COMMIT would run
if cfg.get("hold"):
    time.sleep(cfg["hold"])
if cfg.get("stderr"):
    sys.stderr.write(cfg["stderr"])
sys.exit(cfg.get("exit", 0))
"""


def sql_dump(extra: bytes = b"") -> bytes:
    return b"-- PostgreSQL database dump\nSET statement_timeout = 0;\nSELECT 1;\n" + extra + MARKER


class Rig:
    """Fake tools, a fake database server and a sealed run, ready for `restore_database`."""

    def __init__(self, tmp_path: Path, world: World) -> None:
        self.tmp = tmp_path
        self.world = world
        self.tools = tmp_path / "tools"
        self.tools.mkdir()
        for name, source in (("age", AGE_SCRIPT), ("age-keygen", AGE_KEYGEN_SCRIPT), ("psql", PSQL_SCRIPT)):
            path = self.tools / name
            path.write_text(source.format(python=sys.executable))
            path.chmod(0o700)
        self.scratch = tmp_path / "scratch"
        self.scratch.mkdir(mode=0o700)
        self.identity = tmp_path / "identity.txt"
        self.identity.write_text(KEY_LINE + "\n")
        self.identity.chmod(0o600)
        pgpass = tmp_path / "pgpass"
        pgpass.write_text(f"127.0.0.1:5432:{DATABASE}:pe_user:s3cretpassword\n")
        pgpass.chmod(0o600)
        self.database = PgConnectionConfig("127.0.0.1", 5432, DATABASE, "pe_user", pgpass, "disable")
        self.plaintext = sql_dump()
        self.set_stream(gzip.compress(self.plaintext, mtime=0))
        self.age(exit=0)
        self.keygen(output=RECIPIENT_A)
        self.psql()
        self.target = tg.InMemoryBackupTarget()
        self.run: mf.VerifiedRun | None = None
        # fake database
        self.connects: list[str] = []
        self.connect_error: Exception | None = None
        self.fetch_error: Exception | None = None
        self.current_database: Any = DATABASE
        self.relations: Any = 0
        self.alembic_rows: list[tuple[Any, ...]] = [(ALEMBIC_HEAD,)]
        self.ready_rows = [self.row_for(asset) for asset in world.assets]
        self.status_rows: list[tuple[Any, ...]] = [("READY", len(world.assets))]
        self.reader: Any = self.target

    @staticmethod
    def row_for(asset: Any) -> tuple[Any, ...]:
        return (
            asset.asset_id, asset.key_original, asset.key_display, asset.key_thumbnail,
            asset.byte_size, asset.display_byte_size, asset.thumbnail_byte_size, asset.sha256,
        )  # fmt: skip

    # -- fake tool configuration -------------------------------------------------------------------------

    def set_stream(self, data: bytes) -> None:
        path = self.tools / "stream.bin"
        path.write_bytes(data)
        self.stream = path

    def age(self, **cfg: Any) -> None:
        # A short pause before the first byte lets the fake psql (a Python process) start first, so that the
        # "psql never saw EOF" assertions are about a live psql and not vacuous.
        (self.tools / "age.json").write_text(json.dumps({"stdout_file": str(self.stream), "sleep": 0.4, **cfg}))

    def keygen(self, **cfg: Any) -> None:
        (self.tools / "keygen.json").write_text(json.dumps(cfg))

    def psql(self, **cfg: Any) -> None:
        (self.tools / "psql.json").write_text(json.dumps(cfg))

    def seen(self, name: str) -> Any:
        path = self.tools / name
        if not path.exists():
            return None
        return json.loads(path.read_text()) if name.endswith((".argv", ".env")) else path.read_bytes()

    def psql_got_eof(self) -> bool:
        return (self.tools / "psql.eof").exists()

    # -- fake asyncpg ---------------------------------------------------------------------------------------

    async def connect(self, dsn: str, **kwargs: Any) -> "FakeConn":
        self.connects.append(dsn)
        if self.connect_error is not None:
            raise self.connect_error
        return FakeConn(self)

    # -- run ---------------------------------------------------------------------------------------------------

    async def seal(self) -> mf.VerifiedRun:
        if self.run is None:
            self.run = await sealed(self.world, self.target, self.scratch, self.tmp, RUN_1)
            self.target.calls.clear()
            assert self.scratch.exists() and not list(self.scratch.iterdir())
        return self.run

    async def restore(self, **overrides: Any) -> rd.DbRestoreReport:
        run = await self.seal()
        options: dict[str, Any] = {
            "database": self.database,
            "identity_file": self.identity,
            "scratch_dir": self.scratch,
            "age_path": str(self.tools / "age"),
            "age_keygen_path": str(self.tools / "age-keygen"),
            "psql_path": str(self.tools / "psql"),
            "connect": self.connect,
            "retry": NO_RETRY,
            "sleep": Sleeps(),
            "timeout_seconds": 60.0,
            "repository_head": lambda: ALEMBIC_HEAD,
        }
        options.update(overrides)
        return await rd.restore_database(self.reader, run, **options)


class FakeConn:
    def __init__(self, rig: Rig) -> None:
        self.rig = rig
        self.closed = False
        self.executed: list[str] = []

    async def fetchval(self, sql: str) -> Any:
        if self.rig.fetch_error is not None:
            raise self.rig.fetch_error
        return {rd.CURRENT_DATABASE_SQL: self.rig.current_database, rd.USER_RELATIONS_SQL: self.rig.relations}[sql]

    async def execute(self, sql: str) -> None:
        self.executed.append(sql)

    async def fetch(self, sql: str) -> list[tuple[Any, ...]]:
        if self.rig.fetch_error is not None:
            raise self.rig.fetch_error
        return {
            rd.ALEMBIC_SQL: self.rig.alembic_rows,
            rd.READY_INVENTORY_SQL: self.rig.ready_rows,
            rd.STATUS_COUNTS_SQL: self.rig.status_rows,
        }[sql]

    async def close(self) -> None:
        self.closed = True

    def terminate(self) -> None:
        self.closed = True


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path, World(2))


def assert_clean(rig: Rig) -> None:
    assert list(rig.scratch.iterdir()) == [], "the encrypted copy must always be removed"


def flip_byte(data: bytes, index: int) -> bytes:
    return data[:index] + bytes([data[index] ^ 0xFF]) + data[index + 1 :]


# --- the happy path ------------------------------------------------------------------------------------------------


async def test_a_good_restore_loads_the_dump_and_proves_the_result(rig: Rig):
    report = await rig.restore()
    assert report.ok and report.step is rd.RestoreStep.DONE and report.failure is None
    assert report.plaintext_bytes == len(rig.plaintext) and report.plaintext_sha256 == hashlib.sha256(rig.plaintext).hexdigest()
    run = rig.run
    assert run is not None
    assert report.encrypted_bytes == run.manifest.header.db_dump.encrypted_size
    assert report.alembic_revision == ALEMBIC_HEAD and report.matches_repository_head is True
    assert report.ready_count == 2 and report.status_counts == {"FAILED": 0, "PENDING": 0, "READY": 2}
    assert rig.seen("psql.stdin") == rig.plaintext, "psql received exactly the decrypted, gunzipped dump"
    assert rig.psql_got_eof(), "psql is released (COMMIT) after every gate passed"
    assert_clean(rig)


async def test_a_large_stream_is_forwarded_in_bounded_chunks(rig: Rig):
    body = b"".join(b"INSERT INTO t VALUES (%d, 'row-%d');\n" % (n, n) for n in range(300_000))  # ~12 MiB plain
    rig.plaintext = sql_dump(body)
    rig.set_stream(gzip.compress(rig.plaintext, mtime=0))
    rig.age(step=100_000)
    report = await rig.restore()
    assert report.ok and rig.seen("psql.stdin") == rig.plaintext
    assert report.plaintext_sha256 == hashlib.sha256(rig.plaintext).hexdigest()


async def test_the_tools_get_the_documented_command_lines_and_environment(rig: Rig):
    await rig.restore()
    assert rig.seen("age.argv") == ["--decrypt", "-i", str(rig.identity), rig.seen("age.argv")[-1]]
    assert rig.seen("age.argv")[-1].endswith("artifact.age")
    assert rig.seen("keygen.argv") == ["-y", str(rig.identity)]
    assert rig.seen("psql.argv") == ["-X", "-q", "-v", "ON_ERROR_STOP=1", "--single-transaction", "--no-password", "-f", "-"]
    env = rig.seen("psql.env")
    assert env == {
        "PGHOST": "127.0.0.1", "PGPORT": "5432", "PGDATABASE": DATABASE, "PGUSER": "pe_user",
        "PGPASSFILE": str(rig.database.passfile), "PGSSLMODE": "disable",
    }  # fmt: skip
    assert "s3cretpassword" not in json.dumps(rig.seen("psql.argv")) and "PGPASSWORD" not in env


def test_the_command_builders_never_contain_a_secret_or_a_forbidden_option(tmp_path: Path):
    identity, artifact = tmp_path / "i", tmp_path / "a"
    decrypt = rd.age_decrypt_argv("age", identity, artifact)
    assert decrypt == ["age", "--decrypt", "-i", str(identity), str(artifact)]
    assert not {"-o", "--output", "--armor", "-a", "-p", "--passphrase"} & set(decrypt)
    assert rd.age_public_key_argv("age-keygen", identity) == ["age-keygen", "-y", str(identity)]
    assert "--single-transaction" in rd.psql_restore_argv("psql") and "ON_ERROR_STOP=1" in rd.psql_restore_argv("psql")


async def test_the_report_is_canonical_and_secret_free(rig: Rig):
    report = await rig.restore()
    data = report.report_bytes()
    document = json.loads(data)
    assert data == mf.canonical_line(document) and data.count(b"\n") == 1
    assert document["format"] == "plan-estimate/db-restore-report/v1" and document["ok"] is True
    text = data.decode()
    for secret in (str(rig.identity), "s3cretpassword", "127.0.0.1", DATABASE, KEY_LINE, RECIPIENT_A):
        assert secret not in text
    assert report.report_bytes() == data


async def test_no_plaintext_file_is_written_anywhere_under_the_scratch_directory(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
):
    seen: list[str] = []
    original = rd._load

    async def spy(**kwargs: Any) -> rd._Load:
        seen.extend(str(p.relative_to(rig.scratch)) for p in rig.scratch.rglob("*"))
        return await original(**kwargs)

    monkeypatch.setattr(rd, "_load", spy)
    await rig.restore()
    assert len(seen) == 2 and max(seen).endswith("artifact.age"), "only the encrypted copy and its directory"


# --- guards ----------------------------------------------------------------------------------------------------------


async def test_an_unsafe_database_is_refused_before_anything_else_happens(rig: Rig):
    pgpass = rig.tmp / "pgpass2"
    pgpass.write_text("127.0.0.1:5432:plan_estimate:pe_user:s3cretpassword\n")
    pgpass.chmod(0o600)
    rig.database = PgConnectionConfig("127.0.0.1", 5432, "plan_estimate", "pe_user", pgpass, "disable")
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.SCRATCH_UNSAFE, rd.RestoreStep.GUARDS)
    assert rig.connects == [] and rig.target.calls == [] and rig.seen("age.argv") is None and rig.seen("keygen.argv") is None


async def test_an_unsafe_host_is_refused_unless_explicitly_allowed(rig: Rig):
    pgpass = rig.tmp / "pgpass3"
    pgpass.write_text(f"db.example.com:5432:{DATABASE}:pe_user:s3cretpassword\n")
    pgpass.chmod(0o600)
    rig.database = PgConnectionConfig("db.example.com", 5432, DATABASE, "pe_user", pgpass, "disable")
    assert (await rig.restore()).failure is rd.RestoreFailure.SCRATCH_UNSAFE
    assert (await rig.restore(allowed_hosts=["db.example.com"])).ok


@pytest.mark.parametrize("problem", ["missing", "mode", "content"])
async def test_an_unusable_identity_file_is_refused_locally(rig: Rig, problem: str):
    if problem == "missing":
        rig.identity.unlink()
    elif problem == "mode":
        rig.identity.chmod(0o644)
    else:
        rig.identity.write_text("not a key\n")
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.IDENTITY_INVALID, rd.RestoreStep.GUARDS)
    assert rig.seen("keygen.argv") is None and rig.connects == []


async def test_an_identity_the_tool_does_not_accept_is_refused(rig: Rig):
    rig.keygen(exit=1)
    assert (await rig.restore()).failure is rd.RestoreFailure.IDENTITY_INVALID
    rig.keygen(output="garbage")
    assert (await rig.restore()).failure is rd.RestoreFailure.IDENTITY_INVALID
    rig.keygen(output=RECIPIENT_A + "\n" + RECIPIENT_A)
    assert (await rig.restore()).failure is rd.RestoreFailure.IDENTITY_INVALID


async def test_an_identity_that_is_not_a_recipient_of_the_run_is_refused_before_downloading(rig: Rig):
    rig.keygen(output="age1" + "z" * 58)
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.IDENTITY_NOT_A_RECIPIENT
    assert rig.target.calls == [] and rig.connects == [], "nothing was downloaded or connected"


async def test_missing_tools_are_reported(rig: Rig):
    assert (await rig.restore(age_keygen_path=str(rig.tools / "nope"))).failure is rd.RestoreFailure.TOOL_UNUSABLE
    assert (await rig.restore(age_path=str(rig.tools / "nope"))).failure is rd.RestoreFailure.TOOL_UNUSABLE
    assert not rig.psql_got_eof()
    assert (await rig.restore(psql_path=str(rig.tools / "nope"))).failure is rd.RestoreFailure.TOOL_UNUSABLE
    assert_clean(rig)


# --- database preflight ----------------------------------------------------------------------------------------------------


async def test_an_unreachable_database_is_reported(rig: Rig):
    rig.connect_error = OSError("refused")
    assert (await rig.restore()).failure is rd.RestoreFailure.DATABASE_UNREACHABLE
    rig.connect_error = None
    rig.fetch_error = asyncpg.PostgresConnectionError("lost")
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.DATABASE_UNREACHABLE, rd.RestoreStep.DATABASE)
    assert rig.target.calls == []


async def test_a_database_that_is_not_the_configured_one_is_refused(rig: Rig):
    rig.current_database = "plan_estimate"
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.SCRATCH_UNSAFE and rig.target.calls == []


async def test_a_database_that_is_not_empty_is_refused_before_downloading(rig: Rig):
    rig.relations = 3
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.DATABASE_NOT_EMPTY, rd.RestoreStep.DATABASE)
    assert rig.target.calls == [] and rig.seen("age.argv") is None


async def test_the_connection_never_carries_a_password(rig: Rig):
    await rig.restore()
    assert rig.connects and all("s3cretpassword" not in dsn and "passfile=" in dsn for dsn in rig.connects)


# --- the artifact ---------------------------------------------------------------------------------------------------------------


async def test_a_missing_dump_is_reported(rig: Rig):
    run = await rig.seal()
    del rig.target.objects[run.manifest.header.db_dump.key]
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.DUMP_MISSING, rd.RestoreStep.ARTIFACT)
    assert rig.seen("age.argv") is None and not rig.psql_got_eof()


async def test_a_dump_of_another_size_is_refused_before_decryption(rig: Rig):
    run = await rig.seal()
    rig.target.objects[run.manifest.header.db_dump.key] += b"x"
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.DUMP_SIZE_MISMATCH and rig.seen("age.argv") is None
    assert_clean(rig)


async def test_a_dump_with_changed_bytes_is_refused_before_decryption(rig: Rig):
    run = await rig.seal()
    key = run.manifest.header.db_dump.key
    rig.target.objects[key] = flip_byte(rig.target.objects[key], 3)
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.DUMP_SHA_MISMATCH and report.encrypted_bytes > 0
    assert rig.seen("age.argv") is None, "the ciphertext is not handed to age unless it is the one the manifest records"
    assert_clean(rig)


async def test_storage_failures_while_fetching_the_dump(rig: Rig):
    await rig.seal()
    rig.target.inject("download_to", MediaStorageUnavailable("x", error_code="Throttled", http_status=503))
    assert (await rig.restore()).failure is rd.RestoreFailure.STORAGE_UNAVAILABLE
    rig.target.inject("download_to", MediaStorageMisconfigured("x", error_code="AccessDenied", http_status=403))
    assert (await rig.restore()).failure is rd.RestoreFailure.STORAGE_MISCONFIGURED
    rig.target.inject("download_to", MediaObjectNotFound("gone"))
    assert (await rig.restore()).failure is rd.RestoreFailure.DUMP_MISSING
    assert_clean(rig)


async def test_transient_storage_errors_are_retried(rig: Rig):
    await rig.seal()
    sleeps = Sleeps()
    rig.target.inject("download_to", MediaStorageUnavailable("x", error_code="Throttled", http_status=503), times=2)
    report = await rig.restore(retry=RETRY_3, sleep=sleeps)
    assert report.ok and sleeps.values == [0.5, 1.0]


# --- the load: every gate must hold before psql is released ----------------------------------------------------------------------


async def test_a_decryption_failure_never_lets_psql_commit(rig: Rig):
    rig.age(exit=1, stderr="age: error: no identity matched any of the recipients\n")
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.DECRYPT_FAILED, rd.RestoreStep.LOAD)
    assert rig.seen("psql.stdin") == rig.plaintext, "the data arrived; the transaction was simply never committed"
    assert not rig.psql_got_eof()
    assert_clean(rig)


async def test_ciphertext_cut_off_part_way_never_commits(rig: Rig):
    body = b"".join(b"-- row %d\n" % n for n in range(200_000))
    rig.plaintext = sql_dump(body)
    compressed = gzip.compress(rig.plaintext, mtime=0)
    rig.set_stream(compressed[: len(compressed) // 2])
    rig.age(exit=1, stderr="age: error: truncated\n", step=50_000)
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.DECRYPT_FAILED, "age's failure is the root cause, not the short gzip stream"
    assert not rig.psql_got_eof()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c[:-1] + bytes([c[-1] ^ 0xFF]),  # ISIZE
        lambda c: c[:-6] + bytes([c[-6] ^ 0xFF]) + c[-5:],  # CRC32
        lambda c: c[:-8],  # no trailer
        lambda c: c + b"trailing garbage",
        lambda c: c + gzip.compress(b"-- a second member\n", mtime=0),
        lambda c: flip_byte(c, len(c) // 2),  # inside the deflate stream
        lambda c: b"\x00" + c[1:],  # not gzip at all
    ],
    ids=["isize", "crc32", "no-trailer", "trailing-garbage", "second-member", "deflate-body", "not-gzip"],
)
async def test_a_gzip_stream_that_is_not_one_clean_member_never_commits(rig: Rig, mutate: Any):
    rig.set_stream(mutate(gzip.compress(rig.plaintext, mtime=0)))
    rig.age()
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.GZIP_INVALID, rd.RestoreStep.LOAD)
    assert not rig.psql_got_eof()
    assert_clean(rig)


async def test_a_bad_trailer_is_noticed_only_after_data_was_sent_and_still_does_not_commit(rig: Rig):
    rig.plaintext = sql_dump(b"".join(b"INSERT INTO t VALUES (%d);\n" % n for n in range(400_000)))
    c = gzip.compress(rig.plaintext, mtime=0)
    rig.set_stream(c[:-6] + bytes([c[-6] ^ 0xFF]) + c[-5:])
    rig.age(step=30_000)
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.GZIP_INVALID
    got = rig.seen("psql.stdin")
    assert got and rig.plaintext.startswith(got), "statements were already delivered when the trailer failed"
    assert not rig.psql_got_eof(), "the commit gate is the point: psql never saw EOF"


async def test_data_arriving_as_a_later_chunk_after_the_end_of_the_member_is_refused(rig: Rig):
    member = gzip.compress(rig.plaintext, mtime=0)
    rig.set_stream(member + b"late bytes")
    rig.age(step=len(member), pause=0.3)  # the member, then (after a pause: a pipe merges back-to-back writes) the extra bytes
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.GZIP_INVALID and not rig.psql_got_eof()


async def test_a_corrupt_stream_stops_the_decryption_early(rig: Rig):
    rig.plaintext = sql_dump(b"".join(b"INSERT INTO t VALUES (%d);\n" % n for n in range(600_000)))
    member = bytearray(gzip.compress(rig.plaintext, mtime=0))
    member[:2] = b"\x00\x00"  # not gzip from the very first byte
    rig.set_stream(bytes(member))
    rig.age(step=20_000, pause=0.15, sleep=0.4)  # the whole stream would take far longer than the assertion below
    started = asyncio.get_running_loop().time()
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.GZIP_INVALID
    assert asyncio.get_running_loop().time() - started < 3.0, "age is killed at the first bad byte, not read to the end"


async def test_a_dump_without_pg_dumps_completion_marker_never_commits(rig: Rig):
    rig.plaintext = b"-- PostgreSQL database dump\nSELECT 1;\n"
    rig.set_stream(gzip.compress(rig.plaintext, mtime=0))
    rig.age()
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.DUMP_INCOMPLETE and not rig.psql_got_eof()


async def test_the_marker_must_be_in_the_tail_of_the_dump(rig: Rig):
    rig.plaintext = MARKER + b"-- more statements after the marker\n" * 400
    rig.set_stream(gzip.compress(rig.plaintext, mtime=0))
    rig.age()
    assert (await rig.restore()).failure is rd.RestoreFailure.DUMP_INCOMPLETE


async def test_an_oversized_plaintext_is_stopped(rig: Rig):
    rig.plaintext = sql_dump(b"-- x\n" * 100_000)
    rig.set_stream(gzip.compress(rig.plaintext, mtime=0))
    rig.age()
    report = await rig.restore(max_plaintext_bytes=100_000)
    assert report.failure is rd.RestoreFailure.PLAINTEXT_TOO_LARGE and not rig.psql_got_eof()
    assert report.plaintext_bytes > 100_000


async def test_a_gzip_bomb_cannot_exhaust_memory_through_one_chunk(rig: Rig):
    rig.plaintext = sql_dump(b"\x00" * (64 * 2**20))
    c = zlib.compressobj(wbits=31)
    rig.set_stream(c.compress(rig.plaintext) + c.flush())
    assert os.path.getsize(rig.stream) < 100_000
    rig.age()
    report = await rig.restore(max_plaintext_bytes=2 * 2**20)
    assert report.failure is rd.RestoreFailure.PLAINTEXT_TOO_LARGE and report.plaintext_bytes < 8 * 2**20


async def test_psql_failing_early_stops_the_feed_and_reports_a_generic_failure(rig: Rig):
    rig.plaintext = sql_dump(b"-- row\n" * 400_000)
    rig.set_stream(gzip.compress(rig.plaintext, mtime=0))
    rig.age(step=20_000)
    rig.psql(die_after=1000, die_stderr='psql:<stdin>:3: ERROR:  invalid input syntax\nCONTEXT:  COPY photo_assets, line 1: "Jan Kowalski ul. Testowa 1"\n')
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.PSQL_FAILED, rd.RestoreStep.LOAD)
    assert report.missing_role is None
    assert not rig.psql_got_eof()
    text = report.report_bytes().decode()
    assert "Kowalski" not in text and "Testowa" not in text and "COPY" not in text, "psql's text never reaches a report"
    assert_clean(rig)


async def test_a_missing_role_is_named_and_nothing_else_from_psql(rig: Rig):
    rig.psql(die_after=10, die_stderr='psql:<stdin>:12: ERROR:  role "plan_estimate" does not exist\n')
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.ROLE_MISSING and report.missing_role == "plan_estimate"
    assert json.loads(report.report_bytes())["missing_role"] == "plan_estimate"


async def test_a_role_name_that_is_not_a_plain_identifier_is_not_reported(rig: Rig):
    rig.psql(die_after=10, die_stderr='ERROR:  role "evil; DROP" does not exist\n')
    report = await rig.restore()
    assert report.failure is rd.RestoreFailure.PSQL_FAILED and report.missing_role is None


async def test_psql_failing_at_commit_time_is_a_failure(rig: Rig):
    rig.psql(exit=1, stderr="ERROR:  could not commit\n")
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.PSQL_FAILED, rd.RestoreStep.LOAD)
    assert rig.psql_got_eof(), "this is the one case where psql did see EOF"


async def test_a_restore_that_takes_too_long_is_stopped_and_both_children_die(rig: Rig):
    rig.age(sleep=60)
    report = await rig.restore(timeout_seconds=1.0)
    assert report.failure is rd.RestoreFailure.RESTORE_TIMEOUT and not rig.psql_got_eof()
    await asyncio.sleep(0.2)
    for name in ("age.pid", "psql.pid"):
        pid = int((rig.tools / name).read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    assert_clean(rig)


async def test_cancellation_kills_the_children_psql_included_and_propagates(rig: Rig):
    rig.age(sleep=60)
    await rig.seal()
    task = asyncio.ensure_future(rig.restore())
    for _ in range(200):
        await asyncio.sleep(0.05)
        if (rig.tools / "age.pid").exists() and (rig.tools / "psql.pid").exists():
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.2)
    for name in ("age.pid", "psql.pid"):
        with pytest.raises(ProcessLookupError):
            os.kill(int((rig.tools / name).read_text()), 0)
    assert not rig.psql_got_eof()
    assert_clean(rig)


# --- checks after the load ------------------------------------------------------------------------------------------------------------


async def test_a_different_alembic_revision_is_a_failure(rig: Rig):
    rig.alembic_rows = [("0031_older",)]
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.ALEMBIC_MISMATCH, rd.RestoreStep.CHECKS)
    assert report.alembic_revision == "0031_older" and report.plaintext_bytes > 0


@pytest.mark.parametrize("rows", [[], [(ALEMBIC_HEAD,), (ALEMBIC_HEAD,)], [("bad revision!",)], [(None,)]])
async def test_an_ambiguous_alembic_state_is_a_failure(rig: Rig, rows: list[tuple[Any, ...]]):
    rig.alembic_rows = rows
    assert (await rig.restore()).failure is rd.RestoreFailure.ALEMBIC_MISMATCH


async def test_a_missing_alembic_table_makes_the_checks_unreadable(rig: Rig):
    await rig.seal()
    original = rig.connect
    state = {"calls": 0}

    async def connect(dsn: str, **kwargs: Any) -> FakeConn:
        state["calls"] += 1
        conn = await original(dsn, **kwargs)
        if state["calls"] == 2:  # the connection of the checks
            rig.fetch_error = asyncpg.UndefinedTableError("relation does not exist")
        return conn

    report = await rig.restore(connect=connect)
    assert (report.failure, report.step) == (rd.RestoreFailure.CHECKS_UNREADABLE, rd.RestoreStep.CHECKS)


async def test_a_connection_failure_after_the_load_makes_the_checks_unreadable(rig: Rig):
    await rig.seal()
    state = {"calls": 0}

    async def connect(dsn: str, **kwargs: Any) -> FakeConn:
        state["calls"] += 1
        if state["calls"] == 2:
            raise OSError("connection reset")
        return await rig.connect(dsn, **kwargs)

    assert (await rig.restore(connect=connect)).failure is rd.RestoreFailure.CHECKS_UNREADABLE


async def test_the_repository_head_is_informational(rig: Rig):
    assert (await rig.restore(repository_head=lambda: "0099_newer")).matches_repository_head is False

    def unresolved() -> str:
        raise rd.ExpectedHeadError("no head")

    report = await rig.restore(repository_head=unresolved)
    assert report.ok and report.matches_repository_head is None


def mutate_ready(rows: list[tuple[Any, ...]], how: str) -> list[tuple[Any, ...]]:
    rows = list(rows)
    if how == "extra":
        rows.append((uuid.uuid4(), "photos/v1/x/original.jpg", "photos/v1/x/display.jpg", "photos/v1/x/thumb.jpg", 5, 4, 3, "a" * 64))
    elif how == "missing":
        rows.pop()
    elif how == "sha":
        rows[0] = (*rows[0][:7], "b" * 64)
    elif how == "size":
        rows[0] = (*rows[0][:4], rows[0][4] + 1, *rows[0][5:])
    elif how == "key":
        rows[0] = (rows[0][0], rows[0][1].replace("original", "orig"), *rows[0][2:])
    elif how == "malformed":
        rows[0] = (rows[0][0], None, *rows[0][2:])
    elif how == "bad-id":
        rows[0] = ("not-a-uuid", *rows[0][1:])
    return rows


@pytest.mark.parametrize("how", ["extra", "missing", "sha", "size", "key", "malformed", "bad-id"])
async def test_a_ready_set_that_differs_from_the_manifest_is_a_failure(rig: Rig, how: str):
    rig.ready_rows = mutate_ready(rig.ready_rows, how)
    report = await rig.restore()
    assert (report.failure, report.step) == (rd.RestoreFailure.READY_SET_MISMATCH, rd.RestoreStep.CHECKS)
    assert report.alembic_revision == ALEMBIC_HEAD, "earlier facts stay in the report"


@pytest.mark.parametrize(
    "rows",
    [
        [("READY", 2), ("PENDING", 1)],
        [("READY", 2), ("FAILED", 1)],
        [("READY", 3)],
        [("READY", 2), ("ARCHIVED", 1)],
        [("READY", 2), ("READY", 1)],
    ],
)
async def test_status_counts_that_differ_from_the_manifest_are_a_failure(rig: Rig, rows: list[tuple[Any, ...]]):
    rig.status_rows = rows
    assert (await rig.restore()).failure is rd.RestoreFailure.STATUS_COUNTS_MISMATCH


async def test_pending_and_failed_counts_that_equal_the_manifests_pass(rig: Rig, tmp_path: Path):
    """The manifest records how many PENDING / FAILED assets were skipped; the restored database must agree."""
    run = await rig.seal()
    skipped = mf.Manifest(run.manifest.header, run.manifest.objects, mf.ManifestSummary(
        ready_assets=run.manifest.summary.ready_assets, objects=run.manifest.summary.objects,
        total_bytes=run.manifest.summary.total_bytes, skipped_pending=2, skipped_failed=1,
        source_keys=run.manifest.summary.source_keys, orphan_candidates=run.manifest.summary.orphan_candidates,
    ))  # fmt: skip
    rig.run = mf.VerifiedRun(complete=run.complete, manifest=skipped)
    rig.status_rows = [("READY", 2), ("PENDING", 2), ("FAILED", 1)]
    assert (await rig.restore()).ok
    rig.status_rows = [("READY", 2), ("PENDING", 1), ("FAILED", 1)]
    assert (await rig.restore()).failure is rd.RestoreFailure.STATUS_COUNTS_MISMATCH


# --- hygiene --------------------------------------------------------------------------------------------------------------------------------


async def test_every_connection_is_closed(rig: Rig):
    closed: list[FakeConn] = []
    original = rig.connect

    async def connect(dsn: str, **kwargs: Any) -> FakeConn:
        conn = await original(dsn, **kwargs)
        closed.append(conn)
        return conn

    assert (await rig.restore(connect=connect)).ok
    assert len(closed) == 2 and all(conn.closed for conn in closed)


async def test_an_unexpected_error_propagates_and_cleans_up(rig: Rig):
    await rig.seal()
    rig.target.inject("download_to", RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        await rig.restore()
    assert_clean(rig)


def test_a_failed_report_is_never_ok():
    report = rd.DbRestoreReport("20261004T120000Z-0123abcd", rd.RestoreStep.LOAD, rd.RestoreFailure.DECRYPT_FAILED)
    assert not report.ok
    assert not rd.DbRestoreReport("20261004T120000Z-0123abcd", rd.RestoreStep.CHECKS, None).ok, "DONE is required"
    assert rd.DbRestoreReport("20261004T120000Z-0123abcd", rd.RestoreStep.DONE, None).ok


# --- resource hygiene: no pipe or process transport outlives the event loop ----------------------------------------------------------------


def _run_on_a_private_loop_and_collect_garbage(scenario: Any) -> list[str]:
    """Run `scenario()` on its own loop, close the loop, collect garbage and return what the interpreter complained
    about (an unclosed subprocess transport is only noticed when it is garbage collected after the loop is gone)."""
    import gc

    complaints: list[str] = []
    previous = sys.unraisablehook
    sys.unraisablehook = lambda args: complaints.append(f"{args.exc_type.__name__}: {args.exc_value}")
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(scenario())
        finally:
            loop.close()
        gc.collect()
    finally:
        sys.unraisablehook = previous
    return complaints


def test_no_transport_outlives_the_loop_after_a_cancelled_restore(tmp_path: Path):
    rig = Rig(tmp_path, World(1))

    async def scenario() -> None:
        rig.age(sleep=60)
        await rig.seal()
        task = asyncio.ensure_future(rig.restore())
        for _ in range(200):
            await asyncio.sleep(0.05)
            if (rig.tools / "age.pid").exists() and (rig.tools / "psql.pid").exists():
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert _run_on_a_private_loop_and_collect_garbage(scenario) == []


def test_no_transport_outlives_the_loop_when_the_pipeline_was_backed_up(tmp_path: Path):
    """psql is not reading, so age's output piles up unread when the restore is cancelled."""
    rig = Rig(tmp_path, World(1))
    rig.plaintext = sql_dump(os.urandom(6 * 2**20))
    rig.set_stream(gzip.compress(rig.plaintext, mtime=0))

    async def scenario() -> None:
        rig.age(sleep=0.2, step=500_000)
        rig.psql(start_delay=60)
        await rig.seal()
        task = asyncio.ensure_future(rig.restore())
        for _ in range(200):
            await asyncio.sleep(0.05)
            if (rig.tools / "psql.pid").exists():
                break
        await asyncio.sleep(1.5)  # age has filled the pipes
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert _run_on_a_private_loop_and_collect_garbage(scenario) == []


def test_no_transport_outlives_the_loop_after_a_failed_restore(tmp_path: Path):
    rig = Rig(tmp_path, World(1))

    async def scenario() -> None:
        rig.age(exit=1, stderr="age: error: boom\n")
        report = await rig.restore()
        assert report.failure is rd.RestoreFailure.DECRYPT_FAILED

    assert _run_on_a_private_loop_and_collect_garbage(scenario) == []
