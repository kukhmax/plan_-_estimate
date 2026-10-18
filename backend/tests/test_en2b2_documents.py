"""EN-2b-2 -- the content of the documents and protocols is ciphertext: the JSON type, the real columns, the re-encoding, the migration 0063."""
import uuid
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Integer, create_engine, inspect, select, text
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core import data_crypto as dc
from app.core.config import settings
from app.core.encrypted_text import EncryptedJSON, EncryptedText
from app.core.key_ring import OwnerKey, ring, set_owner_key
from app.domain.services.data_reencode_service import (
    DataReencodeService,
    encrypted_columns,
)
from app.models.handover_protocol import HandoverProtocol
from app.models.issued_document import IssuedDocument
from app.models.project import Project
from app.models.user import User
from tests.conftest import TestingSessionLocal, fresh_kek, test_engine
from tests.test_stage16e2_contract import load_migration, run

BACKEND = Path(__file__).resolve().parents[1]
NAME = "0063_encrypted_documents"


class Scratch(DeclarativeBase):
    pass


class Box(Scratch):
    __tablename__ = "en2b2_box"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[dict | None] = mapped_column(EncryptedJSON("en2b2_box.data"), nullable=True)
    note: Mapped[str | None] = mapped_column(EncryptedText("en2b2_box.note"), nullable=True)


@pytest.fixture
async def boxes():
    async with test_engine.begin() as conn:
        await conn.run_sync(Scratch.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Scratch.metadata.drop_all)


def a_key() -> OwnerKey:
    return OwnerKey("k1", dc.new_key())


def switch_on(key: OwnerKey) -> None:
    settings.DATA_KEK = fresh_kek()
    ring.disable()
    ring.enable()
    ring.add(key.key_id, key.dek)
    set_owner_key(key)


async def raw_of(column: str, table: str = "en2b2_box") -> list:
    async with TestingSessionLocal() as db:
        return [r[0] for r in (await db.execute(text(f"SELECT {column} FROM {table} ORDER BY id"))).all()]


VALUES = [
    {"name": "Anna Nowak", "address": "ul. Długa 1/2, 30-001 Kraków"},
    [{"person_id": None, "name": "Иван Петров", "role": "właściciel"}, {"name": "Łukasz"}],
    {"nested": {"a": [1, 2.5, True, None, "żółć"]}},
    [],
    {},
    0,
    "text",
]


@pytest.mark.parametrize("value", VALUES)
async def test_a_json_value_is_stored_as_ciphertext_and_comes_back_as_it_was(boxes, encryption_on, value):
    switch_on(a_key())
    async with TestingSessionLocal() as db:
        db.add(Box(id=1, data=value))
        await db.commit()
    [stored] = await raw_of("data")
    assert stored.startswith("enc1:k1:") and "Nowak" not in stored and "żółć" not in stored
    async with TestingSessionLocal() as db:
        assert (await db.get(Box, 1)).data == value


async def test_no_value_stays_null_and_is_never_sealed(boxes, encryption_on):
    switch_on(a_key())
    async with TestingSessionLocal() as db:
        db.add(Box(id=1, data=None, note=None))
        await db.commit()
    assert await raw_of("data") == [None] and await raw_of("note") == [None]
    async with TestingSessionLocal() as db:
        row = await db.get(Box, 1)
        assert row.data is None and row.note is None


async def test_with_the_encryption_off_the_json_is_plain_text_in_the_column(boxes):
    async with TestingSessionLocal() as db:
        db.add(Box(id=1, data={"name": "Anna", "n": [1, 2]}))
        await db.commit()
    assert await raw_of("data") == ['{"name": "Anna", "n": [1, 2]}']
    async with TestingSessionLocal() as db:
        assert (await db.get(Box, 1)).data == {"name": "Anna", "n": [1, 2]}


async def test_an_old_plain_json_is_read_as_it_is_and_the_strict_read_refuses_it(boxes, encryption_on):
    switch_on(a_key())
    async with TestingSessionLocal() as db:
        await db.execute(text("""INSERT INTO en2b2_box (id, data) VALUES (1, '{"name": "Stary"}'), (2, 'null')"""))
        await db.commit()
    async with TestingSessionLocal() as db:
        assert (await db.get(Box, 1)).data == {"name": "Stary"} and (await db.get(Box, 2)).data is None
    ring.strict = True
    async with TestingSessionLocal() as db:
        with pytest.raises(dc.DataPlainValueError) as caught:
            await db.get(Box, 1)
    assert caught.value.code == "DATA_PLAIN_VALUE_REFUSED"


async def test_a_json_ciphertext_does_not_open_in_another_column(boxes, encryption_on):
    switch_on(a_key())
    async with TestingSessionLocal() as db:
        db.add(Box(id=1, data={"name": "Anna"}))
        await db.commit()
        await db.execute(text("UPDATE en2b2_box SET note = data"))
        await db.commit()
    async with TestingSessionLocal() as db:
        with pytest.raises(dc.DataDecryptError) as caught:
            await db.get(Box, 1)
    assert caught.value.code == "DATA_DECRYPT_FAILED" and "Anna" not in str(caught.value)


async def test_a_json_write_with_no_owner_key_is_refused(boxes, encryption_on):
    switch_on(a_key())
    set_owner_key(None)
    async with TestingSessionLocal() as db:
        db.add(Box(id=1, data={"name": "Anna"}))
        with pytest.raises(StatementError) as caught:
            await db.flush()
        await db.rollback()
    assert isinstance(caught.value.orig, dc.DataEncryptionContextMissingError)
    assert await raw_of("data") == []


# --- the real columns --------------------------------------------------------------------------------------------------------------------

DOCUMENT_TABLES = {
    "contracts", "handover_protocols", "concealed_works_protocols", "acceptance_protocols", "decision_protocols", "downtime_episodes", "issued_documents",
}


def test_every_content_column_of_the_documents_is_encrypted_and_the_migration_lists_exactly_them():
    columns = {(c.table, c.column) for c in encrypted_columns() if c.table in DOCUMENT_TABLES}
    migration = load_migration(NAME)
    listed = {(table, name) for table, cols in migration.COLUMNS.items() for name, _kind, _nullable in cols}
    assert columns == listed and len(columns) == 37
    assert {("contracts", "snapshot"), ("handover_protocols", "attendees"), ("downtime_episodes", "protocol_html"), ("issued_documents", "title")} <= columns


async def test_old_plain_documents_become_ciphertext_by_the_command_and_read_the_same(db_session, encryption_on):
    owner, project_id, protocol_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    settings.DATA_KEK = SecretStr("")  # the world before: plain
    db_session.add(User(id=owner, telegram_user_id=870001, first_name="Test"))
    await db_session.flush()
    db_session.add(Project(id=project_id, owner_id=owner, name="Dom", address="ul. 1", city="Kraków", postal_code="30-001"))
    await db_session.flush()
    attendees = [{"person_id": None, "name": "Anna Nowak", "role": "Właścicielka"}]
    db_session.add(HandoverProtocol(
        id=protocol_id, owner_id=owner, project_id=project_id, sequence=1, attendees=attendees, rooms={"r": {"damages": "Rysa"}}, meters="woda 123", notes="Klucze u sąsiada",
        snapshot={"customer": "Anna Nowak"}, document_html="<p>Anna Nowak</p>",
    ))
    db_session.add(IssuedDocument(
        owner_id=owner, project_id=project_id, kind="HANDOVER_PROTOCOL", title="Protokół — Dom Kowalskich", number="PRZEK/1", project_seq=1, template_version="1",
        status="SENT", issued_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    ))
    await db_session.commit()
    assert (await db_session.execute(text("SELECT attendees FROM handover_protocols"))).scalar_one() == '[{"person_id": null, "name": "Anna Nowak", "role": "Właścicielka"}]'

    settings.DATA_KEK = fresh_kek()
    ring.disable()
    set_owner_key(None)
    stats = {f"{s.table}.{s.column}": s for s in await DataReencodeService(TestingSessionLocal).apply()}
    assert stats["handover_protocols.attendees"].converted == 1 and stats["handover_protocols.document_html"].converted == 1
    assert stats["issued_documents.title"].converted == 1 and sum(s.plain for s in stats.values()) == 0
    for column in ("attendees", "rooms", "meters", "notes", "snapshot", "document_html"):
        stored = (await db_session.execute(text(f"SELECT {column} FROM handover_protocols"))).scalar_one()
        assert stored.startswith("enc1:") and "Nowak" not in stored and "Rysa" not in stored and "sąsiada" not in stored, column
    assert (await db_session.execute(text("SELECT title FROM issued_documents"))).scalar_one().startswith("enc1:")

    db_session.expire_all()
    ring.strict = True
    row = (await db_session.execute(select(HandoverProtocol))).scalar_one()
    assert row.attendees == attendees and row.rooms == {"r": {"damages": "Rysa"}} and row.meters == "woda 123" and row.snapshot == {"customer": "Anna Nowak"}
    assert row.document_html == "<p>Anna Nowak</p>" and row.notes == "Klucze u sąsiada"
    assert (await db_session.execute(select(IssuedDocument.title))).scalar_one() == "Protokół — Dom Kowalskich"
    assert sum(s.undecryptable for s in await DataReencodeService(TestingSessionLocal).count(verify=True)) == 0


# --- migration 0063 ----------------------------------------------------------------------------------------------------------------------


def old_engine():
    """The tables as 0062 leaves them (the columns of this migration), JSON as it is on SQLite, with a row each."""
    migration = load_migration(NAME)
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for table, columns in migration.COLUMNS.items():
            definitions = ["id CHAR(32) PRIMARY KEY"]
            for name, kind, nullable in columns:
                sql_type = {"json": "JSON", "text": "TEXT", "varchar": "VARCHAR(255)"}[kind]
                definitions.append(f"{name} {sql_type}{'' if nullable else ' NOT NULL'}")
            conn.execute(text(f"CREATE TABLE {table} ({', '.join(definitions)})"))
            values = {name: ("'[]'" if kind == "json" else "'x'") for name, kind, _ in columns}
            conn.execute(text(f"INSERT INTO {table} (id, {', '.join(values)}) VALUES ('r1', {', '.join(values.values())})"))
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0062_data_keys" and len(module.revision) <= 32


def test_the_columns_become_text_and_the_rows_are_untouched():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    inspector = inspect(engine)
    for table, columns in load_migration(NAME).COLUMNS.items():
        types = {c["name"]: c["type"].__class__.__name__ for c in inspector.get_columns(table)}
        assert all(types[name] == "TEXT" for name, _, _ in columns), table
    with engine.begin() as conn:
        assert conn.execute(text("SELECT attendees, notes FROM handover_protocols")).one() == ("[]", "x")
        assert conn.execute(text("SELECT title FROM issued_documents")).scalar_one() == "x"
        conn.execute(text("UPDATE issued_documents SET title = :v"), {"v": "enc1:" + "x" * 600})  # longer than the old VARCHAR(255)
        assert len(conn.execute(text("SELECT title FROM issued_documents")).scalar_one()) == 605


def test_the_downgrade_restores_the_columns_while_nothing_is_encrypted():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    run(engine, NAME, "downgrade")
    kinds = {c["name"]: c["type"].__class__.__name__ for c in inspect(engine).get_columns("issued_documents")}
    assert kinds["title"] == "VARCHAR"
    with engine.begin() as conn:
        assert conn.execute(text("SELECT title FROM issued_documents")).scalar_one() == "x"


@pytest.mark.parametrize("table, column", [("contracts", "snapshot"), ("handover_protocols", "notes"), ("downtime_episodes", "protocol_html"), ("issued_documents", "title")])
def test_the_downgrade_refuses_while_a_ciphertext_is_stored(table, column):
    engine = old_engine()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {table} SET {column} = 'enc1:k:n:c'"))
    with pytest.raises(RuntimeError, match="encrypted"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        assert conn.execute(text(f"SELECT {column} FROM {table}")).scalar_one() == "enc1:k:n:c"
