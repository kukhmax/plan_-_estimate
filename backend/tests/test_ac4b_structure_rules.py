"""Archive cleanup AC-4b -- which documents hold a room / surface (pure rule, no database)."""
import uuid

from app.domain.rules.purge_rules import DocumentRef, structure_blockers


def test_every_document_that_is_not_archived_holds_it_whatever_its_kind_or_status():
    refs = [DocumentRef(kind, uuid.uuid4(), status) for kind, status in (
        ("CONCEALED_WORKS", "DRAFT"), ("CONCEALED_WORKS", "ISSUED"), ("ACCEPTANCE", "DRAFT"), ("DOWNTIME", "NOTICED"), ("DOWNTIME", "CLOSED"), ("ADJACENT_WORK", "ACTIVE"),
    )]
    assert [(b.kind, b.status) for b in structure_blockers(refs)] == [(r.kind, r.status) for r in refs]


def test_an_archived_document_holds_nothing():
    assert structure_blockers([DocumentRef("ACCEPTANCE", uuid.uuid4(), "ARCHIVED"), DocumentRef("ADJACENT_WORK", uuid.uuid4(), "ARCHIVED")]) == []


def test_the_same_document_is_named_once_even_when_it_points_to_the_room_and_to_its_photos():
    ref = DocumentRef("CONCEALED_WORKS", uuid.uuid4(), "DRAFT")
    assert len(structure_blockers([ref, ref, DocumentRef("CONCEALED_WORKS", ref.id, "DRAFT")])) == 1
    assert structure_blockers([]) == []
