"""V2-12 -- migration 0079: two more packages in the norms and the calculations; a downgrade that never drops the owner's input."""
import pytest
from app.domain.data.material_norms import BY_CODE
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run
from tests.test_v2_11_migration import NOW, calc, engine_0078, norm

NAME = "0079_material_packages"


def engine_0079():
    engine = engine_0078()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0078_material_calcs" and len(module.revision) <= 32


def test_before_the_upgrade_the_new_packages_are_refused_and_after_it_taken():
    engine = engine_0078()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        calc(conn, "x", package="ELECTRIC")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        norm(conn, "y", "ELEC_CABLE_M_SOCKET", package="ELECTRIC", value="6")
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        calc(conn, "x", package="ELECTRIC")
        calc(conn, "z", package="PLUMBING", position=1)
        norm(conn, "y", "ELEC_CABLE_M_SOCKET", package="ELECTRIC", value="6")
        assert conn.execute(text("SELECT count(*) FROM material_calcs")).scalar_one() == 2


def test_an_unknown_package_is_still_refused_and_the_old_rows_stay():
    engine = engine_0078()
    with engine.begin() as conn:
        norm(conn, "a")
        calc(conn, "c")
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM material_norms")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM material_calcs")).scalar_one() == 1
    for bad in (dict(cid="b", package="OTHER"), dict(cid="d", package="")):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            calc(conn, **bad)


def test_the_downgrade_refuses_while_the_owners_input_exists_and_drops_untouched_starting_norms():
    engine = engine_0079()
    with engine.begin() as conn:
        norm(conn, "keep", "TILE_WASTE_STRAIGHT")  # an old package: never touched by the downgrade
        norm(conn, "a", "ELEC_CABLE_M_SOCKET", package="ELECTRIC", value="6")  # untouched
        norm(conn, "b", "PL_PIPE", "MATERIAL", None, package="PLUMBING")
        calc(conn, "c", package="ELECTRIC")
    with pytest.raises(RuntimeError, match="never dropped silently"):
        run(engine, NAME, "downgrade")  # a calculation
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM material_calcs"))
        conn.execute(text("UPDATE material_norms SET value = 8 WHERE id = 'a'"))
    with pytest.raises(RuntimeError, match="never dropped silently"):  # a changed number
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE material_norms SET value = 6 WHERE id = 'a'"))
        conn.execute(text("UPDATE material_norms SET name = 'Moja rura' WHERE id = 'b'"))
    with pytest.raises(RuntimeError, match="never dropped silently"):  # a renamed material
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE material_norms SET name = :n, price_item_id = 'i1' WHERE id = 'b'"), {"n": BY_CODE["PL_PIPE"].name})
    with pytest.raises(RuntimeError, match="never dropped silently"):  # tied to a price item
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE material_norms SET price_item_id = NULL WHERE id = 'b'"))
    run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        assert [r[0] for r in conn.execute(text("SELECT id FROM material_norms ORDER BY id"))] == ["keep"]
    with pytest.raises(IntegrityError), engine.begin() as conn:
        calc(conn, "again", package="PLUMBING")
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        calc(conn, "again", package="PLUMBING")
