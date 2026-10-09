"""Stage 14F.1 — durable finding lineage (`inspection_findings.lineage_id`).

A. migration 0034: chain, deterministic backfill (one id per (inspection, question, finding_key)
   group, NULL question included), NOT NULL + index, nothing else touched, reversible, rendered PostgreSQL DDL;
B. reconciliation: a resolved finding confirmed again is a NEW row (new UUID) in the SAME lineage; active
   findings keep id and lineage; distinct sources / inspections get distinct lineages; the API exposes it.
Stage 7 / 11 semantics (signatures hash finding UUIDs) are unchanged and stay covered by their own suites.
"""

import importlib.util
import io
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Uuid, bindparam, create_engine, inspect, text

import app.models  # noqa: F401
from app.core.database import Base
from app.models.inspection import InspectionFinding
from tests.test_inspections import (
    _complete,
    _findings,
    _put_answers,
    _put_full_answers,
    _scaffold_inspection,
    action_url,
    auth_header,
    full_template,
)

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0034_finding_lineage.py"
INDEX = "ix_inspection_findings_lineage_id"


# ===========================================================================
# A. Migration 0034
# ===========================================================================


def load_migration():
    spec = importlib.util.spec_from_file_location("m0034", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_op(engine, fn):
    with engine.begin() as conn:
        module = load_migration()
        module.op = Operations(MigrationContext.configure(conn))
        fn(module)


def pre_migration_engine():
    """SQLite with every table of the current metadata, but inspection_findings as it was before 0034."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(f"DROP INDEX {INDEX}"))
        conn.execute(text("ALTER TABLE inspection_findings DROP COLUMN lineage_id"))
    return engine


def insert_finding(conn, *, inspection, question, key, created, active=True):
    finding_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO inspection_findings (id, inspection_id, question_id, finding_key, is_active, created_at, updated_at) "
            "VALUES (:id, :inspection, :question, :key, :active, :created, :created)"
        ).bindparams(bindparam("id", type_=Uuid()), bindparam("inspection", type_=Uuid()), bindparam("question", type_=Uuid())),
        {"id": finding_id, "inspection": inspection, "question": question, "key": key, "active": active, "created": created},
    )
    return finding_id


def lineage_rows(engine):
    with engine.connect() as conn:
        return {
            row[0]: row[1]
            for row in conn.execute(
                text("SELECT id, lineage_id FROM inspection_findings").columns(id=Uuid(), lineage_id=Uuid())
            ).all()
        }


def test_revision_chain_and_single_head():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0041_issued_documents_tech_card"]
    assert script.get_revision("0034_finding_lineage").down_revision == "0033_photo_capture_source"


def test_model_declares_the_column_not_null_and_indexed():
    column = InspectionFinding.__table__.c.lineage_id
    assert column.nullable is False
    assert any(index.name == INDEX and [c.name for c in index.columns] == ["lineage_id"] for index in InspectionFinding.__table__.indexes)


def test_backfill_gives_one_lineage_per_source_group_and_touches_nothing_else():
    engine = pre_migration_engine()
    i1, i2 = uuid.uuid4(), uuid.uuid4()
    q1, q2 = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conn:
        a = [insert_finding(conn, inspection=i1, question=q1, key="CRACK", created=f"2026-10-0{n} 10:00:00", active=n == 3) for n in (1, 2, 3)]
        b = insert_finding(conn, inspection=i1, question=q2, key="CRACK", created="2026-10-01 10:00:00")  # other question
        c = [insert_finding(conn, inspection=i1, question=None, key="NOTE", created=f"2026-10-0{n} 11:00:00", active=n == 2) for n in (1, 2)]
        d = insert_finding(conn, inspection=i2, question=q1, key="CRACK", created="2026-10-01 10:00:00")  # other inspection
        e = insert_finding(conn, inspection=i1, question=q1, key="MOLD", created="2026-10-01 10:00:00")  # other key
        before = conn.execute(text("SELECT id, is_active, created_at, finding_key FROM inspection_findings ORDER BY id")).all()

    run_op(engine, lambda m: m.upgrade())

    lineage = lineage_rows(engine)
    assert all(value is not None for value in lineage.values())
    assert lineage[a[0]] == lineage[a[1]] == lineage[a[2]]  # the same source across completions
    assert lineage[c[0]] == lineage[c[1]]  # a NULL question is a value like any other
    groups = [lineage[a[0]], lineage[b], lineage[c[0]], lineage[d], lineage[e]]
    assert len(set(groups)) == 5  # question, inspection and key all separate lineages
    with engine.connect() as conn:
        after = conn.execute(text("SELECT id, is_active, created_at, finding_key FROM inspection_findings ORDER BY id")).all()
    assert after == before  # finding UUIDs, flags, timestamps, keys untouched


def test_upgrade_makes_the_column_not_null_adds_the_index_and_downgrade_reverses_it():
    engine = pre_migration_engine()
    with engine.begin() as conn:
        finding = insert_finding(conn, inspection=uuid.uuid4(), question=None, key="X", created="2026-10-01 10:00:00")
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    columns = {c["name"]: c for c in insp.get_columns("inspection_findings")}
    assert columns["lineage_id"]["nullable"] is False
    assert INDEX in {i["name"] for i in insp.get_indexes("inspection_findings")}

    run_op(engine, lambda m: m.downgrade())
    insp = inspect(engine)
    assert "lineage_id" not in {c["name"] for c in insp.get_columns("inspection_findings")}
    assert INDEX not in {i["name"] for i in insp.get_indexes("inspection_findings")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM inspection_findings")).scalar_one() == 1

    run_op(engine, lambda m: m.upgrade())  # up / down / up
    assert lineage_rows(engine)[finding] is not None


def test_upgrade_on_an_empty_table_and_without_other_changes():
    engine = pre_migration_engine()
    tables_before = {t: [c["name"] for c in inspect(engine).get_columns(t)] for t in inspect(engine).get_table_names() if t != "inspection_findings"}
    run_op(engine, lambda m: m.upgrade())
    tables_after = {t: [c["name"] for c in inspect(engine).get_columns(t)] for t in inspect(engine).get_table_names() if t != "inspection_findings"}
    assert tables_after == tables_before


def test_rendered_postgresql_ddl():
    module = load_migration()
    module._backfill_lineage = lambda: None  # the backfill needs a live database; the DDL around it is what is rendered
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    module.op = Operations(context)
    module.upgrade()
    up = " ".join(buffer.getvalue().split())
    assert "ALTER TABLE inspection_findings ADD COLUMN lineage_id UUID" in up
    assert "ALTER TABLE inspection_findings ALTER COLUMN lineage_id SET NOT NULL" in up
    assert f"CREATE INDEX {INDEX} ON inspection_findings (lineage_id)" in up
    assert up.index("ADD COLUMN") < up.index("SET NOT NULL") < up.index("CREATE INDEX")

    buffer = io.StringIO()
    module.op = Operations(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer}))
    module.downgrade()
    down = " ".join(buffer.getvalue().split())
    assert f"DROP INDEX {INDEX}" in down
    assert "ALTER TABLE inspection_findings DROP COLUMN lineage_id" in down
    assert "DROP TABLE" not in down


# ===========================================================================
# B. Reconciliation
# ===========================================================================


async def _rework(async_client, token, project, room, inspection, template, **answers):
    response = await async_client.post(action_url(project["id"], room["id"], inspection["id"], "reopen"), headers=auth_header(token))
    assert response.status_code == 200, response.text
    await _put_answers(async_client, token, project, room, inspection, template, **answers)
    done = await _complete(async_client, token, project, room, inspection)
    assert done.status_code == 200, done.text


async def _all(async_client, token, project, room, inspection):
    return await _findings(async_client, token, project, room, inspection, include_inactive=True)


async def test_api_exposes_the_lineage_of_every_finding(async_client):
    token, project, room, inspection = await _scaffold_inspection(async_client)
    template = await full_template(async_client, token, inspection["template_id"])
    await _put_full_answers(async_client, token, project, room, inspection, template)
    assert (await _complete(async_client, token, project, room, inspection)).status_code == 200
    items = await _findings(async_client, token, project, room, inspection)
    assert items
    lineages = [item["lineage_id"] for item in items]
    assert all(uuid.UUID(value) for value in lineages)
    assert len(set(lineages)) == len(lineages)  # distinct sources, distinct lineages


async def test_resolved_then_confirmed_again_is_a_new_finding_in_the_same_lineage(async_client):
    token, project, room, inspection = await _scaffold_inspection(async_client)
    template = await full_template(async_client, token, inspection["template_id"])
    await _put_full_answers(async_client, token, project, room, inspection, template)
    assert (await _complete(async_client, token, project, room, inspection)).status_code == 200
    first = {f["finding_key"]: f for f in await _findings(async_client, token, project, room, inspection)}
    crack, unevenness = first["CRACK"], first["UNEVENNESS"]

    # Round 2: cracks gone (resolved), unevenness still there.
    await _rework(async_client, token, project, room, inspection, template, cracks=False, unevenness="1.0")
    everything = await _all(async_client, token, project, room, inspection)
    resolved_crack = next(f for f in everything if f["id"] == crack["id"])
    assert resolved_crack["is_active"] is False
    assert resolved_crack["lineage_id"] == crack["lineage_id"]  # a resolved row keeps its lineage

    # Round 3: the cracks are back.
    await _rework(async_client, token, project, room, inspection, template, cracks=True, unevenness="1.0")
    everything = await _all(async_client, token, project, room, inspection)
    cracks = [f for f in everything if f["finding_key"] == "CRACK" and f["question_id"] == crack["question_id"]]
    assert len(cracks) == 2
    old = next(f for f in cracks if f["id"] == crack["id"])
    new = next(f for f in cracks if f["id"] != crack["id"])
    assert old["is_active"] is False and new["is_active"] is True
    assert new["id"] != old["id"]  # a new row: finding UUIDs (Stage 7 / 11 signatures) are not revived
    assert new["lineage_id"] == old["lineage_id"] == crack["lineage_id"]  # ... but the same finding for evidence purposes

    # The finding that stayed confirmed all along kept both its row and its lineage.
    still = next(f for f in everything if f["id"] == unevenness["id"])
    assert still["is_active"] is True and still["lineage_id"] == unevenness["lineage_id"]
    # No other finding shares the cracks' lineage.
    assert [f["id"] for f in everything if f["lineage_id"] == crack["lineage_id"]] and {f["finding_key"] for f in everything if f["lineage_id"] == crack["lineage_id"]} == {"CRACK"}


async def test_a_new_inspection_of_the_same_place_starts_new_lineages(async_client):
    token, project, room, first_inspection = await _scaffold_inspection(async_client)
    template = await full_template(async_client, token, first_inspection["template_id"])
    await _put_full_answers(async_client, token, project, room, first_inspection, template)
    assert (await _complete(async_client, token, project, room, first_inspection)).status_code == 200
    first = await _findings(async_client, token, project, room, first_inspection)

    from tests.test_inspections import inspections_url

    created = await async_client.post(
        inspections_url(project["id"], room["id"]),
        json={"template_id": first_inspection["template_id"], "substrate": first_inspection["substrate"], "plane": first_inspection["plane"]},
        headers=auth_header(token),
    )
    assert created.status_code == 201, created.text
    second_inspection = created.json()
    await _put_full_answers(async_client, token, project, room, second_inspection, template)
    assert (await _complete(async_client, token, project, room, second_inspection)).status_code == 200
    second = await _findings(async_client, token, project, room, second_inspection)

    assert second
    assert not ({f["lineage_id"] for f in first} & {f["lineage_id"] for f in second})


@pytest.mark.parametrize("round_trips", [1, 3])
async def test_repeated_resolve_and_confirm_cycles_keep_one_lineage(async_client, round_trips):
    token, project, room, inspection = await _scaffold_inspection(async_client)
    template = await full_template(async_client, token, inspection["template_id"])
    await _put_full_answers(async_client, token, project, room, inspection, template)
    assert (await _complete(async_client, token, project, room, inspection)).status_code == 200
    crack = next(f for f in await _findings(async_client, token, project, room, inspection) if f["finding_key"] == "CRACK")
    for _ in range(round_trips):
        await _rework(async_client, token, project, room, inspection, template, cracks=False, unevenness="1.0")
        await _rework(async_client, token, project, room, inspection, template, cracks=True, unevenness="1.0")
    rows = [f for f in await _all(async_client, token, project, room, inspection) if f["lineage_id"] == crack["lineage_id"]]
    assert len(rows) == 1 + round_trips
    assert sum(1 for f in rows if f["is_active"]) == 1
    assert len({f["id"] for f in rows}) == len(rows)


async def test_the_most_recent_row_of_a_source_decides_the_lineage(async_client, db_session):
    """Rows of one source always share a lineage; if that invariant were ever broken by hand, the newest row wins."""
    from sqlalchemy import update

    token, project, room, inspection = await _scaffold_inspection(async_client)
    template = await full_template(async_client, token, inspection["template_id"])
    await _put_full_answers(async_client, token, project, room, inspection, template)
    assert (await _complete(async_client, token, project, room, inspection)).status_code == 200
    crack = next(f for f in await _findings(async_client, token, project, room, inspection) if f["finding_key"] == "CRACK")
    await _rework(async_client, token, project, room, inspection, template, cracks=False, unevenness="1.0")
    await _rework(async_client, token, project, room, inspection, template, cracks=True, unevenness="1.0")  # second CRACK row
    await _rework(async_client, token, project, room, inspection, template, cracks=False, unevenness="1.0")

    stray = uuid.uuid4()
    await db_session.execute(update(InspectionFinding).where(InspectionFinding.id == uuid.UUID(crack["id"])).values(lineage_id=stray))
    await db_session.commit()

    await _rework(async_client, token, project, room, inspection, template, cracks=True, unevenness="1.0")  # third CRACK row
    rows = [f for f in await _all(async_client, token, project, room, inspection) if f["finding_key"] == "CRACK" and f["question_id"] == crack["question_id"]]
    newest = next(f for f in rows if f["is_active"])
    assert len(rows) == 3
    assert newest["lineage_id"] != str(stray)  # not the oldest row's (tampered) lineage
    assert newest["lineage_id"] == next(f for f in rows if f["id"] != crack["id"] and not f["is_active"])["lineage_id"]  # the second row's
