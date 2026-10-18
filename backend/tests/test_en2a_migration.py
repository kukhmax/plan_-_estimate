"""EN-2a -- migration 0062: the table of the data keys, the text columns, the four indexes it drops, the rows it leaves alone, a downgrade that never hides a ciphertext."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0062_data_keys"


def old_engine():
    """The tables as 0061 leaves them (the columns this migration cares about), with an old plain client and an old object."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE clients (id CHAR(32) PRIMARY KEY, owner_user_id CHAR(32) NOT NULL REFERENCES users (id) ON DELETE CASCADE, "
            "first_name VARCHAR(255), last_name VARCHAR(255), company_name VARCHAR(512), phone VARCHAR(50), email VARCHAR(255), nip VARCHAR(20), "
            "street VARCHAR(255), postal_code VARCHAR(10), city VARCHAR(128), telegram_username VARCHAR(64), notes VARCHAR(4096))"
        ))
        for name, columns in (("ix_clients_company_name", "company_name"), ("ix_clients_phone", "phone"),
                              ("ix_clients_owner_first_name", "owner_user_id, first_name"), ("ix_clients_owner_last_name", "owner_user_id, last_name")):
            conn.execute(text(f"CREATE INDEX {name} ON clients ({columns})"))
        conn.execute(text(
            "CREATE TABLE projects (id CHAR(32) PRIMARY KEY, name VARCHAR(255) NOT NULL, address VARCHAR(512) NOT NULL, city VARCHAR(255) NOT NULL, "
            "postal_code VARCHAR(20) NOT NULL, description VARCHAR(4096))"
        ))
        conn.execute(text(
            "CREATE TABLE project_representatives (id CHAR(32) PRIMARY KEY, name VARCHAR(255) NOT NULL, phone VARCHAR(50), email VARCHAR(255), "
            "CONSTRAINT ck_project_representatives_name_not_empty CHECK (length(name) > 0))"
        ))
        conn.execute(text("CREATE TABLE project_notes (id CHAR(32) PRIMARY KEY, body TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1'), ('u2')"))
        conn.execute(text("INSERT INTO clients (id, owner_user_id, first_name, phone) VALUES ('c1', 'u1', 'Jan', '500')"))
        conn.execute(text("INSERT INTO projects (id, name, address, city, postal_code) VALUES ('p1', 'Dom', 'ul. Długa 1', 'Kraków', '30-001')"))
        conn.execute(text("INSERT INTO project_representatives (id, name) VALUES ('r1', 'Anna')"))
        conn.execute(text("INSERT INTO project_notes (id, body) VALUES ('n1', 'notatka')"))
    return engine


def engine_0062():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0061_expense_category" and len(module.revision) <= 32


def test_the_table_the_text_columns_and_the_dropped_indexes():
    engine = engine_0062()
    inspector = inspect(engine)
    assert {c["name"] for c in inspector.get_columns("data_keys")} == {"id", "owner_id", "key_id", "wrapped_dek", "wrapped_by", "kek_version", "active", "created_at"}
    for table, column in (("clients", "first_name"), ("clients", "notes"), ("projects", "name"), ("projects", "description"), ("project_representatives", "phone")):
        kind = next(c["type"] for c in inspector.get_columns(table) if c["name"] == column)
        assert kind.__class__.__name__ == "TEXT", (table, column)
    names = {i["name"] for i in inspector.get_indexes("clients")}
    assert not names & {"ix_clients_company_name", "ix_clients_phone", "ix_clients_owner_first_name", "ix_clients_owner_last_name"}


def test_the_rows_are_untouched_and_a_ciphertext_longer_than_the_old_limit_fits():
    engine = engine_0062()
    with engine.begin() as conn:
        assert conn.execute(text("SELECT first_name, phone FROM clients")).one() == ("Jan", "500")
        assert conn.execute(text("SELECT name, address, city, postal_code FROM projects")).one() == ("Dom", "ul. Długa 1", "Kraków", "30-001")
        conn.execute(text("UPDATE clients SET postal_code = :v"), {"v": "enc1:" + "x" * 300})  # the column was VARCHAR(10)
        assert len(conn.execute(text("SELECT postal_code FROM clients")).scalar_one()) == 305


def test_one_active_key_per_owner_and_the_wrapping_check():
    engine = engine_0062()
    insert = "INSERT INTO data_keys (id, owner_id, key_id, wrapped_dek, wrapped_by, active) VALUES (:id, :owner, :key, 'w', :by, :active)"
    with engine.begin() as conn:
        conn.execute(text(insert), {"id": "a", "owner": "u1", "key": "k1", "by": "SERVER_KEK", "active": 1})
        conn.execute(text(insert), {"id": "b", "owner": "u1", "key": "k2", "by": "SERVER_KEK", "active": 0})  # an old key stays to read old values
        conn.execute(text(insert), {"id": "c", "owner": "u2", "key": "k3", "by": "OWNER_KEY", "active": 1})
    for row in ({"id": "d", "owner": "u1", "key": "k4", "by": "SERVER_KEK", "active": 1},  # a second active key of the owner
                {"id": "e", "owner": "u2", "key": "k1", "by": "SERVER_KEK", "active": 0},  # a key_id is unique
                {"id": "f", "owner": "u2", "key": "k5", "by": "NOBODY", "active": 0}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(insert), row)


def test_a_key_goes_with_its_owner():
    engine = engine_0062()
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("INSERT INTO data_keys (id, owner_id, key_id, wrapped_dek) VALUES ('a', 'u2', 'k1', 'w')"))  # u2 owns no client
        conn.execute(text("DELETE FROM users WHERE id = 'u2'"))
        assert conn.execute(text("SELECT count(*) FROM data_keys")).scalar_one() == 0


def test_the_downgrade_restores_the_old_columns_and_indexes_while_nothing_is_encrypted():
    engine = engine_0062()
    run(engine, NAME, "downgrade")
    inspector = inspect(engine)
    assert "data_keys" not in inspector.get_table_names()
    assert {"ix_clients_company_name", "ix_clients_phone", "ix_clients_owner_first_name", "ix_clients_owner_last_name"} <= {i["name"] for i in inspector.get_indexes("clients")}
    kind = next(c["type"] for c in inspector.get_columns("clients") if c["name"] == "postal_code")
    assert kind.__class__.__name__ == "VARCHAR" and kind.length == 10
    with engine.begin() as conn:
        assert conn.execute(text("SELECT first_name FROM clients")).scalar_one() == "Jan"


@pytest.mark.parametrize("table, column", [("clients", "last_name"), ("projects", "name"), ("project_representatives", "email"), ("project_notes", "body")])
def test_the_downgrade_refuses_while_a_ciphertext_is_stored(table, column):
    engine = engine_0062()
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {table} SET {column} = 'enc1:k:n:c'"))
    with pytest.raises(RuntimeError, match="encrypted"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        assert conn.execute(text(f"SELECT {column} FROM {table}")).scalar_one() == "enc1:k:n:c"
    assert "data_keys" in inspect(engine).get_table_names()
