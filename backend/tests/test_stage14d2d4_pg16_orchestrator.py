"""Stage 14D.2D.4 Part D — the real 14D.2D.3 orchestration against PostgreSQL 16.

Opt-in (`TEST_REAL_POSTGRES=1`); additionally needs the real `age` /
`age-keygen` on PATH (the backup image has age 1.3.2) -- a missing age FAILS,
it is not skipped. Runs `run_db_dump` (the CLI path: exit code, preflight,
lock, stale check, offline head, snapshot + metadata hook, pg_dump 16, age,
evidence, promotion) once per candidate role grant set, then independently
verifies the result: decrypt with a disposable identity, gunzip, restore into
a fresh database, recompute the READY digest and read alembic_version.
Reusable by 14D.2D.5 (Compose topology E2E).
"""

import asyncio
import gzip
import hashlib
import io
import json
import os
import shutil

import asyncpg
import pytest

from app.backup.db_dump_command import EXIT_SUCCESS, run_db_dump
from app.backup.schema_revision import resolve_expected_head
from tests.pg16_proof_fixtures import CANDIDATE_CASES
from tests.pg16_proof_support import gate_enabled, restore_file, run_tool, write_report
from tests.test_stage14d2d4_pg16_snapshot import SQL_DIGEST

pytestmark = pytest.mark.skipif(not gate_enabled(), reason="opt-in: TEST_REAL_POSTGRES=1 (Stage 14D.2D.4)")


def require_age() -> tuple[str, str]:
    age, keygen = shutil.which("age"), shutil.which("age-keygen")
    if age is None or keygen is None:
        pytest.fail("Part D needs the real age / age-keygen (run it inside the backup image)")
    return age, keygen


@pytest.mark.parametrize("case", CANDIDATE_CASES)
async def test_d_real_orchestrated_backup(seeded, cluster, tmp_path, monkeypatch, case):
    server, db = seeded.server, seeded.name
    age, keygen = require_age()
    role = cluster.create_role("orch" + case[:6].replace("_", ""), db, case)

    keys = tmp_path / "keys"
    keys.mkdir(mode=0o700)
    identity = keys / "identity.txt"
    run_tool([keygen, "-o", str(identity)], {})
    os.chmod(identity, 0o600)
    recipient = run_tool([keygen, "-y", str(identity)], {}).stdout.decode().strip()

    data_root = tmp_path / "data"
    data_root.mkdir(mode=0o700)
    env = {**server.libpq_env(db, user=role.name, passfile=role.passfile), "BACKUP_AGE_RECIPIENTS": recipient}
    for key in ("PGPASSWORD", "PGSERVICE", "PGSERVICEFILE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)  # 14D.2A's pg_dump inherits the process environment

    out = io.StringIO()
    code = await asyncio.to_thread(run_db_dump, env, out, data_root=data_root, signals=())
    summary = out.getvalue()
    assert code == EXIT_SUCCESS, summary

    work, encrypted, evidence_dir = data_root / "work", data_root / "encrypted", data_root / "evidence"
    assert list(work.iterdir()) == [] and list(evidence_dir.iterdir()) == []
    (run_dir,) = list(encrypted.iterdir())
    assert sorted(p.name for p in run_dir.iterdir()) == ["local-run.json", "plan-estimate.sql.gz.age"]
    evidence = json.loads((run_dir / "local-run.json").read_bytes())
    artifact = run_dir / "plan-estimate.sql.gz.age"
    artifact_bytes = artifact.read_bytes()

    head = resolve_expected_head()
    assert evidence["status"] == "complete" and evidence["run_id"] == run_dir.name
    assert evidence["database"]["alembic_revision"] == evidence["database"]["expected_alembic_head"] == head
    assert evidence["database"]["photo_asset_status_counts"] == {"FAILED": 1, "PENDING": 1, "READY": 2}
    assert evidence["artifact"]["sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert evidence["artifact"]["size"] == len(artifact_bytes)
    assert evidence["artifact"]["recipient_count"] == 1
    assert evidence["artifact"]["age_version"].removeprefix("v") == "1.3.2"
    assert evidence["dump"]["pg_dump_version"].startswith("pg_dump (PostgreSQL) 16.")

    source = await asyncpg.connect(server.dsn(db))
    try:
        ready, digest = await source.fetchrow(SQL_DIGEST)
    finally:
        await source.close()
    assert evidence["snapshot"]["ready_count"] == ready == 2
    assert evidence["snapshot"]["ready_set_sha256"] == digest

    decrypted = run_tool([age, "--decrypt", "-i", str(identity), str(artifact)], {})
    plaintext = gzip.decompress(decrypted.stdout)
    assert hashlib.sha256(plaintext).hexdigest() == evidence["dump"]["plaintext_sha256"]
    verify = cluster.create_db("orchverify")
    restore_input = keys / "restore.sql"
    fd = os.open(restore_input, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(plaintext)
    restore_file(server, verify, restore_input)
    restore_input.unlink()
    restored = await asyncpg.connect(server.dsn(verify))
    try:
        restored_ready, restored_digest = await restored.fetchrow(SQL_DIGEST)
        restored_revision = await restored.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await restored.close()
    assert (restored_ready, restored_digest, restored_revision) == (2, digest, head)

    write_report(server, f"part_d_orchestrator_{case}", {
        "case": case, "exit_code": code, "run_id": evidence["run_id"],
        "work_empty": True, "failure_evidence_present": False,
        "artifact_sha256_matches_evidence": True, "artifact_size": len(artifact_bytes),
        "observed_revision": evidence["database"]["alembic_revision"], "expected_head": head,
        "ready_count": ready, "ready_digest_matches_source": True,
        "decrypt_gunzip_restore": "PASS", "restored_ready_digest_matches": True, "restored_revision": restored_revision,
        "age_version": evidence["artifact"]["age_version"], "pg_dump_version": evidence["dump"]["pg_dump_version"],
    })
