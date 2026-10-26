"""Archive cleanup AC-5b -- which documents hold an object (pure rule, no database)."""
import uuid

import pytest

from app.domain.rules.purge_rules import OBJECT_BLOCKING_STATUSES, DocumentRef, object_blockers


@pytest.mark.parametrize(
    "kind, status, holds",
    [
        ("CONTRACT", "DRAFT", False), ("CONTRACT", "ISSUED", True), ("CONTRACT", "SIGNED", True), ("CONTRACT", "ARCHIVED", False),
        ("HANDOVER", "DRAFT", False), ("HANDOVER", "ISSUED", True), ("HANDOVER", "ARCHIVED", False),
        ("CONCEALED_WORKS", "ISSUED", True), ("CONCEALED_WORKS", "ARCHIVED", False),
        ("DECISION", "ISSUED", True), ("DECISION", "DRAFT", False),
        ("ACCEPTANCE", "ISSUED", True), ("ACCEPTANCE", "ARCHIVED", False),
        ("DOWNTIME", "DRAFT", False), ("DOWNTIME", "NOTICED", True), ("DOWNTIME", "CLOSED", True), ("DOWNTIME", "ARCHIVED", False),
    ],
)
def test_a_document_holds_the_object_by_its_kind_and_status(kind, status, holds):
    ref = DocumentRef(kind, uuid.uuid4(), status)
    assert bool(object_blockers([ref])) is holds


def test_the_blockers_name_the_kind_the_id_and_the_status_of_each_holding_document():
    contract, draft, notice = DocumentRef("CONTRACT", uuid.uuid4(), "SIGNED"), DocumentRef("HANDOVER", uuid.uuid4(), "DRAFT"), DocumentRef("DOWNTIME", uuid.uuid4(), "NOTICED")
    found = object_blockers([contract, draft, notice])
    assert [(b.kind, b.protocol_id, b.status) for b in found] == [("CONTRACT", contract.id, "SIGNED"), ("DOWNTIME", notice.id, "NOTICED")]


def test_an_object_without_documents_or_a_document_of_an_unknown_kind_is_not_held():
    assert object_blockers([]) == []
    assert object_blockers([DocumentRef("SOMETHING_NEW", uuid.uuid4(), "ISSUED")]) == []


def test_every_kind_of_document_has_a_rule():
    assert set(OBJECT_BLOCKING_STATUSES) == {"CONTRACT", "HANDOVER", "CONCEALED_WORKS", "PRESSURE_TEST", "DECISION", "ACCEPTANCE", "DOWNTIME"}
