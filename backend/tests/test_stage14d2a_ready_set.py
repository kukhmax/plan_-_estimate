"""Stage 14D.2A — canonical READY-set serialization and digest (pure, no DB)."""

import dataclasses
import hashlib
import random
import uuid

import pytest

from app.domain.services.media_backup_ready_set import (
    READY_SET_HEADER,
    ReadyAsset,
    ReadySetFormatError,
    canonical_bytes,
    canonical_line,
    ready_set_digest,
)

EMPTY_DIGEST = hashlib.sha256(b"plan-estimate/ready-set/v1\n").hexdigest()


def asset(n: int = 1, **overrides) -> ReadyAsset:
    asset_id = overrides.pop("asset_id", uuid.UUID(int=n, version=4))
    base = f"photos/v1/{asset_id}/"
    values = dict(
        asset_id=asset_id,
        key_original=base + "original.jpg",
        key_display=base + "display.jpg",
        key_thumbnail=base + "thumb.jpg",
        byte_size=1000 + n,
        display_byte_size=500 + n,
        thumbnail_byte_size=50 + n,
        sha256=hashlib.sha256(str(n).encode()).hexdigest(),
    )
    values.update(overrides)
    return ReadyAsset(**values)


def test_canonical_line_exact_bytes():
    a = asset(asset_id=uuid.UUID("0b7c3f0e-1d2a-4b5c-8d9e-0123456789ab"), byte_size=12, display_byte_size=7,
              thumbnail_byte_size=3, sha256="ab" * 32)
    assert canonical_line(a) == (
        b"0b7c3f0e-1d2a-4b5c-8d9e-0123456789ab"
        b"|photos/v1/0b7c3f0e-1d2a-4b5c-8d9e-0123456789ab/original.jpg"
        b"|photos/v1/0b7c3f0e-1d2a-4b5c-8d9e-0123456789ab/display.jpg"
        b"|photos/v1/0b7c3f0e-1d2a-4b5c-8d9e-0123456789ab/thumb.jpg"
        b"|12|7|3|" + b"ab" * 32 + b"\n"
    )


def test_empty_set_has_a_fixed_digest():
    digest = ready_set_digest([])
    assert digest.ready_count == 0
    assert digest.ready_set_sha256 == EMPTY_DIGEST
    assert canonical_bytes([]) == READY_SET_HEADER


def test_digest_is_the_sha256_of_header_plus_sorted_lines():
    items = [asset(n) for n in (3, 1, 2)]
    expected = READY_SET_HEADER + b"".join(sorted(canonical_line(a) for a in items))
    digest = ready_set_digest(items)
    assert digest.ready_set_sha256 == hashlib.sha256(expected).hexdigest()
    assert digest.ready_count == 3


def test_digest_does_not_depend_on_input_order():
    items = [asset(n) for n in range(1, 40)]
    reference = ready_set_digest(items)
    rnd = random.Random(14)
    for _ in range(20):
        shuffled = items[:]
        rnd.shuffle(shuffled)
        assert ready_set_digest(shuffled) == reference
    assert ready_set_digest(iter(reversed(items))) == reference  # any iterable


def test_equivalent_sets_built_separately_are_equal():
    a = [asset(n) for n in range(1, 6)]
    b = [asset(n) for n in range(5, 0, -1)]
    assert a is not b and ready_set_digest(a) == ready_set_digest(b)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset_id", uuid.UUID(int=999, version=4)),
        ("key_original", "photos/v1/x/original.png"),
        ("key_display", "photos/v1/x/display2.jpg"),
        ("key_thumbnail", "photos/v1/x/thumb2.jpg"),
        ("byte_size", 999_999),
        ("display_byte_size", 999_998),
        ("thumbnail_byte_size", 999_997),
        ("sha256", "f" * 64),
    ],
)
def test_any_relevant_field_change_changes_the_digest(field, value):
    items = [asset(n) for n in range(1, 4)]
    changed = items[:1] + [dataclasses.replace(items[1], **{field: value})] + items[2:]
    assert ready_set_digest(changed).ready_set_sha256 != ready_set_digest(items).ready_set_sha256


def test_adding_or_removing_an_asset_changes_the_digest():
    items = [asset(n) for n in range(1, 4)]
    base = ready_set_digest(items).ready_set_sha256
    assert ready_set_digest(items[:2]).ready_set_sha256 != base
    assert ready_set_digest([*items, asset(9)]).ready_set_sha256 != base


@pytest.mark.parametrize(
    "overrides",
    [
        {"sha256": "AB" * 32},
        {"sha256": "ab" * 31},
        {"sha256": "g" * 64},
        {"key_original": ""},
        {"key_original": "photos/v1/a|b/original.jpg"},
        {"key_display": "photos/v1/a\nb/display.jpg"},
        {"key_thumbnail": "photos/v1/a b/thumb.jpg"},
        {"key_thumbnail": "photos/v1/zdjęcie/thumb.jpg"},
        {"byte_size": 0},
        {"byte_size": -1},
        {"display_byte_size": True},
        {"thumbnail_byte_size": 1.0},
        {"byte_size": "12"},
        {"asset_id": "0b7c3f0e-1d2a-4b5c-8d9e-0123456789ab"},
    ],
)
def test_non_canonical_values_are_rejected_not_normalized(overrides):
    with pytest.raises(ReadySetFormatError):
        ready_set_digest([asset(1, **overrides)])


def test_duplicate_asset_ids_are_rejected():
    a = asset(1)
    with pytest.raises(ReadySetFormatError):
        ready_set_digest([a, dataclasses.replace(a, byte_size=5)])


def test_uuid_text_is_canonical_lowercase():
    upper_source = uuid.UUID("0B7C3F0E-1D2A-4B5C-8D9E-0123456789AB")
    assert canonical_line(asset(asset_id=upper_source)).startswith(b"0b7c3f0e-1d2a-4b5c-8d9e-0123456789ab|")
