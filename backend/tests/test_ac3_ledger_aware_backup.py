"""Archive cleanup AC-3a -- the backup tooling knows the purge ledger.

The ledger file is read strictly (a wrong line would delete the wrong object); `verify` accepts the objects the ledger purged as absent;
`restore` never copies a purged object back and replays the ledger on the restored database; the server-side export / mark-done never let a drill
rehearsal mark a production row.
"""
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup import purge_ledger as pl
from app.backup import purge_replay as pr
from app.backup import restore_media as rm
from app.backup import restore_run as rr
from app.backup import verify as vf
from app.backup.purge_report import ReportEntry, parse_report, serialize_report
from tests.test_stage14d2g_media_sync import World
from tests.test_stage14d2h_verify import (  # noqa: F401  (the fixture)
    published,
    scratch,
    verify,
)
from tests.test_stage14d2i2_restore_media import Rig as MediaRig
from tests.test_stage14d2i2_restore_media import assert_clean, stored
from tests.test_stage14d2i3_restore_run import Chain

NOW = "2026-10-16T20:00:00Z"
SHA = "a" * 64


def entry(world: World, index: int) -> pl.LedgerEntry:
    asset = world.assets[index]
    return pl.LedgerEntry(
        id=uuid.UUID(int=index + 1), asset_id=asset.asset_id, storage_name="r2", key_original=asset.key_original, key_display=asset.key_display,
        key_thumbnail=asset.key_thumbnail, sha256=SHA, size_original=asset.byte_size, size_display=asset.display_byte_size,
        size_thumbnail=asset.thumbnail_byte_size, purged_at="2026-10-16T19:00:00Z",
    )


def ledger_bytes(world: World, *indexes: int) -> bytes:
    return pl.serialize_ledger([entry(world, i) for i in indexes], exported_at=NOW)


# --- the file ----------------------------------------------------------------------------------------------------------------


def test_a_ledger_round_trips_and_names_exactly_the_three_keys_of_each_asset():
    world = World(3)
    parsed = pl.parse_ledger(ledger_bytes(world, 0, 2))
    assert parsed.exported_at == NOW and len(parsed.entries) == 2
    assert parsed.asset_ids == {world.assets[0].asset_id, world.assets[2].asset_id}
    assert parsed.purged_keys == {world.key_of(i, role) for i in (0, 2) for role in ("original", "display", "thumbnail")}
    assert pl.serialize_ledger(list(parsed.entries), exported_at=NOW) == ledger_bytes(world, 0, 2)  # canonical and stable


def lines(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode().splitlines()]


def rebuilt(documents: list[dict]) -> bytes:
    return "".join(mf.canonical_line(d).decode() for d in documents).encode()


def broken(world: World, change) -> bytes:
    documents = lines(ledger_bytes(world, 0, 1))
    change(documents)
    return rebuilt(documents)


@pytest.mark.parametrize("name, change", [
    ("a key of another asset", lambda d: d[1]["keys"].update(display=d[2]["keys"]["display"])),
    ("the original of another asset", lambda d: d[1]["keys"].update(original=d[2]["keys"]["original"])),
    ("a key outside the photo prefix", lambda d: d[1]["keys"].update(display="runs/x/manifest.jsonl")),
    ("a key that is not one of the three roles", lambda d: d[1]["keys"].update(thumbnail=d[1]["keys"]["thumbnail"].replace("thumb.jpg", "other.jpg"))),
    ("an escaping key", lambda d: d[1]["keys"].update(original=d[1]["keys"]["original"].replace("original", "../original"))),
    ("a bad sha256", lambda d: d[1].update(sha256="xyz")),
    ("a non-canonical uuid", lambda d: d[1].update(asset_id=d[1]["asset_id"].upper())),
    ("a zero size", lambda d: d[1]["sizes"].update(display=0)),
    ("an extra role", lambda d: d[1]["keys"].update(extra="photos/v1/x/y")),
    ("a wrong kind", lambda d: d[1].update(kind="ROOM")),
    ("a count that does not match", lambda d: d[0].update(count=5)),
    ("a duplicate asset", lambda d: d.append(dict(d[1], id=str(uuid.uuid4())))),
    ("a wrong format name", lambda d: d[0].update(format="other/v1")),
])
def test_a_wrong_line_is_refused_because_it_would_delete_the_wrong_object(name, change):
    data = broken(World(2), change)
    if name == "a duplicate asset":
        data = rebuilt([*lines(data)[:-1], lines(data)[-1]])
        documents = lines(data)
        documents[0]["count"] = len(documents) - 1
        data = rebuilt(documents)
    with pytest.raises(pl.PurgeLedgerError):
        pl.parse_ledger(data)


@pytest.mark.parametrize("data", [b"", b"\n", b"not json\n", b"[]\n", "ł".encode() + b"\n"])
def test_something_that_is_not_a_ledger_is_refused(data):
    with pytest.raises(pl.PurgeLedgerError):
        pl.parse_ledger(data)


def test_the_report_of_the_cleaning_round_trips_and_is_strict():
    ids = [uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)]
    data = serialize_report(
        [ReportEntry(ids[0], "deleted", 2), ReportEntry(ids[1], "already_absent", 0), ReportEntry(ids[2], "failed", 1)], bucket_kind="prod", finished_at=NOW
    )
    report = parse_report(data)
    assert report.bucket_kind == "prod" and [e.clean for e in report.entries] == [True, True, False]
    for bad in (data.replace(b'"deleted"', b'"erased"'), data.replace(b'"prod"', b'"live"'), data + b'{"asset_id":"x"}\n', b"{}\n"):
        with pytest.raises(pl.PurgeLedgerError):
            parse_report(bad)


# --- verify -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(vf.VerifyMode))
async def test_a_purged_object_that_is_gone_from_the_backup_is_expected_not_a_problem(scratch: Path, tmp_path: Path, mode):
    world = World(3)
    target = await published(world, scratch, tmp_path)
    purged = pl.parse_ledger(ledger_bytes(world, 1)).purged_keys
    for key in purged:
        del target.objects[key]
    without = await verify(target, scratch, mode=mode)
    assert not without.ok and len(without.object_problems) == 3  # without the ledger the cleaning looks like damage
    report = await verify(target, scratch, mode=mode, purged_keys=purged)
    assert report.ok and report.object_problems == () and report.counts.purged_absent == 3 and report.counts.purged_present == 0


async def test_a_purged_object_that_is_still_in_the_backup_is_checked_like_any_other(scratch: Path, tmp_path: Path):
    world = World(2)
    target = await published(world, scratch, tmp_path)
    purged = pl.parse_ledger(ledger_bytes(world, 0)).purged_keys
    report = await verify(target, scratch, purged_keys=purged)
    assert report.ok and report.counts.purged_present == 3 and report.counts.purged_absent == 0
    key = world.key_of(0, "display")
    target.objects[key] = target.objects[key][:-1]  # still present but damaged: the ledger does not excuse that
    damaged = await verify(target, scratch, purged_keys=purged)
    assert not damaged.ok and [p.code for p in damaged.object_problems] == [vf.ObjectProblemCode.SIZE_MISMATCH]


async def test_the_ledger_never_excuses_an_object_it_does_not_list(scratch: Path, tmp_path: Path):
    world = World(3)
    target = await published(world, scratch, tmp_path)
    del target.objects[world.key_of(0, "original")]  # damage, not a purge
    del target.objects[world.key_of(1, "original")]
    report = await verify(target, scratch, purged_keys=pl.parse_ledger(ledger_bytes(world, 1)).purged_keys)
    assert [(p.asset_id, p.code) for p in report.object_problems] == [(str(world.assets[0].asset_id), vf.ObjectProblemCode.MISSING_OBJECT)]
    assert report.counts.purged_absent == 1


async def test_the_counts_of_a_run_without_a_ledger_are_unchanged_but_for_two_zeros(scratch: Path, tmp_path: Path):
    target = await published(World(2), scratch, tmp_path)
    report = await verify(target, scratch)
    counts = report.counts.to_dict()
    assert counts["purged_absent"] == 0 and counts["purged_present"] == 0 and counts["objects_total"] == 6


# --- restore media ----------------------------------------------------------------------------------------------------------


async def test_a_purged_object_is_never_copied_back_whether_or_not_the_backup_still_has_it(tmp_path: Path, scratch: Path):
    rig = MediaRig(tmp_path, scratch, count=3)
    purged = pl.parse_ledger(ledger_bytes(rig.world, 1)).purged_keys
    await rig.seal()
    for key in list(purged)[:2]:
        del rig.backup.objects[key]  # two of its three objects are gone from the backup, one is still there
    report = await rig.restore(purged_keys=purged)
    assert report.ok and report.object_problems == () and report.counts.purged_skipped == 3 and report.counts.restored == 6
    assert not (set(stored(rig)) & purged)
    assert set(stored(rig)) == set(rig.world.contents) - purged
    assert_clean(rig)


async def test_a_missing_object_that_is_not_in_the_ledger_is_still_a_problem(tmp_path: Path, scratch: Path):
    rig = MediaRig(tmp_path, scratch, count=3)
    purged = pl.parse_ledger(ledger_bytes(rig.world, 1)).purged_keys
    await rig.seal()
    del rig.backup.objects[rig.world.key_of(0, "original")]
    report = await rig.restore(purged_keys=purged)
    assert not report.ok and [p.code for p in report.object_problems] == [rm.ObjectProblemCode.MISSING_BACKUP_OBJECT]


async def test_without_a_ledger_the_restore_is_exactly_what_it_was(tmp_path: Path, scratch: Path):
    rig = MediaRig(tmp_path, scratch, count=2)
    report = await rig.restore()
    assert report.ok and report.counts.purged_skipped == 0 and report.counts.restored == 6


# --- the replay on the restored database ----------------------------------------------------------------------------------------------


class ReplayConnection:
    """What asyncpg gives the replay: statements run in one transaction; the row counts are what the fake says."""

    def __init__(self, fail: bool = False) -> None:
        self.statements: list[tuple[str, tuple]] = []
        self.fail, self.committed, self.rolled_back, self.closed = fail, False, False, False

    def transaction(self):
        outer = self

        class Transaction:
            async def __aenter__(self):
                return None

            async def __aexit__(self, exc_type, exc, tb):
                outer.committed, outer.rolled_back = exc_type is None, exc_type is not None
                return False

        return Transaction()

    async def execute(self, sql: str, *args: Any) -> str:
        if self.fail:
            raise OSError("connection reset")
        self.statements.append((sql, args))
        return {"DELETE FROM photo_annotations": "DELETE 2", "DELETE FROM photo_attachments": "DELETE 3", "DELETE FROM photo_assets": "DELETE 2"}.get(
            next((p for p in ("DELETE FROM photo_annotations", "DELETE FROM photo_attachments", "DELETE FROM photo_assets") if sql.startswith(p)), ""), "INSERT 0 1"
        )

    async def close(self) -> None:
        self.closed = True

    def terminate(self) -> None:
        self.closed = True


def connect_to(conn: ReplayConnection):
    async def connect(dsn: str, **kwargs: Any) -> ReplayConnection:
        return conn

    return connect


async def test_the_replay_removes_exactly_the_ledger_assets_and_records_the_deletions(tmp_path: Path):
    world = World(3)
    ledger = pl.parse_ledger(ledger_bytes(world, 0, 2))
    conn = ReplayConnection()
    report = await pr.replay_purge(Chain(tmp_path).rig.database, ledger, connect=connect_to(conn))
    assert (report.ledger_entries, report.assets_removed, report.attachments_removed, report.annotations_removed, report.ledger_rows_added) == (2, 2, 3, 2, 2)
    deletes = [s for s in conn.statements if s[0].startswith("DELETE")]
    assert [d[0].split()[2] for d in deletes] == ["photo_annotations", "photo_attachments", "photo_assets"]  # leaves first
    assert all(d[1] == (sorted(ledger.asset_ids),) for d in deletes)  # only the ledger's assets
    inserts = [s for s in conn.statements if s[0].startswith("INSERT")]
    assert len(inserts) == 2 and all("ON CONFLICT DO NOTHING" in s[0] for s in inserts)
    assert conn.committed and conn.closed and not conn.rolled_back


async def test_a_database_that_cannot_be_changed_stays_as_it_was(tmp_path: Path):
    conn = ReplayConnection(fail=True)
    with pytest.raises(pr.PurgeReplayError):
        await pr.replay_purge(Chain(tmp_path).rig.database, pl.parse_ledger(ledger_bytes(World(2), 0)), connect=connect_to(conn))
    assert conn.rolled_back and conn.closed and not conn.committed


# --- the whole chain ----------------------------------------------------------------------------------------------------------


def chain_connect(chain: Chain, replay: ReplayConnection):
    original = chain.rig.connect

    async def connect(dsn: str, **kwargs: Any) -> Any:
        if len(chain.rig.connects) >= 3:  # preflight, checks and the READY set read back have been made: this is the replay
            return replay
        return await original(dsn, **kwargs)

    return connect


async def test_the_chain_with_a_ledger_skips_the_purged_objects_and_replays_after_the_media_step(tmp_path: Path):
    chain = Chain(tmp_path)
    ledger = pl.parse_ledger(ledger_bytes(chain.rig.world, 0))
    await chain.rig.seal()
    for key in ledger.purged_keys:
        del chain.rig.target.objects[key]  # the owner's cleaning already removed them from the backup
    replay = ReplayConnection()
    report = await chain.restore(connect=chain_connect(chain, replay), purge_ledger=ledger)
    assert report.ok and report.step is rr.RunStep.DONE and report.failure is None
    assert report.media is not None and report.media.counts.purged_skipped == 3 and report.media.counts.restored == 3
    assert report.replay is not None and report.replay.assets_removed == 2 and replay.committed
    assert set(chain.destination.inner._objects) == set(chain.rig.world.contents) - ledger.purged_keys
    document = json.loads(report.report_bytes())
    assert document["replay"]["ledger_entries"] == 1 and document["media"]["counts"]["purged_skipped"] == 3
    text = report.report_bytes().decode()
    assert "photos/v1" not in text and SHA not in text


async def test_without_a_ledger_there_is_no_replay_and_the_chain_is_as_it_was(tmp_path: Path):
    chain = Chain(tmp_path)
    report = await chain.restore()
    assert report.ok and report.replay is None and json.loads(report.report_bytes())["replay"] is None


async def test_a_replay_that_fails_is_a_failed_restore_and_says_so(tmp_path: Path):
    chain = Chain(tmp_path)
    ledger = pl.parse_ledger(ledger_bytes(chain.rig.world, 0))
    report = await chain.restore(connect=chain_connect(chain, ReplayConnection(fail=True)), purge_ledger=ledger)
    assert not report.ok and (report.step, report.failure) == (rr.RunStep.REPLAY, rr.ChainFailure.REPLAY_FAILED)
    assert report.media is not None and report.media.ok  # the media step had succeeded; only the replay failed


async def test_a_failed_media_step_never_reaches_the_replay(tmp_path: Path):
    chain = Chain(tmp_path)
    ledger = pl.parse_ledger(ledger_bytes(chain.rig.world, 0))
    await chain.rig.seal()
    del chain.rig.target.objects[chain.rig.world.key_of(1, "display")]  # damage that is not a purge
    replay = ReplayConnection()
    report = await chain.restore(connect=chain_connect(chain, replay), purge_ledger=ledger)
    assert not report.ok and report.step is rr.RunStep.MEDIA and report.replay is None and replay.statements == []
