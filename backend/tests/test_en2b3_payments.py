"""EN-2b-3 -- the title, the number, the shop and the note of the settlement records are ciphertext: the real columns, the re-encoding, the migration 0064."""
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, select, text

from app.core.config import settings
from app.core.key_ring import ring, set_owner_key
from app.domain.services.data_reencode_service import DataReencodeService, encrypted_columns
from app.models.project import Project
from app.models.project_payment import ProjectPayment
from app.models.user import User
from tests.conftest import TestingSessionLocal, fresh_kek
from tests.test_en2b2_documents import a_key, switch_on
from tests.test_stage16e2_contract import load_migration, run

NAME = "0064_encrypted_payments"
SEALED = ("title", "number", "counterparty", "note")


async def world(db):
    owner, project = uuid.uuid4(), uuid.uuid4()
    db.add(User(id=owner, telegram_user_id=880001, first_name="Test"))
    await db.flush()
    db.add(Project(id=project, owner_id=owner, name="Dom", address="ul. 1", city="Kraków", postal_code="30-001"))
    await db.flush()
    return owner, project


def expense(owner, project, **over):
    fields = dict(
        owner_id=owner, project_id=project, kind="EXPENSE", title="Farba dla Kowalskich", number="FV 12/2026", amount_gross=120,
        occurred_on=date(2026, 10, 1), counterparty="Castorama Mokotów", note="Reszta do zwrotu", created_at=datetime.now(UTC),
    )
    fields.update(over)
    return ProjectPayment(**fields)


def test_the_four_columns_are_encrypted_and_the_migration_lists_exactly_them():
    columns = {c.column for c in encrypted_columns() if c.table == "project_payments"}
    listed = {name for cols in load_migration(NAME).COLUMNS.values() for name, _length, _nullable in cols}
    assert columns == set(SEALED) == listed


async def test_a_record_is_stored_as_ciphertext_and_read_back_as_written(db_session, encryption_on):
    switch_on(a_key())
    owner, project = await world(db_session)
    db_session.add(expense(owner, project))
    await db_session.commit()
    stored = (await db_session.execute(text("SELECT title, number, counterparty, note, amount_gross FROM project_payments"))).one()
    assert all(value.startswith("enc1:") for value in stored[:4])
    assert "Kowalskich" not in stored[0] and "Castorama" not in stored[2]
    db_session.expire_all()
    row = (await db_session.execute(select(ProjectPayment))).scalar_one()
    assert (row.title, row.number, row.counterparty, row.note) == ("Farba dla Kowalskich", "FV 12/2026", "Castorama Mokotów", "Reszta do zwrotu")


async def test_empty_optional_values_stay_null(db_session, encryption_on):
    switch_on(a_key())
    owner, project = await world(db_session)
    db_session.add(expense(owner, project, number=None, counterparty=None, note=None))
    await db_session.commit()
    stored = (await db_session.execute(text("SELECT number, counterparty, note FROM project_payments"))).one()
    assert tuple(stored) == (None, None, None)


async def test_old_plain_records_become_ciphertext_by_the_command_and_read_the_same(db_session, encryption_on):
    settings.DATA_KEK = SecretStr("")  # the world before: plain
    owner, project = await world(db_session)
    db_session.add(expense(owner, project))
    db_session.add(expense(owner, project, kind="INVOICE", title="Faktura za etap 1", number=None, counterparty=None, note=None))
    await db_session.commit()
    assert (await db_session.execute(text("SELECT count(*) FROM project_payments WHERE title LIKE 'enc1:%'"))).scalar_one() == 0

    settings.DATA_KEK = fresh_kek()
    ring.disable()
    set_owner_key(None)
    stats = {f"{s.table}.{s.column}": s for s in await DataReencodeService(TestingSessionLocal).apply()}
    assert stats["project_payments.title"].converted == 2 and stats["project_payments.counterparty"].converted == 1
    assert sum(s.plain for s in stats.values()) == 0
    for column in SEALED:
        stored = (await db_session.execute(text(f"SELECT {column} FROM project_payments WHERE kind = 'EXPENSE'"))).scalar_one()
        assert stored.startswith("enc1:"), column

    db_session.expire_all()
    ring.strict = True
    rows = {r.kind: r for r in (await db_session.execute(select(ProjectPayment))).scalars()}
    assert rows["EXPENSE"].title == "Farba dla Kowalskich" and rows["EXPENSE"].note == "Reszta do zwrotu"
    assert rows["INVOICE"].title == "Faktura za etap 1" and rows["INVOICE"].number is None
    assert sum(s.undecryptable for s in await DataReencodeService(TestingSessionLocal).count(verify=True)) == 0


async def test_the_strict_read_refuses_a_plain_title(db_session, encryption_on):
    switch_on(a_key())
    owner, project = await world(db_session)
    db_session.add(expense(owner, project))
    await db_session.commit()
    await db_session.execute(text("UPDATE project_payments SET title = 'Jawny tytuł'"))
    await db_session.commit()
    db_session.expire_all()
    ring.strict = True
    with pytest.raises(Exception) as caught:
        (await db_session.execute(select(ProjectPayment))).scalar_one()
    assert getattr(caught.value, "code", None) == "DATA_PLAIN_VALUE_REFUSED" or getattr(caught.value.__cause__, "code", None) == "DATA_PLAIN_VALUE_REFUSED"


# --- migration 0064 ----------------------------------------------------------------------------------------------------------------------


def old_engine():
    """The table as 0063 leaves it (the columns of this migration), with a row."""
    migration = load_migration(NAME)
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for table, columns in migration.COLUMNS.items():
            definitions = ["id CHAR(32) PRIMARY KEY"]
            for name, length, nullable in columns:
                sql_type = "TEXT" if length is None else f"VARCHAR({length})"
                definitions.append(f"{name} {sql_type}{'' if nullable else ' NOT NULL'}")
            conn.execute(text(f"CREATE TABLE {table} ({', '.join(definitions)})"))
            values = ", ".join("'x'" for _ in columns)
            conn.execute(text(f"INSERT INTO {table} (id, {', '.join(name for name, _, _ in columns)}) VALUES ('r1', {values})"))
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0063_encrypted_documents" and len(module.revision) <= 32
    assert Path(module.__file__).name == f"{NAME}.py"


def test_the_columns_become_text_and_the_rows_are_untouched():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    types = {c["name"]: c["type"].__class__.__name__ for c in inspect(engine).get_columns("project_payments")}
    assert all(types[name] == "TEXT" for name in SEALED)
    with engine.begin() as conn:
        assert tuple(conn.execute(text("SELECT title, number, counterparty, note FROM project_payments")).one()) == ("x",) * 4
        conn.execute(text("UPDATE project_payments SET title = :v"), {"v": "enc1:" + "x" * 700})  # longer than the old VARCHAR(500)
        assert len(conn.execute(text("SELECT title FROM project_payments")).scalar_one()) == 705


def test_the_downgrade_restores_the_columns_while_nothing_is_encrypted():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    run(engine, NAME, "downgrade")
    kinds = {c["name"]: c["type"].__class__.__name__ for c in inspect(engine).get_columns("project_payments")}
    assert kinds["title"] == kinds["number"] == kinds["counterparty"] == "VARCHAR" and kinds["note"] == "TEXT"


@pytest.mark.parametrize("column", SEALED)
def test_the_downgrade_refuses_while_a_ciphertext_is_stored(column):
    engine = old_engine()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE project_payments SET {column} = 'enc1:k:n:c'"))
    with pytest.raises(RuntimeError, match="encrypted"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        assert conn.execute(text(f"SELECT {column} FROM project_payments")).scalar_one() == "enc1:k:n:c"


def test_every_column_is_sealed_under_its_own_label():
    """The label is the associated data of the ciphertext: a copy-paste to another column's label would let a value move between columns."""
    for name in SEALED:
        assert getattr(ProjectPayment, name).type.label == f"project_payments.{name}"
