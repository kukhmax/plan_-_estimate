"""Stage 14D.2E — backup manifest v1, COMPLETE.json and SHA-256 provenance (pure)."""

import dataclasses
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.backup import manifest as mf
from app.backup.evidence import canonical_json
from app.backup.evidence import format_timestamp as evidence_format_timestamp
from app.backup.run_id import RunIdError
from app.core.db_dump_encryption import (
    ENCRYPTED_DUMP_NAME,
    AgeRecipientError,
    parse_age_recipients,
)
from app.domain.services.media_backup_ready_set import ReadyAsset, ready_set_digest

RUN = "20261004T120000Z-0123abcd"
PRIOR = "20261003T120000Z-89abcdef"
EARLIER = "20261002T120000Z-aaaaaaaa"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
T_START, T_VERIFIED, T_DONE = "2026-10-04T12:00:00Z", "2026-10-04T12:05:00Z", "2026-10-04T12:10:00Z"
RECIPIENT_A, RECIPIENT_B = "age1" + "q" * 58, "age1" + "p" * 58


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def asset_id(index: int) -> uuid.UUID:
    return uuid.UUID(bytes=hashlib.sha256(f"asset-{index}".encode()).digest()[:16], version=4)


def make_asset(index: int, extension: str = "jpg") -> tuple[ReadyAsset, list[mf.ManifestObject]]:
    aid = asset_id(index)
    base = f"photos/v1/{aid}/"
    original_type = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[extension]
    sizes = (1000 + index, 200 + index, 30 + index)
    ready = ReadyAsset(
        aid, f"{base}original.{extension}", f"{base}display.jpg", f"{base}thumb.jpg", *sizes, sha(f"orig-{index}")
    )
    specs = (
        (mf.Role.ORIGINAL, ready.key_original, sizes[0], sha(f"orig-{index}"), original_type),
        (mf.Role.DISPLAY, ready.key_display, sizes[1], sha(f"disp-{index}"), "image/jpeg"),
        (mf.Role.THUMBNAIL, ready.key_thumbnail, sizes[2], sha(f"thumb-{index}"), "image/jpeg"),
    )
    objects = [
        mf.ManifestObject(
            asset_id=str(aid),
            role=role,
            key=key,
            size=size,
            sha256=digest,
            content_type=content_type,
            action=mf.Action.COPIED,
            sha_provenance=mf.DOWNLOADED,
            verified_at=T_VERIFIED,
            target_etag=f'"etag-{index}"' if role is mf.Role.ORIGINAL else None,
        )
        for role, key, size, digest, content_type in specs
    ]
    return ready, objects


def make_header(readies: list[ReadyAsset], run_id: str = RUN) -> mf.ManifestHeader:
    digest = ready_set_digest(readies)
    return mf.ManifestHeader(
        run_id=run_id,
        started_at=T_START,
        tool_commit=COMMIT,
        source=mf.SourceInfo("r2-primary", "plan-estimate-media-prod"),
        target=mf.TargetInfo("plan-estimate-backup-prod"),
        db_dump=mf.DbDumpInfo(
            key=mf.db_dump_key(run_id),
            recipients=(RECIPIENT_A, RECIPIENT_B),
            encrypted_sha256=sha("dump"),
            encrypted_size=123456,
            alembic_head="0032_photo_attachments",
            dumped_at=T_START,
        ),
        snapshot=mf.SnapshotInfo(digest.ready_count, digest.ready_set_sha256),
    )


def make_manifest(count: int = 2, run_id: str = RUN, **extra: Any) -> tuple[mf.Manifest, list[ReadyAsset]]:
    readies, objects = [], []
    for index in range(count):
        ready, objs = make_asset(index, ("jpg", "png", "webp")[index % 3])
        readies.append(ready)
        objects.extend(objs)
    manifest = mf.build_manifest(
        make_header(readies, run_id), objects, source_keys=extra.pop("source_keys", 3 * count), orphan_candidates=0, **extra
    )
    return manifest, readies


def docs_of(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.decode().splitlines()]


def join(docs: list[dict[str, Any]]) -> bytes:
    return b"".join(mf.canonical_line(doc) for doc in docs)


# --- happy path, determinism, golden ------------------------------------------------------


def test_manifest_round_trips_through_canonical_bytes():
    manifest, _ = make_manifest(3)
    data = manifest.to_bytes()
    assert mf.parse_manifest(data) == manifest
    assert mf.parse_manifest(data).to_bytes() == data
    assert manifest.sha256 == hashlib.sha256(data).hexdigest()
    assert len(data.splitlines()) == 1 + 9 + 1
    assert manifest.summary.objects == 9 and manifest.summary.ready_assets == 3


def test_object_order_in_input_does_not_change_the_bytes():
    readies, objects = [], []
    for index in range(3):
        ready, objs = make_asset(index)
        readies.append(ready)
        objects.extend(objs)
    forward = mf.build_manifest(make_header(readies), objects, source_keys=9, orphan_candidates=0)
    backward = mf.build_manifest(make_header(readies), reversed(objects), source_keys=9, orphan_candidates=0)
    assert forward.to_bytes() == backward.to_bytes()


def test_golden_manifest_and_complete_digests_pin_the_v1_format():
    manifest, _ = make_manifest(2)
    complete = mf.build_complete(manifest, datetime(2026, 10, 4, 12, 10, tzinfo=UTC))
    assert manifest.sha256 == "9d84e8e38587cd85b1a0db9dd0b922be3eca15d2cf87b85fecefce037fc3d882"
    assert hashlib.sha256(complete.to_bytes()).hexdigest() == "f30b507ca52aa9db911311528b45b5f2bffceb5e231f38ac60c3a57f86acbc5a"


def test_empty_ready_set_is_a_valid_manifest_with_the_fixed_digest():
    manifest, _ = make_manifest(0)
    assert manifest.summary == mf.ManifestSummary(0, 0, 0, 0, 0, 0, 0)
    assert manifest.header.snapshot.ready_set_sha256 == hashlib.sha256(b"plan-estimate/ready-set/v1\n").hexdigest()
    assert len(manifest.to_bytes().splitlines()) == 2
    assert mf.parse_manifest(manifest.to_bytes()) == manifest


def test_skipped_counts_and_source_listing_are_carried():
    manifest, _ = make_manifest(1, skipped_pending=2, skipped_failed=1, source_keys=50)
    reparsed = mf.parse_manifest(manifest.to_bytes())
    assert (reparsed.summary.skipped_pending, reparsed.summary.skipped_failed, reparsed.summary.source_keys) == (2, 1, 50)


# --- canonical form -------------------------------------------------------------------------


def _pretty(data: bytes) -> bytes:
    return b"".join((json.dumps(doc, sort_keys=True) + "\n").encode() for doc in docs_of(data))


@pytest.mark.parametrize(
    "mutate",
    [
        _pretty,  # spaces after separators
        lambda d: d.replace(b"\n", b"\r\n"),
        lambda d: d[:-1],  # no trailing newline
        lambda d: d + b"\n",  # blank line at the end
        lambda d: d.replace(b'"tool_commit"', b'"tool_commit "'),
        lambda d: d.replace(b"r2-primary", "r2-primärary".encode()),
        lambda d: d.replace(b'"size":1000', b'"size":1000.0'),
        lambda d: d.replace(b'"size":1000', b'"size":NaN'),
        lambda d: d.replace(b'"size":1000', b'"size":true'),
        lambda d: d.replace(b'"size":1000', b'"size":"1000"'),
        lambda d: d.replace(b'{"action":"copied",', b'{"action":"copied","action":"copied",', 1),  # duplicate field
    ],
)
def test_only_the_exact_canonical_bytes_are_accepted(mutate):
    manifest, _ = make_manifest(1)
    mutated = mutate(manifest.to_bytes())
    assert mutated != manifest.to_bytes(), "the mutation must change the bytes"
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_manifest(mutated)


@pytest.mark.parametrize("bad", [None, "text", 5, [b"x"]])
def test_non_bytes_input_is_refused(bad):
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_manifest(bad)
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_complete(bad)


def test_unknown_missing_and_misplaced_fields_are_refused():
    manifest, _ = make_manifest(1)
    base = docs_of(manifest.to_bytes())
    cases: list[list[dict[str, Any]]] = []
    for line, mutate in (
        (0, lambda d: d.update(extra=1)),
        (0, lambda d: d.pop("snapshot")),
        (0, lambda d: d["source"].update(region="x")),
        (0, lambda d: d["db_dump"].pop("alembic_head")),
        (1, lambda d: d.update(filename="IMG_1.jpg")),
        (1, lambda d: d.pop("target_etag")),
        (-1, lambda d: d["skipped"].update(unknown=0)),
        (-1, lambda d: d.pop("source_listing")),
    ):
        docs = json.loads(json.dumps(base))
        mutate(docs[line])
        cases.append(docs)
    for docs in cases:
        with pytest.raises(mf.ManifestFormatError):
            mf.parse_manifest(join(docs))


def test_line_structure_is_enforced():
    manifest, _ = make_manifest(1)
    docs = docs_of(manifest.to_bytes())
    header, objects, summary = docs[0], docs[1:-1], docs[-1]
    for broken in (
        [*objects, header, summary],  # header not first
        [header, *objects],  # no summary
        [header, summary, *objects],  # summary not last
        [header, *objects, header, summary],  # second header
        [header, *objects, summary, summary],  # second summary
        [summary],
        [],
    ):
        with pytest.raises(mf.ManifestFormatError):
            mf.parse_manifest(join(broken))
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_manifest(b"\n")
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_manifest(b'{"type":"header"}\n' + b" " * 5000 + b"\n")
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_manifest(b"not json\n{}\n")
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_manifest(b"[1]\n[2]\n")


# --- header validation -----------------------------------------------------------------------


def _header_kwargs() -> dict[str, Any]:
    header = make_header([])
    return {
        "run_id": header.run_id,
        "started_at": header.started_at,
        "tool_commit": header.tool_commit,
        "source": header.source,
        "target": header.target,
        "db_dump": header.db_dump,
        "snapshot": header.snapshot,
    }


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"run_id": "2026-10-04"}, mf.ManifestFormatError),
        ({"started_at": "2026-10-04T12:00:00"}, mf.ManifestFormatError),
        ({"started_at": "2026-02-30T12:00:00Z"}, mf.ManifestFormatError),
        ({"tool_commit": "ABCDEF"}, mf.ManifestFormatError),
        ({"tool_commit": "g" * 40}, mf.ManifestFormatError),
        ({"manifest_version": 2}, mf.ManifestFormatError),
        ({"manifest_version": True}, mf.ManifestFormatError),
        ({"target": mf.TargetInfo("plan-estimate-media-prod")}, mf.ManifestInvariantError),
        ({"run_id": PRIOR}, mf.ManifestInvariantError),  # db_dump.key was built for RUN
    ],
)
def test_header_rejects_invalid_values(override, error):
    with pytest.raises(error):
        mf.ManifestHeader(**(_header_kwargs() | override))


@pytest.mark.parametrize(
    "override",
    [
        {"encryption": "none"},
        {"recipients": ()},
        {"recipients": ("AGE-SECRET-KEY-1" + "Q" * 58,)},
        {"recipients": ("ssh-ed25519 AAAA",)},
        {"recipients": (RECIPIENT_A, RECIPIENT_A)},
        {"recipients": ("age1" + "q" * 57,)},
        {"recipients": ("age1" + "Q" * 58,)},
        {"recipients": ["age1" + "q" * 58]},  # list, not tuple
        {"recipients": tuple(f"age1{'q' * 57}{c}" for c in "qpzry9x8gf2tvdw0s3jn54khce6mua7l") + (RECIPIENT_B,)},
        {"encrypted_sha256": "A" * 64},
        {"encrypted_size": 0},
        {"alembic_head": "0032 photo"},
        {"dumped_at": "yesterday"},
    ],
)
def test_db_dump_info_rejects_invalid_values(override):
    base = dataclasses.asdict(make_header([]).db_dump) | {"recipients": (RECIPIENT_A,)}
    with pytest.raises(mf.ManifestFormatError):
        mf.DbDumpInfo(**(base | override))


@pytest.mark.parametrize(
    ("factory", "args"),
    [
        (mf.SourceInfo, ("r2 primary", "bucket-a")),
        (mf.SourceInfo, ("r2-primary", "Bucket_A")),
        (mf.SourceInfo, ("r2-primary", "a")),
        (mf.TargetInfo, ("-bucket",)),
        (mf.SnapshotInfo, (-1, "0" * 64)),
        (mf.SnapshotInfo, (True, "0" * 64)),
        (mf.SnapshotInfo, (0, "G" * 64)),
    ],
)
def test_small_header_parts_reject_invalid_values(factory, args):
    with pytest.raises(mf.ManifestFormatError):
        factory(*args)


def test_snapshot_method_and_recipient_limit():
    with pytest.raises(mf.ManifestFormatError):
        mf.SnapshotInfo(0, "0" * 64, method="live-read")
    recipients = tuple("age1" + "q" * 57 + c for c in "qpzry9x8gf2tvdw0s3jn54khce6mua7l")
    assert len(recipients) == 32
    base = dataclasses.asdict(make_header([]).db_dump)
    assert mf.DbDumpInfo(**(base | {"recipients": recipients})).recipients == recipients
    with pytest.raises(mf.ManifestFormatError):
        mf.DbDumpInfo(**(base | {"recipients": (*recipients, RECIPIENT_B)}))


# --- object-line validation ------------------------------------------------------------------


def _object_kwargs(role: mf.Role = mf.Role.ORIGINAL) -> dict[str, Any]:
    obj = next(o for o in make_asset(0)[1] if o.role is role)
    return dataclasses.asdict(obj)


@pytest.mark.parametrize(
    "override",
    [
        {"asset_id": "NOT-A-UUID"},
        {"asset_id": str(uuid.UUID(int=1))},  # not version 4
        {"asset_id": str(asset_id(0)).upper()},
        {"key": f"photos/v1/{asset_id(1)}/original.jpg"},  # another asset's key
        {"key": f"photos/v1/{asset_id(0)}/original.gif"},
        {"key": f"photos/v1/{asset_id(0)}/display.jpg"},  # key of another role
        {"key": f"other/{asset_id(0)}/original.jpg"},
        {"content_type": "image/png"},  # key says jpg
        {"content_type": "application/octet-stream"},
        {"size": 0},
        {"size": -5},
        {"size": True},
        {"size": 1.5},
        {"size": 2**53},
        {"sha256": "A" * 64},
        {"sha256": "a" * 63},
        {"verified_at": "2026-10-04T12:05:00.123Z"},
        {"verified_at": "2026-10-04T12:05:00+02:00"},
        {"target_etag": "has space"},
        {"target_etag": ""},
        {"target_etag": 5},
        {"sha_provenance": "inherited:not-a-run"},
        {"sha_provenance": "trusted"},
        {"sha_provenance": None},
        {"sha_provenance": f"inherited:{PRIOR}", "action": mf.Action.COPIED},  # a fresh copy is always downloaded
        {"role": "original-ish"},
        {"action": "moved"},
    ],
)
def test_object_line_rejects_invalid_values(override):
    with pytest.raises(mf.ManifestFormatError):
        mf.ManifestObject(**(_object_kwargs() | override))


@pytest.mark.parametrize(
    ("role", "override"),
    [
        (mf.Role.DISPLAY, {"content_type": "image/png"}),
        (mf.Role.DISPLAY, {"key": f"photos/v1/{asset_id(0)}/display.png"}),
        (mf.Role.THUMBNAIL, {"key": f"photos/v1/{asset_id(0)}/thumbnail.jpg"}),
        (mf.Role.THUMBNAIL, {"content_type": "image/webp"}),
    ],
)
def test_derivative_lines_are_pinned_to_their_fixed_key_and_type(role, override):
    with pytest.raises(mf.ManifestFormatError):
        mf.ManifestObject(**(_object_kwargs(role) | override))


def test_already_present_objects_may_inherit_provenance():
    obj = mf.ManifestObject(
        **(_object_kwargs() | {"action": mf.Action.ALREADY_PRESENT, "sha_provenance": mf.inherited_provenance(PRIOR)})
    )
    assert mf.inherited_run_id(obj.sha_provenance) == PRIOR
    assert mf.inherited_run_id(mf.DOWNLOADED) is None


# --- cross-line invariants (plan §7) ------------------------------------------------------------


def _line(docs: list[dict[str, Any]], role: str) -> dict[str, Any]:
    """The first object line with this role (lines are sorted by key, not by role)."""
    return next(doc for doc in docs if doc.get("role") == role)


def _rewrite(manifest: mf.Manifest, mutate) -> bytes:
    docs = docs_of(manifest.to_bytes())
    mutate(docs)
    return join(docs)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop(1),  # an asset with two lines
        lambda d: d.insert(2, dict(d[1])),  # duplicate key
        lambda d: d.insert(1, d.pop(2)),  # unsorted
        lambda d: _line(d, "original").update(sha256="b" * 64),  # original SHA differs -> READY-set digest
        lambda d: _line(d, "original").update(size=_line(d, "original")["size"] + 1),
        lambda d: _line(d, "display").update(size=_line(d, "display")["size"] + 1),
        lambda d: _line(d, "thumbnail").update(size=_line(d, "thumbnail")["size"] + 1),
        lambda d: d[-1].update(objects=d[-1]["objects"] + 1),
        lambda d: d[-1].update(bytes=d[-1]["bytes"] + 1),
        lambda d: d[-1].update(ready_assets=d[-1]["ready_assets"] + 1),
        lambda d: d[0]["snapshot"].update(ready_count=d[0]["snapshot"]["ready_count"] + 1),
        lambda d: d[0]["snapshot"].update(ready_set_sha256="c" * 64),
        lambda d: d[1].update(verified_at="2026-10-04T11:59:59Z"),  # before the run started
        lambda d: d[1].update(action="already_present", sha_provenance=f"inherited:{RUN}"),  # not earlier
        lambda d: d[1].update(action="already_present", sha_provenance="inherited:20261005T000000Z-aaaaaaaa"),
        lambda d: d[0]["target"].update(bucket=d[0]["source"]["bucket"]),
        lambda d: d[0]["db_dump"].update(key=f"db/{PRIOR}/plan-estimate.sql.gz.age"),
    ],
)
def test_completeness_invariants_reject_inconsistent_manifests(mutate):
    manifest, _ = make_manifest(2)
    with pytest.raises(mf.ManifestInvariantError):  # the invariant, not a format error, must be the reason
        mf.parse_manifest(_rewrite(manifest, mutate))


def test_a_changed_derivative_sha_is_detected_by_the_seal_not_by_internal_consistency():
    """The READY-set digest (and the database) carry the original's SHA-256 only; the
    derivatives' SHA-256 values are protected by COMPLETE.json's manifest hash and
    re-checked against the restored objects (plan §8, §10)."""
    manifest, complete = _sealed(2)
    tampered = _rewrite(manifest, lambda d: _line(d, "display").update(sha256="b" * 64))
    forged = mf.parse_manifest(tampered)  # internally consistent
    assert forged.sha256 != manifest.sha256
    with pytest.raises(mf.CompleteMismatchError, match="SHA-256"):
        mf.verify_run(complete.to_bytes(), tampered)


def test_an_extra_asset_line_set_breaks_the_snapshot_digest():
    manifest, _ = make_manifest(2)
    extra = [o.to_dict() for o in make_asset(9)[1]]

    def add_asset(docs):
        docs[1:-1] = sorted([*docs[1:-1], *extra], key=lambda doc: doc["key"])

    with pytest.raises(mf.ManifestInvariantError, match="digest"):
        mf.parse_manifest(_rewrite(manifest, add_asset))


def test_a_second_original_for_one_asset_is_refused():
    manifest, _ = make_manifest(1)
    twin = dataclasses.replace(
        next(o for o in manifest.objects if o.role is mf.Role.ORIGINAL),
        key=f"photos/v1/{asset_id(0)}/original.png",
        content_type="image/png",
    )
    with pytest.raises(mf.ManifestInvariantError, match="same role"):
        mf.build_manifest(manifest.header, [*manifest.objects, twin], source_keys=0, orphan_candidates=0)


def test_inherited_provenance_must_name_an_earlier_run():
    ok = mf.ManifestObject(
        **(_object_kwargs() | {"action": mf.Action.ALREADY_PRESENT, "sha_provenance": mf.inherited_provenance(PRIOR)})
    )
    manifest, _ = make_manifest(1)
    objects = [ok, *[o for o in manifest.objects if o.role is not mf.Role.ORIGINAL]]
    rebuilt = mf.build_manifest(manifest.header, objects, source_keys=3, orphan_candidates=0)
    assert mf.parse_manifest(rebuilt.to_bytes()) == rebuilt


def test_errors_never_echo_values():
    secrets = "SECRETVALUE" + "x" * 5
    for factory in (
        lambda: mf.ManifestObject(**(_object_kwargs() | {"sha_provenance": f"inherited:{secrets}"})),
        lambda: mf.ManifestObject(**(_object_kwargs() | {"key": f"photos/v1/{secrets}"})),
        lambda: mf.ManifestObject(**(_object_kwargs() | {"sha256": secrets})),
        lambda: mf.DbDumpInfo(**(dataclasses.asdict(make_header([]).db_dump) | {"recipients": (secrets,)})),
        lambda: mf.parse_manifest(f'{{"type":"{secrets}"}}\n'.encode() * 2),
    ):
        with pytest.raises(mf.ManifestError) as caught:
            factory()
        assert secrets not in str(caught.value)


# --- READY-set verification -------------------------------------------------------------------


def test_manifest_matches_the_ready_set_it_was_built_from():
    manifest, readies = make_manifest(3)
    mf.verify_against_ready_set(manifest, readies)
    mf.verify_against_ready_set(manifest, reversed(readies))


def test_ready_set_differences_are_counted_without_values():
    manifest, readies = make_manifest(3)
    extra, _ = make_asset(7)
    changed = dataclasses.replace(readies[0], sha256="d" * 64)
    resized = dataclasses.replace(readies[1], display_byte_size=readies[1].display_byte_size + 1)
    cases = {
        "not_in_manifest=0, not_in_ready_set=1, changed=0": readies[:2],
        "not_in_manifest=1, not_in_ready_set=0, changed=0": [*readies, extra],
        "not_in_manifest=0, not_in_ready_set=0, changed=1": [changed, *readies[1:]],
        "not_in_manifest=0, not_in_ready_set=0, changed=2": [changed, resized, readies[2]],
        "not_in_manifest=0, not_in_ready_set=3, changed=0": [],
    }
    for expected, ready_set in cases.items():
        with pytest.raises(mf.ManifestInvariantError, match=expected) as caught:
            mf.verify_against_ready_set(manifest, ready_set)
        assert str(readies[0].asset_id) not in str(caught.value) and readies[0].sha256 not in str(caught.value)


def test_manifest_derived_ready_set_reproduces_the_snapshot_digest():
    manifest, readies = make_manifest(4)
    digest = ready_set_digest(mf.ready_assets_from_objects(manifest.objects))
    assert digest == ready_set_digest(readies)
    assert digest.ready_set_sha256 == manifest.header.snapshot.ready_set_sha256


# --- COMPLETE.json ----------------------------------------------------------------------------


def _sealed(count: int = 2, run_id: str = RUN) -> tuple[mf.Manifest, mf.CompleteRecord]:
    manifest, _ = make_manifest(count, run_id=run_id)
    return manifest, mf.build_complete(manifest, datetime(2026, 10, 4, 12, 10, tzinfo=UTC))


def test_complete_seals_the_manifest_and_round_trips():
    manifest, complete = _sealed()
    assert complete.manifest_sha256 == manifest.sha256
    assert complete.manifest_key == f"runs/{RUN}/manifest.jsonl"
    assert (complete.objects, complete.ready_assets) == (6, 2)
    assert complete.total_bytes == manifest.summary.total_bytes
    assert complete.completed_at == T_DONE
    assert mf.parse_complete(complete.to_bytes()) == complete
    run = mf.verify_run(complete.to_bytes(), manifest.to_bytes())
    assert run.run_id == RUN and run.manifest == manifest and run.complete == complete


def test_complete_json_is_a_single_canonical_line_with_the_planned_fields():
    _, complete = _sealed()
    document = json.loads(complete.to_bytes())
    assert sorted(document) == sorted(
        [
            "run_id",
            "manifest_version",
            "manifest_key",
            "manifest_sha256",
            "objects",
            "bytes",
            "ready_assets",
            "ready_set_sha256",
            "db_dump_encrypted_sha256",
            "completed_at",
        ]
    )
    assert complete.to_bytes().count(b"\n") == 1 and complete.to_bytes().endswith(b"\n")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b[:-1],
        lambda b: b + b"\n",
        lambda b: b.replace(b",", b", "),
        lambda b: b.replace(b'"objects"', b'"objects "'),
        lambda b: b.replace(b'"bytes":', b'"extra":1,"bytes":'),
        lambda b: b.replace(b'"objects":6', b'"objects":6.0'),
        lambda b: b.replace(b'"manifest_version":1', b'"manifest_version":true'),
        lambda b: b.replace(b"\n", b"\r\n"),
        lambda b: b.replace(b'"run_id"', b'"run_id":"x","run_id"', 1),
        lambda b: "é".encode() + b,
        lambda b: b"x" * 5000 + b,
    ],
)
def test_complete_json_accepts_only_canonical_bytes(mutate):
    _, complete = _sealed()
    mutated = mutate(complete.to_bytes())
    assert mutated != complete.to_bytes(), "the mutation must change the bytes"
    with pytest.raises(mf.ManifestFormatError):
        mf.parse_complete(mutated)


def test_complete_does_not_seal_a_different_or_modified_manifest():
    manifest, complete = _sealed()
    other, _ = make_manifest(3)
    with pytest.raises(mf.CompleteMismatchError, match="SHA-256"):
        mf.verify_run(complete.to_bytes(), other.to_bytes())
    with pytest.raises(mf.CompleteMismatchError):
        mf.verify_run(complete.to_bytes(), manifest.to_bytes() + b" ")
    with pytest.raises(mf.CompleteMismatchError):
        mf.verify_run(complete.to_bytes(), manifest.to_bytes().replace(b"r2-primary", b"r2-primarz"))


@pytest.mark.parametrize(
    ("override", "named"),
    [
        ({"objects": 9}, "objects"),
        ({"total_bytes": 1}, "bytes"),
        ({"ready_assets": 3}, "ready_assets"),
        ({"ready_set_sha256": "e" * 64}, "ready_set_sha256"),
        ({"db_dump_encrypted_sha256": "f" * 64}, "db_dump_encrypted_sha256"),
        ({"completed_at": "2026-10-04T12:04:59Z"}, "predates"),
    ],
)
def test_every_complete_field_must_agree_with_the_manifest(override, named):
    manifest, complete = _sealed()
    forged = dataclasses.replace(complete, **override)
    with pytest.raises(mf.CompleteMismatchError, match=named):
        mf.verify_run(forged.to_bytes(), manifest.to_bytes())


def test_complete_with_another_run_id_is_refused():
    manifest, complete = _sealed()
    forged = dataclasses.replace(complete, run_id=PRIOR, manifest_key=mf.manifest_key(PRIOR))
    with pytest.raises(mf.CompleteMismatchError, match="run_id"):
        mf.verify_run(forged.to_bytes(), manifest.to_bytes())
    with pytest.raises(mf.ManifestFormatError):
        dataclasses.replace(complete, manifest_key=mf.manifest_key(PRIOR))


def test_build_complete_checks_time_and_timezone():
    manifest, _ = make_manifest(1)
    with pytest.raises(mf.ManifestInvariantError):
        mf.build_complete(manifest, datetime(2026, 10, 4, 12, 4, tzinfo=UTC))
    with pytest.raises(mf.ManifestFormatError):
        mf.build_complete(manifest, datetime(2026, 10, 4, 12, 10))  # noqa: DTZ001 - naive on purpose
    plus_two = timezone(timedelta(hours=2))
    assert mf.build_complete(manifest, datetime(2026, 10, 4, 14, 10, tzinfo=plus_two)).completed_at == T_DONE


# --- SHA-256 provenance (plan §8) -----------------------------------------------------------------


def _prior_run(count: int = 2) -> tuple[mf.VerifiedRun, list[mf.ManifestObject]]:
    manifest, complete = _sealed(count, run_id=PRIOR)
    return mf.verify_run(complete.to_bytes(), manifest.to_bytes()), list(manifest.objects)


def _decide(prior, obj: mf.ManifestObject, **override: Any) -> mf.ProvenanceDecision:
    args: dict[str, Any] = {
        "key": obj.key,
        "expected_size": obj.size,
        "expected_sha256": obj.sha256 if obj.role is mf.Role.ORIGINAL else None,
        "target_size": obj.size,
        "deep": False,
    }
    return mf.decide_provenance(prior, **(args | override))


def test_matching_prior_run_allows_inheritance():
    prior, objects = _prior_run()
    for obj in objects:
        decision = _decide(prior, obj)
        assert decision.kind is mf.ProvenanceKind.INHERIT and decision.reason is None
        assert decision.sha256 == obj.sha256 and decision.run_id == PRIOR
        assert decision.provenance == f"inherited:{PRIOR}"


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"deep": True}, mf.DownloadReason.DEEP),
        ({"key": "photos/v1/00000000-0000-4000-8000-000000000000/original.jpg"}, mf.DownloadReason.KEY_NOT_IN_PRIOR),
        ({"expected_size": 1}, mf.DownloadReason.SIZE_DIFFERS_FROM_PRIOR),
        ({"target_size": None}, mf.DownloadReason.TARGET_MISSING),
        ({"target_size": 1}, mf.DownloadReason.TARGET_SIZE_DIFFERS),
        ({"expected_sha256": "9" * 64}, mf.DownloadReason.SHA_DIFFERS_FROM_DB),
    ],
)
def test_any_unmet_condition_forces_a_download(override, reason):
    prior, objects = _prior_run()
    decision = _decide(prior, objects[0], **override)
    assert decision.kind is mf.ProvenanceKind.DOWNLOAD and decision.reason is reason
    assert decision.provenance == mf.DOWNLOADED and decision.run_id is None and decision.sha256 is None


def test_no_prior_run_means_download():
    _, objects = _prior_run()
    decision = _decide(None, objects[0])
    assert (decision.kind, decision.reason) == (mf.ProvenanceKind.DOWNLOAD, mf.DownloadReason.NO_PRIOR_RUN)


def test_derivatives_have_no_database_sha_to_compare():
    prior, objects = _prior_run()
    derivative = next(o for o in objects if o.role is mf.Role.DISPLAY)
    assert _decide(prior, derivative, expected_sha256=None).kind is mf.ProvenanceKind.INHERIT


def test_an_etag_is_not_an_input_to_the_decision():
    import inspect

    assert "etag" not in " ".join(inspect.signature(mf.decide_provenance).parameters)


def test_prior_run_must_have_been_verified_to_be_usable():
    _, complete = _sealed(2, run_id=PRIOR)
    other, _ = make_manifest(1, run_id=PRIOR)
    with pytest.raises(mf.CompleteMismatchError):
        mf.verify_run(complete.to_bytes(), other.to_bytes())  # the only way to obtain a VerifiedRun


# --- compatibility with the neighbouring modules -----------------------------------------------------


def test_constants_match_the_other_backup_modules():
    assert mf.DB_DUMP_NAME == ENCRYPTED_DUMP_NAME
    assert mf.db_dump_key(RUN) == f"db/{RUN}/{ENCRYPTED_DUMP_NAME}"
    assert mf.complete_key(RUN) == f"runs/{RUN}/COMPLETE.json"
    document = {"b": 1, "a": [1, 2], "c": {"z": None}}
    assert mf.canonical_line(document) == canonical_json(document)
    moment = datetime(2026, 10, 4, 14, 10, 5, tzinfo=timezone(timedelta(hours=2)))
    assert mf.format_timestamp(moment) == evidence_format_timestamp(moment) == "2026-10-04T12:10:05Z"


@pytest.mark.parametrize(
    "candidate",
    [
        RECIPIENT_A,
        "age1" + "q" * 57,
        "age1" + "Q" * 58,
        "age1" + "b" * 58,  # 'b' is not in the bech32 alphabet
        "AGE-SECRET-KEY-1" + "Q" * 58,
        "ssh-ed25519 AAAAC3",
        "age1pq1" + "q" * 58,
    ],
)
def test_recipient_acceptance_equals_the_encryption_primitives(candidate):
    try:
        parse_age_recipients(candidate)
        primitive_accepts = True
    except AgeRecipientError:
        primitive_accepts = False
    try:
        mf.DbDumpInfo(**(dataclasses.asdict(make_header([]).db_dump) | {"recipients": (candidate,)}))
        manifest_accepts = True
    except mf.ManifestFormatError:
        manifest_accepts = False
    assert manifest_accepts == primitive_accepts


@pytest.mark.parametrize("run_id", ["20261004T120000Z", "../20261004T120000Z-0123abcd", "x" * 25])
def test_key_helpers_refuse_invalid_run_ids(run_id):
    for helper in (mf.manifest_key, mf.complete_key, mf.db_dump_key):
        with pytest.raises(RunIdError):
            helper(run_id)
