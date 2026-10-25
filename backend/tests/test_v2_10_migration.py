"""V2-10 -- migration 0077: the table of the points and routes of a room; what the database refuses; a downgrade that never drops the owner's input."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0077_room_points"
NOW = "2026-10-29 10:00:00"


def old_engine():
    """The tables 0076 leaves that this migration touches: a user, an object with a room, two price items (one of an old category)."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE rooms (id CHAR(32) PRIMARY KEY, project_id CHAR(32) NOT NULL REFERENCES projects (id) ON DELETE CASCADE)"))
        conn.execute(text("CREATE TABLE price_items (id CHAR(32) PRIMARY KEY, category VARCHAR(32) NOT NULL, unit VARCHAR(8) NOT NULL)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1')"))
        conn.execute(text("INSERT INTO rooms (id, project_id) VALUES ('r1', 'p1')"))
        conn.execute(text("INSERT INTO price_items VALUES ('i1', 'PAINTING', 'M2')"))
    return engine


def engine_0077():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
    return engine


def point(conn, pid="a", quantity="4", room="r1", item="i1", position=0):
    conn.execute(
        text("INSERT INTO room_points (id, owner_id, project_id, room_id, price_item_id, quantity, position, created_at, updated_at) VALUES (:id, 'u1', 'p1', :r, :i, :q, :pos, :n, :n)"),
        {"id": pid, "r": room, "i": item, "q": quantity, "pos": position, "n": NOW},
    )


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0076_payment_schedule_doc" and len(module.revision) <= 32
    assert module.NEW_CATEGORIES == ("ELECTRICAL", "PLUMBING", "TILE", "POINTS_ROUTES")


def test_upgrade_adds_the_table_and_leaves_every_row():
    engine = engine_0077()
    assert "room_points" in set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM price_items")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM room_points")).scalar_one() == 0


@pytest.mark.parametrize("quantity", ["0", "-1"])
def test_a_quantity_must_be_positive(quantity):
    engine = engine_0077()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        point(conn, quantity=quantity)


def test_a_row_needs_its_room_and_its_item_and_a_non_negative_position():
    engine = engine_0077()
    with engine.begin() as conn:
        point(conn, "ok")
        assert conn.execute(text("SELECT count(*) FROM room_points")).scalar_one() == 1
    for bad in ({"room": "nope"}, {"item": "nope"}, {"position": -1}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            point(conn, "bad", **bad)


def test_the_rows_go_with_their_room_and_with_their_object():
    engine = engine_0077()
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        point(conn)
        conn.execute(text("DELETE FROM rooms WHERE id = 'r1'"))
        assert conn.execute(text("SELECT count(*) FROM room_points")).scalar_one() == 0
        conn.execute(text("INSERT INTO rooms (id, project_id) VALUES ('r2', 'p1')"))
        point(conn, "b", room="r2")
        conn.execute(text("DELETE FROM rooms")), conn.execute(text("DELETE FROM projects"))
        assert conn.execute(text("SELECT count(*) FROM room_points")).scalar_one() == 0


def test_a_price_item_in_use_cannot_be_deleted_from_under_a_row():
    engine = engine_0077()
    with engine.begin() as conn:
        point(conn)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM price_items WHERE id = 'i1'"))


def test_the_downgrade_refuses_while_the_owners_input_exists_and_then_restores_the_old_shape():
    engine = engine_0077()
    with engine.begin() as conn:
        point(conn)
    with pytest.raises(RuntimeError, match="never dropped silently"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM room_points"))
        conn.execute(text("INSERT INTO price_items VALUES ('i2', 'ELECTRICAL', 'PCS')"))
    with pytest.raises(RuntimeError, match="never dropped silently"):  # an item of a new category is the owner's input too
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM price_items WHERE id = 'i2'"))
    run(engine, NAME, "downgrade")
    assert "room_points" not in set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM price_items")).scalar_one() == 1
    run(engine, NAME, "upgrade")  # and up again


def test_the_model_is_what_the_migration_makes():
    from app.models.room_point import RoomPoint

    engine = engine_0077()
    names = inspect(engine)
    assert {c["name"] for c in names.get_columns("room_points")} == {c.name for c in RoomPoint.__table__.columns}
    migration_checks = {c["name"] for c in names.get_check_constraints("room_points")}
    assert migration_checks == {c.name for c in RoomPoint.__table__.constraints if getattr(c, "name", None) and c.__class__.__name__ == "CheckConstraint"}
