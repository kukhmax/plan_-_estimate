"""Stage 14D.2J.1 — the READY-assets and recipients sidecars written by `db-dump`."""

import hashlib
import os
import stat
import uuid

import pytest

from app.backup import run_sidecars as sc
from app.backup import workspace as ws
from app.backup.evidence import ErrorCode, FailureStage
from app.backup.orchestrator import BackupRunFailed
from app.domain.services.media_backup_ready_set import (
    READY_SET_HEADER,
    ReadyAsset,
    ready_set_digest,
)
from tests.test_stage14d2d3_orchestrator import (
    DUMP,
    READY_ASSETS,
    RECIPIENT,
    Harness,
    failure_doc,
    make,
    root,  # noqa: F401 - fixture
)

OTHER_RECIPIENT = "age1" + "p" * 58


def asset(n: int) -> ReadyAsset:
    return ReadyAsset(uuid.UUID(int=n), f"photos/v1/{n}/o.jpg", f"photos/v1/{n}/d.jpg", f"photos/v1/{n}/t.jpg", 9, 8, 7, f"{n:064x}")


# --- READY set sidecar -----------------------------------------------------------------------------------------


def test_ready_assets_round_trip_and_the_digest_is_preserved():
    assets = tuple(asset(n) for n in (3, 1, 2))
    data = sc.ready_assets_bytes(assets)
    parsed = sc.parse_ready_assets(data)
    assert set(parsed) == set(assets)
    assert ready_set_digest(parsed) == ready_set_digest(assets)
    assert hashlib.sha256(data).hexdigest() == ready_set_digest(assets).ready_set_sha256


def test_the_empty_set_is_the_header_alone():
    assert sc.ready_assets_bytes([]) == READY_SET_HEADER
    assert sc.parse_ready_assets(READY_SET_HEADER) == ()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d[1:],  # header damaged
        lambda d: d + b"\n",  # extra blank line
        lambda d: d.replace(b"\n", b"\r\n"),
        lambda d: d.rstrip(b"\n"),  # no final newline
        lambda d: d + d.splitlines(keepends=True)[-1],  # duplicate line
        lambda d: d.replace(b"|9|", b"|09|", 1),  # padded size
        lambda d: d.replace(b"|9|", b"|9 |", 1),
        lambda d: d.replace(b"photos", "fotó".encode(), 1),  # non-ASCII
        lambda d: d.replace(b"|", b"||", 1),  # wrong field count
        lambda d: d.replace(b"0" * 63 + b"1", b"G" * 64, 1),  # bad sha256
    ],
)
def test_a_malformed_ready_file_is_refused(mutate):
    data = sc.ready_assets_bytes([asset(1), asset(2)])
    with pytest.raises(sc.SidecarError):
        sc.parse_ready_assets(mutate(data))


def test_lines_out_of_canonical_order_are_refused():
    lines = sc.ready_assets_bytes([asset(1), asset(2)])[len(READY_SET_HEADER):].splitlines(keepends=True)
    with pytest.raises(sc.SidecarError, match="not canonical"):
        sc.parse_ready_assets(READY_SET_HEADER + lines[1] + lines[0])


def test_errors_never_contain_file_content():
    secret = b"SECRETVALUE"
    with pytest.raises(sc.SidecarError) as excinfo:
        sc.parse_ready_assets(READY_SET_HEADER + secret + b"|x\n")
    assert "SECRETVALUE" not in str(excinfo.value)


# --- recipients sidecar -----------------------------------------------------------------------------------------


def test_recipients_round_trip_in_order():
    data = sc.recipients_bytes([RECIPIENT, OTHER_RECIPIENT])
    assert data == f"{RECIPIENT}\n{OTHER_RECIPIENT}\n".encode()
    assert sc.parse_recipients(data) == (RECIPIENT, OTHER_RECIPIENT)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\n",
        f"{RECIPIENT}".encode(),  # no newline
        f"{RECIPIENT}\n{RECIPIENT}\n".encode(),  # duplicate
        f"{RECIPIENT}\n\n".encode(),
        f"{RECIPIENT}, {OTHER_RECIPIENT}\n".encode(),
        b"AGE-SECRET-KEY-1" + b"Q" * 58 + b"\n",
        b"ssh-ed25519 AAAA\n",
        b"not-a-recipient\n",
        f"{RECIPIENT}\r\n".encode(),
    ],
)
def test_malformed_recipients_are_refused(data):
    with pytest.raises(sc.SidecarError):
        sc.parse_recipients(data)


# --- data root writer ----------------------------------------------------------------------------------------------


def test_run_files_are_private_exclusive_and_limited_to_the_fixed_names(tmp_path):
    root_dir = tmp_path / "data"
    root_dir.mkdir(mode=0o700)
    data_root = ws.BackupDataRoot(root_dir)
    data_root.prepare()
    run = data_root.create_run("20261004T100000Z-0123abcd")
    path = data_root.write_run_file(run.run_id, sc.READY_ASSETS_NAME, b"x")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and path.read_bytes() == b"x"
    with pytest.raises(ws.EvidenceWriteError, match="already exists"):
        data_root.write_run_file(run.run_id, sc.READY_ASSETS_NAME, b"y")
    assert path.read_bytes() == b"x"
    for bad in ("local-run.json", "../x", "other.txt", ""):
        with pytest.raises(ws.EvidenceWriteError):
            data_root.write_run_file(run.run_id, bad, b"z")
    assert sc.SIDECAR_NAMES == ws.RUN_SIDECAR_NAMES


def test_a_symlink_in_place_of_a_sidecar_is_not_followed(tmp_path):
    root_dir = tmp_path / "data"
    root_dir.mkdir(mode=0o700)
    data_root = ws.BackupDataRoot(root_dir)
    data_root.prepare()
    run = data_root.create_run("20261004T100000Z-0123abcd")
    victim = tmp_path / "victim"
    victim.write_text("keep")
    os.symlink(victim, run.directory / sc.RECIPIENTS_NAME)
    with pytest.raises(ws.EvidenceWriteError):
        data_root.write_run_file(run.run_id, sc.RECIPIENTS_NAME, b"overwritten")
    assert victim.read_text() == "keep"


# --- orchestrator -----------------------------------------------------------------------------------------------------


async def test_a_successful_run_leaves_both_sidecars_bound_to_the_evidence(root, tmp_path):  # noqa: F811
    h = Harness(root)
    result = await make(root, tmp_path, h).run()
    run_dir = root / "encrypted" / result.run_id
    ready_file = (run_dir / sc.READY_ASSETS_NAME).read_bytes()
    assert hashlib.sha256(ready_file).hexdigest() == result.evidence.snapshot.ready_set_sha256
    assert set(sc.parse_ready_assets(ready_file)) == set(READY_ASSETS)
    recipients = sc.parse_recipients((run_dir / sc.RECIPIENTS_NAME).read_bytes())
    assert recipients == (RECIPIENT,) and len(recipients) == result.evidence.artifact.recipient_count
    for name in sc.SIDECAR_NAMES:
        assert stat.S_IMODE((run_dir / name).stat().st_mode) == 0o600


async def test_assets_that_do_not_match_the_snapshot_digest_stop_the_run_before_evidence(root, tmp_path):  # noqa: F811
    h = Harness(root)
    original = h.snapshot_dump

    async def tampered(*args, **kwargs):
        result = await original(*args, **kwargs)
        return type(result)(**{**result.__dict__, "ready_assets": READY_ASSETS[:-1]})

    with pytest.raises(BackupRunFailed) as exc:
        await make(root, tmp_path, h, snapshot_dump=tampered).run()
    assert exc.value.code is ErrorCode.SNAPSHOT_METADATA_INVALID and exc.value.stage is FailureStage.EVIDENCE
    assert list((root / "encrypted").iterdir()) == []
    run_dir = root / "work" / exc.value.run_id
    assert not (run_dir / "local-run.json").exists() and not (run_dir / sc.READY_ASSETS_NAME).exists()
    assert failure_doc(root)["failure"]["error_code"] == "SNAPSHOT_METADATA_INVALID"
    assert DUMP  # the harness dump was real input
