"""V2-11 -- migration 0078: the norms and the calculations of materials; what the database refuses; a downgrade that never drops the owner's input."""
import pytest
from app.domain.data.material_norms import BY_CODE
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0078_material_calcs"
NOW = "2026-10-30 10:00:00"


def old_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE rooms (id CHAR(32) PRIMARY KEY, project_id CHAR(32) NOT NULL REFERENCES projects (id) ON DELETE CASCADE)"))
        conn.execute(text("CREATE TABLE price_items (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1')"))
        conn.execute(text("INSERT INTO rooms (id, project_id) VALUES ('r1', 'p1')"))
        conn.execute(text("INSERT INTO price_items (id) VALUES ('i1')"))
    return engine


def engine_0078():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
    return engine


def norm(conn, nid="n1", code="TILE_WASTE_STRAIGHT", kind="PARAM", value="10", name=None, package="TILE", item=None):
    name = name or BY_CODE[code].name
    conn.execute(
        text("INSERT INTO material_norms (id, owner_id, code, package, kind, name, value, price_item_id, created_at, updated_at) VALUES (:id, 'u1', :c, :p, :k, :n, :v, :i, :t, :t)"),
        {"id": nid, "c": code, "p": package, "k": kind, "n": name, "v": value, "i": item, "t": NOW},
    )


def calc(conn, cid="c1", package="TILE", room="r1", position=0):
    conn.execute(
        text("INSERT INTO material_calcs (id, owner_id, project_id, room_id, package, params, position, created_at, updated_at) VALUES (:id, 'u1', 'p1', :r, :p, '{}', :pos, :t, :t)"),
        {"id": cid, "r": room, "p": package, "pos": position, "t": NOW},
    )


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0077_room_points" and len(module.revision) <= 32


def test_upgrade_adds_the_two_tables_and_leaves_every_row():
    engine = engine_0078()
    assert {"material_norms", "material_calcs"} <= set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM price_items")).scalar_one() == 1


def test_a_norm_is_a_number_or_a_material_and_nothing_else():
    engine = engine_0078()
    with engine.begin() as conn:
        norm(conn, "a")
        norm(conn, "b", "TILE_ADHESIVE", "MATERIAL", None, item="i1")
        assert conn.execute(text("SELECT count(*) FROM material_norms")).scalar_one() == 2
    for bad in (
        dict(nid="c", value=None),  # a number without a value
        dict(nid="d", value="-1"),
        dict(nid="e", code="TILE_ADHESIVE", kind="MATERIAL", value="5"),  # a material with a value
        dict(nid="f", package="OTHER"),
        dict(nid="g", kind="WHAT"),
        dict(nid="h", item="i1"),  # a number tied to a price item
        dict(nid="i", code="TILE_ADHESIVE", kind="MATERIAL", value=None, item="nope"),
        dict(nid="j", code="TILE_WASTE_STRAIGHT"),  # the same code of the same owner
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            norm(conn, **bad)


def test_a_calculation_needs_its_room_and_a_known_package():
    engine = engine_0078()
    with engine.begin() as conn:
        calc(conn)
    for bad in (dict(cid="x", package="OTHER"), dict(cid="y", room="nope"), dict(cid="z", position=-1)):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            calc(conn, **bad)


def test_the_calculations_go_with_their_room_and_with_their_object():
    engine = engine_0078()
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        calc(conn)
        conn.execute(text("DELETE FROM rooms WHERE id = 'r1'"))
        assert conn.execute(text("SELECT count(*) FROM material_calcs")).scalar_one() == 0
        conn.execute(text("INSERT INTO rooms (id, project_id) VALUES ('r2', 'p1')"))
        calc(conn, "d", room="r2")
        conn.execute(text("DELETE FROM rooms")), conn.execute(text("DELETE FROM projects"))
        assert conn.execute(text("SELECT count(*) FROM material_calcs")).scalar_one() == 0


def test_the_downgrade_refuses_while_the_owners_input_exists_and_drops_untouched_starting_norms():
    engine = engine_0078()
    with engine.begin() as conn:
        norm(conn, "a")  # untouched
        norm(conn, "b", "TILE_ADHESIVE", "MATERIAL", None)
        calc(conn)
    with pytest.raises(RuntimeError, match="never dropped silently"):
        run(engine, NAME, "downgrade")  # a calculation
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM material_calcs"))
        conn.execute(text("UPDATE material_norms SET value = 12 WHERE id = 'a'"))
    with pytest.raises(RuntimeError, match="never dropped silently"):  # a changed number
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE material_norms SET value = 10 WHERE id = 'a'"))
        conn.execute(text("UPDATE material_norms SET name = 'Moj klej' WHERE id = 'b'"))
    with pytest.raises(RuntimeError, match="never dropped silently"):  # a renamed material
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE material_norms SET name = :n WHERE id = 'b'"), {"n": BY_CODE["TILE_ADHESIVE"].name})
        conn.execute(text("UPDATE material_norms SET price_item_id = 'i1' WHERE id = 'b'"))
    with pytest.raises(RuntimeError, match="never dropped silently"):  # a material tied to a price item
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE material_norms SET price_item_id = NULL WHERE id = 'b'"))
    run(engine, NAME, "downgrade")  # only untouched starting norms: dropped, they are made again on the next opening
    assert not ({"material_norms", "material_calcs"} & set(inspect(engine).get_table_names()))
    run(engine, NAME, "upgrade")


def test_the_models_are_what_the_migration_makes():
    from app.models.material import MaterialCalc, MaterialNorm

    engine = engine_0078()
    names = inspect(engine)
    for model in (MaterialNorm, MaterialCalc):
        assert {c["name"] for c in names.get_columns(model.__tablename__)} == {c.name for c in model.__table__.columns}
        migration_checks = {c["name"] for c in names.get_check_constraints(model.__tablename__)}
        assert migration_checks == {c.name for c in model.__table__.constraints if getattr(c, "name", None) and c.__class__.__name__ == "CheckConstraint"}
