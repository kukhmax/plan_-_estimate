"""Stage 14D.2B — opt-in real-age round-trip proof.

Runs only with `TEST_REAL_AGE=1`; then `age` and `age-keygen` must be on
PATH (missing binaries FAIL instead of skipping). Identities are generated
per run into a private temp directory and never committed or logged.

Proves: source SQL -> production gzip + age primitive -> `age --decrypt`
with a disposable identity -> gzip decompression (CRC32 / ISIZE checked) ->
exact original bytes; two recipients each decrypt; an unrelated identity
cannot.
"""

import hashlib
import os
import shutil
import subprocess
import zlib
from pathlib import Path

import pytest

from app.core.db_dump_encryption import encrypt_dump_artifact
from app.core.pg_snapshot_dump import SnapshotDumpResult
from app.domain.services.media_backup_ready_set import ready_set_digest

pytestmark = pytest.mark.skipif(os.environ.get("TEST_REAL_AGE") != "1", reason="set TEST_REAL_AGE=1 to run")


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.fail(f"TEST_REAL_AGE=1 but {name} is not on PATH")
    return path


def _identity(keys: Path, name: str) -> tuple[Path, str]:
    path = keys / name
    subprocess.run([_tool("age-keygen"), "-o", str(path)], check=True, capture_output=True)
    os.chmod(path, 0o600)
    recipient = subprocess.run(
        [_tool("age-keygen"), "-y", str(path)], check=True, capture_output=True, text=True
    ).stdout.strip()
    assert recipient.startswith("age1")
    return path, recipient


def _decrypt(identity: Path, artifact: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [_tool("age"), "--decrypt", "-i", str(identity), str(artifact)], capture_output=True, check=False
    )


def _age_version_line() -> str:
    reported = subprocess.run([_tool("age"), "--version"], capture_output=True, text=True, check=True).stdout
    return reported.strip().splitlines()[0]


def _source_sql() -> bytes:
    rows = b"".join(b"INSERT INTO photo_assets VALUES ('%06d', 'photos/v1/x/original.jpg', %d);\n" % (i, i * 7)
                    for i in range(60000))
    return (b"--\n-- PostgreSQL database dump\n--\n" + rows + os.urandom(300000).hex().encode()
            + b"\n--\n-- PostgreSQL database dump complete\n--\n")


def _dump(tmp_path: Path, data: bytes) -> SnapshotDumpResult:
    work = tmp_path / "run"
    work.mkdir(mode=0o700)
    path = work / "plan-estimate.sql"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return SnapshotDumpResult(
        snapshot_id="00000003-0000001B-1",
        ready=ready_set_digest([]),
        server_major_version=16,
        dump_path=path,
        dump_size=len(data),
        dump_sha256=hashlib.sha256(data).hexdigest(),
    )


@pytest.fixture
def keys(tmp_path):
    directory = tmp_path / "keys"
    directory.mkdir(mode=0o700)
    return directory


async def test_real_age_round_trip_single_recipient(tmp_path, keys):
    identity, recipient = _identity(keys, "a.txt")
    source = _source_sql()
    dump = _dump(tmp_path, source)
    result = await encrypt_dump_artifact(dump, recipient, age_binary=_tool("age"), timeout_seconds=300)

    ciphertext = result.artifact_path.read_bytes()
    assert hashlib.sha256(ciphertext).hexdigest() == result.artifact_sha256
    assert len(ciphertext) == result.artifact_size
    assert ciphertext.startswith(b"age-encryption.org/v1\n")  # binary (not armored) age file
    assert not dump.dump_path.exists()

    decrypted = _decrypt(identity, result.artifact_path)
    assert decrypted.returncode == 0, decrypted.stderr.decode(errors="replace")
    gz = decrypted.stdout
    assert gz[:3] == b"\x1f\x8b\x08"
    assert gz[3] & 0b00011110 == 0  # no FEXTRA / FNAME / FCOMMENT / FHCRC
    assert gz[4:8] == b"\x00\x00\x00\x00"  # MTIME == 0
    assert b"plan-estimate.sql" not in gz and str(tmp_path).encode() not in gz
    d = zlib.decompressobj(31)  # validates CRC32 and ISIZE at end of member
    plain = d.decompress(gz) + d.flush()
    assert d.eof and d.unused_data == b""
    assert plain == source
    assert hashlib.sha256(plain).hexdigest() == result.plaintext_sha256


async def test_real_age_two_recipients_and_unrelated_identity(tmp_path, keys):
    identity_a, recipient_a = _identity(keys, "a.txt")
    identity_b, recipient_b = _identity(keys, "b.txt")
    identity_c, _ = _identity(keys, "c.txt")
    source = _source_sql()
    dump = _dump(tmp_path, source)
    result = await encrypt_dump_artifact(
        dump, f"{recipient_a},{recipient_b}", age_binary=_tool("age"), timeout_seconds=300
    )
    assert result.recipients == (recipient_a, recipient_b)

    for identity in (identity_a, identity_b):
        decrypted = _decrypt(identity, result.artifact_path)
        assert decrypted.returncode == 0
        assert zlib.decompress(decrypted.stdout, 31) == source

    unrelated = _decrypt(identity_c, result.artifact_path)
    assert unrelated.returncode != 0 and unrelated.stdout == b""


async def test_real_age_version_is_recorded(tmp_path, keys):
    _, recipient = _identity(keys, "a.txt")
    dump = _dump(tmp_path, _source_sql())
    result = await encrypt_dump_artifact(dump, recipient, age_binary=_tool("age"), timeout_seconds=300)
    assert result.age_version == _age_version_line()
