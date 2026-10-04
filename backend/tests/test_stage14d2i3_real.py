"""Stage 14D.2I.3 — opt-in real proof of the WHOLE restore: real age, real PostgreSQL 16, real object bytes.

Gate and environment as `test_stage14d2i1_real.py` (`TEST_REAL_POSTGRES=1`, `TEST_PG16_*`, `age` on PATH).

A database with the real Alembic schema is given real media bytes (the rows' sizes and the original's SHA-256 are
updated to describe them), dumped with `pg_dump`, encrypted with the production primitive, and sealed with a manifest
whose object lines describe the bytes the backup target really holds. `restore_run` then restores the dump into a fresh
scratch database, reads the READY set back from it and restores every object into an empty destination.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.backup import restore_db as rd
from app.backup import restore_media as rm
from app.backup import restore_run as rr
from tests.pg16_proof_fixtures import (  # noqa: F401
    cluster,
    proof_server,
    seeded,
    template_db,
)
from tests.pg16_proof_support import gate_enabled
from tests.test_stage14d2i1_real import (  # noqa: F401
    Restore,
    flip,
    keys,
    proof,
    scratch,
)
from tests.test_stage14d2i2_restore_media import DESTINATION, FORBIDDEN, Destination

pytestmark = pytest.mark.skipif(not gate_enabled(), reason="opt-in: TEST_REAL_POSTGRES=1 (Stage 14D.2I.3)")


async def whole_restore(proof: Restore, run: Any, target: Any, destination: Destination, config: Any, identity: Path, **kwargs: Any) -> rr.RestoreRunReport:  # noqa: F811
    options: dict[str, Any] = {
        "database": config,
        "identity_file": identity,
        "destination": destination,
        "destination_bucket": DESTINATION,
        "forbidden_buckets": FORBIDDEN,
        "scratch_dir": proof.scratch_dir,
        "allowed_hosts": [proof.cluster.server.host],
        "db_timeout_seconds": 300.0,
    }
    options.update(kwargs)
    return await rr.restore_run(target, run.run_id, **options)


async def test_the_whole_restore_with_real_tools_and_real_bytes(proof: Restore, keys: SimpleNamespace):  # noqa: F811
    media = await proof.make_media()
    assert len(media) == 6
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public, keys.b.public), media=media)
    config = proof.new_target()
    destination = Destination()

    report = await whole_restore(proof, run, target, destination, config, keys.b.path)

    assert report.ok, report.report_bytes()
    assert report.step is rr.RunStep.DONE and report.database is not None and report.media is not None
    assert report.database.ready_count == 2 and report.database.status_counts == {"FAILED": 1, "PENDING": 1, "READY": 2}
    assert report.media.counts.restored == 6 and report.media.counts.bytes_restored == sum(map(len, media.values()))
    assert {key: obj.data for key, obj in destination.inner._objects.items()} == media
    assert proof.table_digest(config.database) == proof.table_digest(proof.source)
    assert list(proof.scratch_dir.iterdir()) == []


async def test_a_second_whole_restore_is_refused_by_the_database_and_never_reaches_media(proof: Restore, keys: SimpleNamespace):  # noqa: F811
    media = await proof.make_media()
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,), media=media)
    config = proof.new_target()
    first = Destination()
    assert (await whole_restore(proof, run, target, first, config, keys.a.path)).ok
    second = Destination()
    again = await whole_restore(proof, run, target, second, config, keys.a.path)
    assert again.step is rr.RunStep.DATABASE and again.database is not None
    assert again.database.failure is rd.RestoreFailure.DATABASE_NOT_EMPTY and again.media is None
    assert second.calls == []


async def test_a_bad_database_artifact_leaves_the_destination_untouched(proof: Restore, keys: SimpleNamespace):  # noqa: F811
    media = await proof.make_media()
    run, target = await proof.seal(
        proof.pg_dump(proof.source), (keys.a.public,), media=media, mutate=lambda c: flip(c, len(c) // 2)
    )
    config = proof.new_target()
    destination = Destination()
    report = await whole_restore(proof, run, target, destination, config, keys.a.path)
    assert report.step is rr.RunStep.DATABASE and report.database is not None
    assert report.database.failure is rd.RestoreFailure.DECRYPT_FAILED and report.media is None
    assert destination.calls == [] and proof.relations(config) == 0


async def test_a_damaged_backup_object_is_reported_and_the_rest_is_restored(proof: Restore, keys: SimpleNamespace):  # noqa: F811
    media = await proof.make_media()
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,), media=media)
    victim = min(media)
    target.objects[victim] = flip(target.objects[victim], 0)
    config = proof.new_target()
    destination = Destination()
    report = await whole_restore(proof, run, target, destination, config, keys.a.path)
    assert not report.ok and report.step is rr.RunStep.MEDIA
    assert report.database is not None and report.database.ok, "the database restore itself succeeded"
    assert report.media is not None and [p.code for p in report.media.object_problems] == [rm.ObjectProblemCode.BACKUP_SHA_MISMATCH]
    assert report.media.counts.restored == 5 and victim not in {key for key in destination.inner._objects}


async def test_a_destination_that_holds_other_objects_is_refused_after_the_database_restore(proof: Restore, keys: SimpleNamespace):  # noqa: F811
    media = await proof.make_media()
    run, target = await proof.seal(proof.pg_dump(proof.source), (keys.a.public,), media=media)
    config = proof.new_target()
    destination = Destination()
    destination.seed("photos/v1/00000000-0000-4000-8000-0000000000aa/original.jpg", b"a newer upload")
    report = await whole_restore(proof, run, target, destination, config, keys.a.path)
    assert report.database is not None and report.database.ok
    assert report.media is not None and report.media.preflight is rm.Preflight.FOREIGN_OBJECTS_PRESENT
    assert destination.ops("put_object") == []
