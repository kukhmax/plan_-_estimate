"""Archive cleanup AC-2 -- the rules of the final deletion of a photo (pure functions)."""
import uuid

from app.domain.rules.purge_rules import (
    ProtocolRef,
    acceptance_photo_ids,
    photo_blockers,
)

A, B = uuid.UUID(int=1), uuid.UUID(int=2)


def ref(kind="CONCEALED_WORKS", status="DRAFT", photos=(str(A),)):
    return ProtocolRef(kind, uuid.uuid4(), status, frozenset(photos))


def test_a_protocol_that_points_to_the_photo_blocks_in_every_status_but_archived():
    for status in ("DRAFT", "ISSUED", "NOTICED", "CLOSED"):
        assert [b.status for b in photo_blockers(A, [ref(status=status)])] == [status]
    assert photo_blockers(A, [ref(status="ARCHIVED")]) == []


def test_only_the_photos_a_protocol_names_are_protected():
    assert photo_blockers(B, [ref(photos=(str(A),)), ref("DOWNTIME", "NOTICED", ())]) == []


def test_every_protocol_that_names_the_photo_is_reported_with_its_kind():
    blockers = photo_blockers(A, [ref("CONCEALED_WORKS"), ref("DOWNTIME", "NOTICED"), ref("ACCEPTANCE", "ISSUED"), ref("ACCEPTANCE", "ARCHIVED")])
    assert [b.kind for b in blockers] == ["CONCEALED_WORKS", "DOWNTIME", "ACCEPTANCE"]


def test_the_photos_in_the_remarks_of_an_acceptance_are_found_in_either_stored_shape():
    as_dict = {"s1": {"assessed": True, "remarks": {"r1": {"photo_ids": [str(A)]}, "r2": {"photo_ids": []}}}, "s2": {"remarks": {"r3": {"photo_ids": [str(B)]}}}}
    as_list = {"s1": {"remarks": [{"photo_ids": [str(A)]}, {"photo_ids": [str(B)]}]}}
    assert acceptance_photo_ids(as_dict) == {str(A), str(B)}
    assert acceptance_photo_ids(as_list) == {str(A), str(B)}


def test_an_empty_or_odd_acceptance_has_no_photos_and_does_not_crash():
    assert acceptance_photo_ids(None) == frozenset()
    assert acceptance_photo_ids({}) == frozenset()
    assert acceptance_photo_ids({"s": "x", "t": {"remarks": None}, "u": {"remarks": ["x", {"photo_ids": None}]}}) == frozenset()
