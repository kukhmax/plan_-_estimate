"""Stage 14C.2 — photo_attachments schema: migration 0032, CHECKs, partial
unique indexes and FK behaviour (docs/STAGE_14C_MEDIA_API_CONTRACT.md §4–§8).

SQLite executes the real migration and is compared with the model; the
PostgreSQL DDL is rendered offline. The final PostgreSQL 16 proof is the
owner-run scratch-database verification.
"""

import importlib.util
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401
from app.core.database import Base
from app.models.checklist import AnswerType, ChecklistQuestion
from app.models.inspection import Inspection, InspectionFinding
from app.models.opening import Opening
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import (
    ACTIVE_UNIQUE_INDEXES,
    CONTEXT_TARGETS_CHECK,
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
from tests.test_estimates import _make_opening, _make_price_item, _make_project, _make_room, _make_surface, _make_user
from tests.test_stage14b4_photo_asset import raw_asset
from tests.test_work_recommendation_accept import _make_inspection, _make_template

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0032_photo_attachments.py"
C = PhotoAttachmentContext


# ===========================================================================
# A. Migration 0032
# ===========================================================================


def load_migration():
    spec = importlib.util.spec_from_file_location("m0032", MIGRATION)
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
    tables = [t for t in Base.metadata.sorted_tables if t.name != "photo_attachments"]
    Base.metadata.create_all(engine, tables=tables)
    return engine


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _index_sql(engine) -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='photo_attachments'")
        ).all()
    return {name: _normalize(sql) for name, sql in rows if sql}


def test_revision_chain_and_single_head():
    module = load_migration()
    assert module.revision == "0032_photo_attachments"
    assert module.down_revision == "0031_photo_assets"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    # Stage 14E.2 added 0033, 14F.1 0034, 14G.1 0035, 14G.4 0036, 15C 0037 and 15F 0038 on top; 0032 must stay 0033's direct parent (single linear chain).
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0047_handover_protocols"]
    assert scripts.get_revision("0034_finding_lineage").down_revision == "0033_photo_capture_source"
    assert scripts.get_revision("0033_photo_capture_source").down_revision == "0032_photo_attachments"


def test_enum_values_are_exact():
    module = load_migration()
    assert module.CONTEXTS == ("PROJECT", "ROOM", "SURFACE", "OPENING", "INSPECTION", "FINDING", "WORK")
    assert module.CATEGORIES == (
        "GENERAL", "BEFORE", "DEFECT", "PREPARATION", "IN_PROGRESS", "HIDDEN_WORK", "AFTER", "DAMAGE",
    )
    assert tuple(m.value for m in PhotoAttachmentContext) == module.CONTEXTS
    assert tuple(m.value for m in PhotoCategory) == module.CATEGORIES


def test_upgrade_matches_model_and_downgrade_removes_only_the_table():
    engine = fresh_engine()
    before = set(inspect(engine).get_table_names())
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    model = Base.metadata.tables["photo_attachments"]

    columns = {c["name"]: c for c in insp.get_columns("photo_attachments")}
    assert set(columns) == set(model.columns.keys())
    for name, col in model.columns.items():
        assert columns[name]["nullable"] == col.nullable, name

    indexes = {i["name"]: bool(i["unique"]) for i in insp.get_indexes("photo_attachments")}
    assert indexes == {i.name: bool(i.unique) for i in model.indexes}
    assert sum(indexes.values()) == 8

    checks = {c["name"] for c in insp.get_check_constraints("photo_attachments")}
    assert checks == {"ck_photo_attachments_context_targets", "ck_photo_attachments_position_nonneg"}

    fks = {
        (fk["constrained_columns"][0], fk["referred_table"], fk["options"].get("ondelete"))
        for fk in insp.get_foreign_keys("photo_attachments")
    }
    assert fks == {
        ("asset_id", "photo_assets", "RESTRICT"),
        ("project_id", "projects", "RESTRICT"),
        ("room_id", "rooms", "RESTRICT"),
        ("surface_id", "surfaces", "RESTRICT"),
        ("opening_id", "openings", "RESTRICT"),
        ("inspection_id", "inspections", "RESTRICT"),
        ("question_id", "checklist_questions", "RESTRICT"),  # R-2: not SET NULL
        ("finding_id", "inspection_findings", "RESTRICT"),
        ("price_item_id", "price_items", "RESTRICT"),
    }  # occurrence_key: no FK

    # Partial-index predicates and the CHECK text are identical to the model's.
    migrated_indexes = _index_sql(engine)
    model_engine = create_engine("sqlite://")
    Base.metadata.create_all(model_engine)
    assert migrated_indexes == _index_sql(model_engine)
    for name, _cols, predicate in ACTIVE_UNIQUE_INDEXES:
        assert migrated_indexes[name].endswith(f"WHERE {predicate} AND archived_at IS NULL")

    def table_sql(e):
        with e.connect() as conn:
            return _normalize(conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='photo_attachments'")
            ).scalar_one())

    migrated_table = table_sql(engine)
    model_table = table_sql(model_engine)
    fragments = re.findall(r"CONSTRAINT \w+ CHECK \(.*?\)\)?(?=, CONSTRAINT|, FOREIGN|\)$)", model_table)
    # Non-vacuous: exactly the two named CHECKs, each captured in full (not a truncated prefix).
    assert fragments == [
        f"CONSTRAINT ck_photo_attachments_context_targets CHECK ({_normalize(CONTEXT_TARGETS_CHECK)})",
        "CONSTRAINT ck_photo_attachments_position_nonneg CHECK (position >= 0)",
    ]
    assert _normalize(load_migration().CONTEXT_TARGETS_CHECK) == _normalize(CONTEXT_TARGETS_CHECK)
    for fragment in fragments:
        assert fragment in migrated_table

    run_op(engine, lambda m: m.downgrade())
    assert set(inspect(engine).get_table_names()) == before
    run_op(engine, lambda m: m.upgrade())
    assert "photo_attachments" in inspect(engine).get_table_names()


def test_upgrade_does_not_alter_existing_tables():
    engine = fresh_engine()
    insp = inspect(engine)
    snapshot = {t: [c["name"] for c in insp.get_columns(t)] for t in insp.get_table_names()}
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    after = {t: [c["name"] for c in insp.get_columns(t)] for t in insp.get_table_names() if t != "photo_attachments"}
    assert after == snapshot


def _offline_sql(*args: str) -> str:
    env = dict(os.environ, DATABASE_URL="postgresql+asyncpg://offline:offline@localhost:1/offline")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args, "--sql"],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True,
    ).stdout


def test_rendered_postgresql_ddl():
    up = _offline_sql("upgrade", "0031_photo_assets:0032_photo_attachments")
    assert (
        "CREATE TYPE photoattachmentcontext AS ENUM "
        "('PROJECT', 'ROOM', 'SURFACE', 'OPENING', 'INSPECTION', 'FINDING', 'WORK')"
    ) in up
    assert (
        "CREATE TYPE photocategory AS ENUM ('GENERAL', 'BEFORE', 'DEFECT', 'PREPARATION', "
        "'IN_PROGRESS', 'HIDDEN_WORK', 'AFTER', 'DAMAGE')"
    ) in up
    assert "REFERENCES checklist_questions (id) ON DELETE RESTRICT" in up
    assert "SET NULL" not in up and "CASCADE" not in up
    assert up.count("ON DELETE RESTRICT") == 9
    assert "include_in_report BOOLEAN DEFAULT false NOT NULL" in up
    assert "position INTEGER DEFAULT 0 NOT NULL" in up
    assert "caption VARCHAR(1000)," in up
    assert "archived_at TIMESTAMP WITH TIME ZONE," in up
    assert "CONSTRAINT ck_photo_attachments_context_targets CHECK" in up
    assert "CONSTRAINT ck_photo_attachments_position_nonneg CHECK (position >= 0)" in up
    for name, _cols, predicate in ACTIVE_UNIQUE_INDEXES:
        assert re.search(
            rf"CREATE UNIQUE INDEX {name} ON photo_attachments \([^)]*\) "
            rf"WHERE {re.escape(predicate)} AND archived_at IS NULL",
            up,
        ), name
    assert "ALTER TABLE photo_assets" not in up
    down = _offline_sql("downgrade", "0032_photo_attachments:0031_photo_assets")
    assert "DROP TABLE photo_attachments" in down and down.count("DROP TABLE") == 1
    assert "DROP TYPE IF EXISTS photocategory" in down
    assert "DROP TYPE IF EXISTS photoattachmentcontext" in down


# ===========================================================================
# B. Constraint behaviour (model schema, SQLite with FKs enforced)
# ===========================================================================


async def world(db, tg: int = 7001) -> SimpleNamespace:
    user = await _make_user(db, tg)
    project = await _make_project(db, user.id)
    room = await _make_room(db, project.id)
    surface = await _make_surface(db, room.id)
    opening = await _make_opening(db, surface.id)
    template = await _make_template(db)
    question = ChecklistQuestion(
        template_id=template.id, position=1, key="q1", text_key="q.one", answer_type=AnswerType.BOOLEAN
    )
    question2 = ChecklistQuestion(
        template_id=template.id, position=2, key="q2", text_key="q.two", answer_type=AnswerType.BOOLEAN
    )
    db.add_all([question, question2])
    await db.commit()
    inspection = await _make_inspection(db, room.id, template.id)
    finding = InspectionFinding(inspection_id=inspection.id, question_id=question.id, finding_key="cracks")
    db.add(finding)
    await db.commit()
    price_item = await _make_price_item(db, user.id)
    asset = raw_asset(user, project, status=PhotoAssetStatus.READY)
    asset2 = raw_asset(user, project, status=PhotoAssetStatus.READY)
    db.add_all([asset, asset2])
    await db.commit()
    return SimpleNamespace(
        user_id=user.id, project_id=project.id, room_id=room.id, surface_id=surface.id,
        opening_id=opening.id, template_id=template.id, question_id=question.id,
        question2_id=question2.id, inspection_id=inspection.id, finding_id=finding.id,
        price_item_id=price_item.id, asset_id=asset.id, asset2_id=asset2.id,
    )


def targets(w) -> dict[PhotoAttachmentContext, dict]:
    return {
        C.PROJECT: {},
        C.ROOM: {"room_id": w.room_id},
        C.SURFACE: {"surface_id": w.surface_id},
        C.OPENING: {"opening_id": w.opening_id},
        C.INSPECTION: {"inspection_id": w.inspection_id},
        C.FINDING: {"finding_id": w.finding_id},
        C.WORK: {"surface_id": w.surface_id, "occurrence_key": uuid.UUID(int=42), "price_item_id": w.price_item_id},
    }


def attachment(w, context, asset_id=None, **fields) -> PhotoAttachment:
    return PhotoAttachment(
        asset_id=asset_id or w.asset_id, project_id=w.project_id, context=context,
        category=fields.pop("category", PhotoCategory.GENERAL), **fields,
    )


async def insert_ok(db, row) -> uuid.UUID:
    db.add(row)
    await db.commit()
    return row.id


async def rejected(db, row) -> bool:
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return True
    await db.rollback()
    return False


@pytest.mark.parametrize("context", list(C))
async def test_every_context_branch_accepts_its_valid_shape(db_session, context):
    w = await world(db_session)
    row_id = await insert_ok(db_session, attachment(w, context, **targets(w)[context]))
    row = (await db_session.execute(select(PhotoAttachment).where(PhotoAttachment.id == row_id))).scalar_one()
    assert row.context is context
    assert row.include_in_report is False and row.position == 0 and row.archived_at is None


async def test_inspection_branch_accepts_optional_question(db_session):
    w = await world(db_session)
    await insert_ok(db_session, attachment(w, C.INSPECTION, inspection_id=w.inspection_id, question_id=w.question_id))


INVALID_SHAPES = [
    ("project with room", C.PROJECT, lambda w: {"room_id": w.room_id}),
    ("project with occurrence_key", C.PROJECT, lambda w: {"occurrence_key": uuid.uuid4()}),
    ("room without room", C.ROOM, lambda w: {}),
    ("room with surface", C.ROOM, lambda w: {"room_id": w.room_id, "surface_id": w.surface_id}),
    ("surface without surface", C.SURFACE, lambda w: {"room_id": w.room_id}),
    ("surface with occurrence_key", C.SURFACE, lambda w: {"surface_id": w.surface_id, "occurrence_key": uuid.uuid4()}),
    ("opening without opening", C.OPENING, lambda w: {"surface_id": w.surface_id}),
    ("opening with room", C.OPENING, lambda w: {"opening_id": w.opening_id, "room_id": w.room_id}),
    ("inspection without inspection", C.INSPECTION, lambda w: {"question_id": w.question_id}),
    ("inspection with finding", C.INSPECTION, lambda w: {"inspection_id": w.inspection_id, "finding_id": w.finding_id}),
    ("finding without finding", C.FINDING, lambda w: {"inspection_id": w.inspection_id}),
    ("finding with question", C.FINDING, lambda w: {"finding_id": w.finding_id, "question_id": w.question_id}),
    ("work without occurrence_key", C.WORK, lambda w: {"surface_id": w.surface_id, "price_item_id": w.price_item_id}),
    ("work without price_item", C.WORK, lambda w: {"surface_id": w.surface_id, "occurrence_key": uuid.uuid4()}),
    ("work without surface", C.WORK, lambda w: {"occurrence_key": uuid.uuid4(), "price_item_id": w.price_item_id}),
    (
        "work with room",
        C.WORK,
        lambda w: {
            "surface_id": w.surface_id, "occurrence_key": uuid.uuid4(),
            "price_item_id": w.price_item_id, "room_id": w.room_id,
        },
    ),
]


@pytest.mark.parametrize(("label", "context", "fields"), INVALID_SHAPES, ids=[s[0] for s in INVALID_SHAPES])
async def test_invalid_target_combinations_are_rejected(db_session, label, context, fields):
    w = await world(db_session)
    assert await rejected(db_session, attachment(w, context, **fields(w))), label


async def test_negative_position_rejected(db_session):
    w = await world(db_session)
    assert await rejected(db_session, attachment(w, C.PROJECT, position=-1))


@pytest.mark.parametrize("context", list(C))
async def test_active_duplicate_rejected_and_archived_duplicate_allowed(db_session, context):
    w = await world(db_session)
    shape = targets(w)[context]
    await insert_ok(db_session, attachment(w, context, **shape))
    assert await rejected(db_session, attachment(w, context, **shape))
    # another asset on the same target is fine
    await insert_ok(db_session, attachment(w, context, asset_id=w.asset2_id, **shape))
    # an archived duplicate never blocks, and a new active one is allowed after archiving
    await insert_ok(db_session, attachment(w, context, archived_at=datetime.now(timezone.utc), **shape))
    await db_session.execute(
        PhotoAttachment.__table__.update()
        .where(PhotoAttachment.asset_id == w.asset_id, PhotoAttachment.archived_at.is_(None))
        .values(archived_at=datetime.now(timezone.utc))
    )
    await db_session.commit()
    await insert_ok(db_session, attachment(w, context, **shape))


async def test_inspection_level_uniqueness(db_session):
    w = await world(db_session)
    await insert_ok(db_session, attachment(w, C.INSPECTION, inspection_id=w.inspection_id))
    assert await rejected(db_session, attachment(w, C.INSPECTION, inspection_id=w.inspection_id))


async def test_question_level_uniqueness(db_session):
    w = await world(db_session)
    shape = {"inspection_id": w.inspection_id, "question_id": w.question_id}
    await insert_ok(db_session, attachment(w, C.INSPECTION, **shape))
    assert await rejected(db_session, attachment(w, C.INSPECTION, **shape))


async def test_inspection_and_question_levels_coexist(db_session):
    w = await world(db_session)
    await insert_ok(db_session, attachment(w, C.INSPECTION, inspection_id=w.inspection_id))
    await insert_ok(db_session, attachment(w, C.INSPECTION, inspection_id=w.inspection_id, question_id=w.question_id))
    await insert_ok(db_session, attachment(w, C.INSPECTION, inspection_id=w.inspection_id, question_id=w.question2_id))
    assert await rejected(
        db_session, attachment(w, C.INSPECTION, inspection_id=w.inspection_id, question_id=w.question2_id)
    )


async def test_work_uniqueness_is_per_occurrence_key(db_session):
    w = await world(db_session)
    base = {"surface_id": w.surface_id, "price_item_id": w.price_item_id}
    await insert_ok(db_session, attachment(w, C.WORK, occurrence_key=uuid.UUID(int=1), **base))
    await insert_ok(db_session, attachment(w, C.WORK, occurrence_key=uuid.UUID(int=2), **base))
    assert await rejected(db_session, attachment(w, C.WORK, occurrence_key=uuid.UUID(int=1), **base))


# FK RESTRICT: (label, model, world attribute, attachment context, fields)
RESTRICT_CASES = [
    ("asset", PhotoAsset, "asset_id", C.PROJECT, lambda w: {}),
    ("project", Project, "project_id", C.PROJECT, lambda w: {}),
    ("room", Room, "room_id", C.ROOM, lambda w: {"room_id": w.room_id}),
    ("surface", Surface, "surface_id", C.SURFACE, lambda w: {"surface_id": w.surface_id}),
    ("opening", Opening, "opening_id", C.OPENING, lambda w: {"opening_id": w.opening_id}),
    ("inspection", Inspection, "inspection_id", C.INSPECTION, lambda w: {"inspection_id": w.inspection_id}),
    (
        "question",
        ChecklistQuestion,
        "question_id",
        C.INSPECTION,
        lambda w: {"inspection_id": w.inspection_id, "question_id": w.question_id},
    ),
    ("finding", InspectionFinding, "finding_id", C.FINDING, lambda w: {"finding_id": w.finding_id}),
    (
        "price_item",
        PriceItem,
        "price_item_id",
        C.WORK,
        lambda w: {"surface_id": w.surface_id, "occurrence_key": uuid.uuid4(), "price_item_id": w.price_item_id},
    ),
]


@pytest.mark.parametrize(
    ("label", "model", "attr", "context", "fields"), RESTRICT_CASES, ids=[c[0] for c in RESTRICT_CASES]
)
async def test_evidence_parent_delete_is_restricted(db_session, label, model, attr, context, fields):
    w = await world(db_session)
    row_id = await insert_ok(db_session, attachment(w, context, **fields(w)))
    parent_id = getattr(w, attr)
    if label == "question":  # the finding also references the question (SET NULL) -- detach it first
        await db_session.execute(
            InspectionFinding.__table__.update().where(InspectionFinding.id == w.finding_id).values(question_id=None)
        )
        await db_session.commit()
    with pytest.raises(IntegrityError):
        await db_session.execute(delete(model).where(model.id == parent_id))
        await db_session.flush()
    await db_session.rollback()
    row = (
        await db_session.execute(
            select(PhotoAttachment).where(PhotoAttachment.id == row_id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    if label in {"room", "surface", "opening", "inspection", "question", "finding", "price_item"}:
        column = attr
        assert getattr(row, column) == parent_id  # never silently nulled (R-2)
