"""Stage 15F.1 — the journal of issued documents: migration 0038, numbers, reuse of a running attempt, stale attempts."""

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, delete, event, inspect, select, text
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401
from app.core.database import Base
from app.domain.exceptions import IssuedDocumentNotFoundError, ProjectNotFoundError
from app.domain.services.issued_document_service import (
    PENDING_TTL,
    IssuedDocumentService,
    number_base,
    scope_key,
)
from app.models.client import Client, ClientType
from app.models.issued_document import (
    IssuedDocument,
    IssuedDocumentKind,
    IssuedDocumentStatus,
)
from app.models.project import Project
from app.models.user import User

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0038_issued_documents.py"
K = IssuedDocumentKind
T = datetime(2026, 10, 8, 17, 53, 10, tzinfo=UTC)  # 19:53 in Poland (summer time)


# --- migration ------------------------------------------------------------------------------------------------------------


def load_migration():
    spec = importlib.util.spec_from_file_location("m0038", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_op(engine, fn):
    with engine.begin() as conn:
        module = load_migration()
        module.op = Operations(MigrationContext.configure(conn))
        fn(module)


def fresh_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "issued_documents"])
    return engine


def test_revision_chain_and_single_head():
    module = load_migration()
    assert module.revision == "0038_issued_documents" and module.down_revision == "0037_executor_profiles"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0049_concealed_works"]


def test_upgrade_matches_the_model_and_downgrade_removes_only_the_table():
    engine = fresh_engine()
    before = set(inspect(engine).get_table_names())
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    assert set(insp.get_table_names()) == before | {"issued_documents"}
    columns = {c["name"]: c for c in insp.get_columns("issued_documents")}
    assert set(columns) == {c.name for c in IssuedDocument.__table__.columns}
    assert {n for n, c in columns.items() if not c["nullable"]} == {
        "id", "owner_id", "project_id", "kind", "title", "number", "project_seq", "template_version", "status", "issued_at",
        "created_at", "updated_at"}
    assert {fk["referred_table"]: fk["options"]["ondelete"] for fk in insp.get_foreign_keys("issued_documents")} == {
        "users": "CASCADE", "projects": "CASCADE"}
    assert {tuple(u["column_names"]) for u in insp.get_unique_constraints("issued_documents")} == {
        ("owner_id", "number"), ("owner_id", "project_id", "project_seq")}
    assert {c["name"] for c in insp.get_check_constraints("issued_documents")} == {
        "ck_issued_documents_kind", "ck_issued_documents_status", "ck_issued_documents_seq_positive", "ck_issued_documents_number_not_empty"}
    run_op(engine, lambda m: m.downgrade())
    assert set(inspect(engine).get_table_names()) == before
    run_op(engine, lambda m: m.upgrade())
    assert "issued_documents" in inspect(engine).get_table_names()


def row(owner, project, **over):
    values = {"id": uuid.uuid4().hex, "owner_id": owner, "project_id": project, "kind": "ESTIMATE", "title": "t", "number": "N1",
              "project_seq": 1, "template_version": "1", "status": "PENDING", "issued_at": "2026-10-08", "created_at": "2026-10-08",
              "updated_at": "2026-10-08"}
    values.update(over)
    return text("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, "
                "issued_at, created_at, updated_at) VALUES (:id, :owner_id, :project_id, :kind, :title, :number, :project_seq, "
                ":template_version, :status, :issued_at, :created_at, :updated_at)"), values


def test_the_database_itself_refuses_a_wrong_kind_status_number_and_duplicates_and_cascades():
    engine = fresh_engine()
    run_op(engine, lambda m: m.upgrade())
    owner, other, project = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as conn:
        for user, tg in ((owner, 1), (other, 2)):
            conn.execute(text("INSERT INTO users (id, telegram_user_id, created_at, updated_at) VALUES (:i, :t, '2026-10-08', '2026-10-08')"),
                         {"i": user, "t": tg})
        conn.execute(text("INSERT INTO projects (id, owner_id, name, address, city, postal_code, status, is_archived, created_at, updated_at) "
                          "VALUES (:p, :o, 'p', 'a', 'c', '00-001', 'PLANNING', 0, '2026-10-08', '2026-10-08')"), {"p": project, "o": owner})
        conn.execute(*row(owner, project))
    bad = [{"kind": "CONTRACT"}, {"status": "DONE"}, {"project_seq": 0}, {"number": ""}, {"number": "N1", "project_seq": 2},
           {"number": "N2"}]
    for over in bad:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(*row(owner, project, **over))
    with engine.begin() as conn:  # another owner may use the same number
        conn.execute(text("DELETE FROM projects WHERE id = :p"), {"p": project})
        assert conn.execute(text("SELECT count(*) FROM issued_documents")).scalar_one() == 0


# --- number text ----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "moment", "expected"),
    [
        (K.ESTIMATE, T, "KOSZ/2026/10/08/1953"),
        (K.PHOTO_REPORT, T, "FOTO/2026/10/08/1953"),
        (K.ESTIMATE, datetime(2026, 1, 15, 17, 53, tzinfo=UTC), "KOSZ/2026/01/15/1853"),  # winter time is UTC+1
        (K.ESTIMATE, datetime(2026, 10, 8, 22, 30, tzinfo=UTC), "KOSZ/2026/10/09/0030"),  # past midnight in Poland
        (K.ESTIMATE, datetime(2026, 12, 31, 23, 5, tzinfo=UTC), "KOSZ/2027/01/01/0005"),  # the year changes in Poland first
        (K.ESTIMATE, datetime(2026, 10, 8, 17, 53), "KOSZ/2026/10/08/1953"),  # a naive value is UTC, as the database keeps it
    ],
)
def test_the_number_is_the_kind_and_the_polish_local_date_and_time(kind, moment, expected):
    assert number_base(kind, moment) == expected


def test_a_scope_is_recognised_whatever_the_order_of_its_keys():
    assert scope_key(None) == scope_key({}) == "" and scope_key({"a": 1, "b": 2}) == scope_key({"b": 2, "a": 1})
    assert scope_key({"rooms": ["x"]}) != scope_key({"rooms": ["y"]})


# --- the service -----------------------------------------------------------------------------------------------------------------


async def world(db, telegram_id=9701):
    owner = User(telegram_user_id=telegram_id, username=f"u{telegram_id}")
    db.add(owner)
    await db.flush()
    client = Client(owner_user_id=owner.id, client_type=ClientType.PRIVATE_PERSON, first_name="Anna", last_name="Nowak")
    db.add(client)
    await db.flush()
    project = Project(owner_id=owner.id, client_id=client.id, name="Mokotów", address="ul. Dobra 1", city="Warszawa", postal_code="00-001")
    other = Project(owner_id=owner.id, name="Drugi", address="ul. Inna 2", city="Warszawa", postal_code="00-002")
    db.add_all([project, other])
    await db.commit()
    return owner, project, other


class Clock:
    def __init__(self, moment=T):
        self.moment = moment

    def __call__(self):
        return self.moment


def service(db, clock=None):
    return IssuedDocumentService(db, clock=clock or Clock())


async def reserve(svc, owner, project, kind=K.ESTIMATE, **kw):
    kw.setdefault("title", "Kosztorys")
    kw.setdefault("template_version", "1")
    return await svc.reserve(owner.id, project.id, kind, **kw)


async def test_the_first_document_gets_the_time_number_and_the_running_number_one(db_session):
    owner, project, _ = await world(db_session)
    result = await reserve(service(db_session), owner, project, source_id=uuid.uuid4(), source_version=3, client_id=project.client_id)
    doc = result.document
    assert not result.reused and (doc.number, doc.project_seq) == ("KOSZ/2026/10/08/1953", 1)
    assert (doc.kind, doc.status, doc.template_version, doc.source_version) == ("ESTIMATE", "PENDING", "1", 3)
    assert doc.client_id == project.client_id and doc.issued_at.replace(tzinfo=UTC) == T and doc.sent_at is None


async def test_the_running_number_counts_all_kinds_of_one_object_and_nothing_of_another(db_session):
    owner, project, other = await world(db_session)
    svc = service(db_session)
    docs = [(await reserve(svc, owner, project, source_id=uuid.uuid4())).document,
            (await reserve(svc, owner, project, K.PHOTO_REPORT)).document,
            (await reserve(svc, owner, project, source_id=uuid.uuid4())).document]
    assert [d.project_seq for d in docs] == [1, 2, 3]
    assert (await reserve(svc, owner, other, source_id=uuid.uuid4())).document.project_seq == 1


async def test_the_same_minute_gets_a_suffix_and_the_next_minute_does_not(db_session):
    owner, project, other = await world(db_session)
    clock = Clock()
    svc = service(db_session, clock)
    numbers = [(await reserve(svc, owner, project, source_id=uuid.uuid4())).document.number for _ in range(3)]
    assert numbers == ["KOSZ/2026/10/08/1953", "KOSZ/2026/10/08/1953-2", "KOSZ/2026/10/08/1953-3"]
    assert (await reserve(svc, owner, other, source_id=uuid.uuid4())).document.number == "KOSZ/2026/10/08/1953-4"  # numbers are the owner's
    assert (await reserve(svc, owner, project, K.PHOTO_REPORT)).document.number == "FOTO/2026/10/08/1953"
    clock.moment = T + timedelta(minutes=1)
    assert (await reserve(svc, owner, project, source_id=uuid.uuid4())).document.number == "KOSZ/2026/10/08/1954"


async def test_a_prefix_of_another_number_is_not_mistaken_for_the_same_minute(db_session):
    owner, project, _ = await world(db_session)
    svc = service(db_session)
    first = await reserve(svc, owner, project, source_id=uuid.uuid4())
    clock = Clock(T.replace(hour=17, minute=5))  # 19:05 -> KOSZ/2026/10/08/1905: its text is not a prefix of 1953 or the other way round
    later = await reserve(service(db_session, clock), owner, project, source_id=uuid.uuid4())
    assert first.document.number == "KOSZ/2026/10/08/1953" and later.document.number == "KOSZ/2026/10/08/1905"


async def test_every_owner_has_numbers_of_their_own(db_session):
    owner, project, _ = await world(db_session)
    stranger, stranger_project, _ = await world(db_session, telegram_id=9702)
    svc = service(db_session)
    mine = (await reserve(svc, owner, project, source_id=uuid.uuid4())).document
    theirs = (await reserve(svc, stranger, stranger_project, source_id=uuid.uuid4())).document
    assert mine.number == theirs.number == "KOSZ/2026/10/08/1953" and mine.project_seq == theirs.project_seq == 1


async def test_a_second_tap_on_the_same_running_document_returns_the_same_row(db_session):
    owner, project, _ = await world(db_session)
    svc = service(db_session)
    source = uuid.uuid4()
    first = await reserve(svc, owner, project, source_id=source)
    again = await reserve(svc, owner, project, source_id=source)
    assert again.reused and again.document.id == first.document.id
    assert len(await svc.list_for_project(owner.id, project.id)) == 1


async def test_a_different_source_or_scope_or_kind_is_a_different_document(db_session):
    owner, project, _ = await world(db_session)
    svc = service(db_session)
    a = await reserve(svc, owner, project, source_id=uuid.uuid4())
    b = await reserve(svc, owner, project, source_id=uuid.uuid4())
    r1 = await reserve(svc, owner, project, K.PHOTO_REPORT, scope={"rooms": ["x"]})
    r1_again = await reserve(svc, owner, project, K.PHOTO_REPORT, scope={"rooms": ["x"]})
    r2 = await reserve(svc, owner, project, K.PHOTO_REPORT, scope={"rooms": ["y"]})
    whole = await reserve(svc, owner, project, K.PHOTO_REPORT)
    assert len({a.document.id, b.document.id, r1.document.id, r2.document.id, whole.document.id}) == 5 and r1_again.reused


async def test_a_running_document_of_another_kind_is_never_taken_for_the_same_one(db_session):
    owner, project, _ = await world(db_session)
    svc = service(db_session)
    report = await reserve(svc, owner, project, K.PHOTO_REPORT)  # no source, no scope
    estimate = await reserve(svc, owner, project, K.ESTIMATE)  # no source, no scope either
    assert not estimate.reused and estimate.document.id != report.document.id and estimate.document.kind == "ESTIMATE"


async def test_after_it_ends_a_new_request_for_the_same_document_is_a_new_attempt(db_session):
    owner, project, _ = await world(db_session)
    svc = service(db_session)
    source = uuid.uuid4()
    first = (await reserve(svc, owner, project, source_id=source)).document
    await svc.mark_failed(owner.id, first.id, "DOCUMENT_RENDER_TIMEOUT")
    second = await reserve(svc, owner, project, source_id=source)
    assert not second.reused and second.document.project_seq == 2
    await svc.mark_sent(owner.id, second.document.id, pages=1, byte_size=10, sha256="a" * 64)
    third = await reserve(svc, owner, project, source_id=source)
    assert not third.reused and third.document.project_seq == 3


async def test_an_attempt_that_never_ended_is_failed_as_interrupted_after_the_ttl(db_session):
    owner, project, _ = await world(db_session)
    clock = Clock()
    svc = service(db_session, clock)
    source = uuid.uuid4()
    stale = (await reserve(svc, owner, project, source_id=source)).document
    clock.moment = T + PENDING_TTL - timedelta(seconds=1)
    assert (await svc.get(owner.id, project.id, stale.id)).status == "PENDING"
    clock.moment = T + PENDING_TTL + timedelta(seconds=1)
    expired = await svc.get(owner.id, project.id, stale.id)
    assert (expired.status, expired.error_code) == ("FAILED", "INTERRUPTED")
    fresh = await reserve(svc, owner, project, source_id=source)
    assert not fresh.reused and fresh.document.project_seq == 2


async def test_listing_expires_the_stale_ones_too_and_is_newest_first(db_session):
    owner, project, _ = await world(db_session)
    clock = Clock()
    svc = service(db_session, clock)
    old = (await reserve(svc, owner, project, source_id=uuid.uuid4())).document
    clock.moment = T + timedelta(hours=1)
    new = (await reserve(svc, owner, project, source_id=uuid.uuid4())).document
    listed = await svc.list_for_project(owner.id, project.id)
    assert [d.id for d in listed] == [new.id, old.id] and [d.status for d in listed] == ["PENDING", "FAILED"]
    assert [d.id for d in await svc.list_for_project(owner.id, project.id, limit=1)] == [new.id]


async def test_sent_and_failed_record_what_happened(db_session):
    owner, project, _ = await world(db_session)
    clock = Clock()
    svc = service(db_session, clock)
    doc = (await reserve(svc, owner, project, source_id=uuid.uuid4())).document
    clock.moment = T + timedelta(seconds=40)
    sent = await svc.mark_sent(owner.id, doc.id, pages=3, byte_size=123456, sha256="b" * 64)
    assert (sent.status, sent.pages, sent.byte_size, sent.sha256, sent.error_code) == ("SENT", 3, 123456, "b" * 64, None)
    assert sent.sent_at.replace(tzinfo=UTC) == T + timedelta(seconds=40)
    other = (await reserve(svc, owner, project, source_id=uuid.uuid4())).document
    failed = await svc.mark_failed(owner.id, other.id, "X" * 100)
    assert (failed.status, len(failed.error_code), failed.sent_at) == ("FAILED", 64, None)


async def test_another_owner_cannot_see_mark_or_list_a_document(db_session):
    owner, project, _ = await world(db_session)
    stranger, stranger_project, _ = await world(db_session, telegram_id=9703)
    owner_id, project_id, stranger_id, stranger_project_id = owner.id, project.id, stranger.id, stranger_project.id
    svc = service(db_session)
    doc_id = (await reserve(svc, owner, project, source_id=uuid.uuid4())).document.id
    for call in (lambda: svc.get(stranger_id, project_id, doc_id), lambda: svc.get(owner_id, stranger_project_id, doc_id),
                 lambda: svc.get(owner_id, project_id, uuid.uuid4()),
                 lambda: svc.mark_sent(stranger_id, doc_id, pages=1, byte_size=1, sha256="c" * 64),
                 lambda: svc.mark_failed(stranger_id, doc_id, "X")):
        with pytest.raises(IssuedDocumentNotFoundError):
            await call()
    with pytest.raises(ProjectNotFoundError):
        await svc.list_for_project(stranger_id, project_id)
    with pytest.raises(ProjectNotFoundError):
        await svc.reserve(stranger_id, project_id, K.ESTIMATE, title="x", template_version="1", source_id=uuid.uuid4())
    assert (await svc.get(owner_id, project_id, doc_id)).status == "PENDING"
    rows = (await db_session.execute(select(IssuedDocument))).scalars().all()
    assert len(rows) == 1


async def test_a_document_goes_with_its_project(db_session):
    owner, project, _ = await world(db_session)
    await reserve(service(db_session), owner, project, source_id=uuid.uuid4())
    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()
    assert (await db_session.execute(select(IssuedDocument))).first() is None


def test_the_status_and_kind_values_match_the_database_checks():
    assert {s.value for s in IssuedDocumentStatus} == {"PENDING", "SENT", "FAILED"}
    assert {k.value for k in IssuedDocumentKind} == {"ESTIMATE", "PHOTO_REPORT", "TECH_CARD", "PRODUCTION_PLAN", "CONTRACT", "HANDOVER_PROTOCOL", "CONCEALED_WORKS_PROTOCOL"}
