"""Stage 14B.4 — migration 0031_photo_assets.

SQLite executes the real upgrade/downgrade functions and the result is
compared with the model metadata; the PostgreSQL DDL is rendered offline.
The final PostgreSQL 16 up/down/up proof is the owner-run scratch-database
check (docs/STAGE_14B_MEDIA_INFRASTRUCTURE_PLAN.md §24).
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from app.core.database import Base

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0031_photo_assets.py"


def load_migration():
    spec = importlib.util.spec_from_file_location("m0031", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_op(engine, fn):
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        module = load_migration()
        module.op = op  # the migration module uses `from alembic import op`
        fn(module)


def fresh_engine():
    engine = create_engine("sqlite://")
    # photo_attachments (0032) is a later revision that depends on photo_assets.
    tables = [t for t in Base.metadata.sorted_tables if t.name not in {"photo_assets", "photo_attachments"}]
    Base.metadata.create_all(engine, tables=tables)
    return engine


def test_revision_chain_and_single_head():
    module = load_migration()
    assert module.revision == "0031_photo_assets"
    assert module.down_revision == "0030_surface_work_executions"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))  # independent of the cwd
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1  # later revisions (0032+) build on 0031 without branching
    chain = [rev.revision for rev in script.walk_revisions(base="base", head=heads[0])]
    assert "0031_photo_assets" in chain


def test_upgrade_creates_schema_matching_model_and_downgrade_removes_it():
    engine = fresh_engine()
    before = set(inspect(engine).get_table_names())
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    assert "photo_assets" in insp.get_table_names()

    model = Base.metadata.tables["photo_assets"]
    columns = {c["name"]: c for c in insp.get_columns("photo_assets")}
    # `capture_source` and its CHECK are added by the later revision 0033 (Stage 14E.2), not by 0031.
    later_columns = {"capture_source"}
    assert set(columns) == set(model.columns.keys()) - later_columns
    for name, col in model.columns.items():
        if name not in later_columns:
            assert columns[name]["nullable"] == col.nullable, name

    indexes = {i["name"]: bool(i["unique"]) for i in insp.get_indexes("photo_assets")}
    model_indexes = {i.name: bool(i.unique) for i in model.indexes}
    assert indexes == model_indexes

    checks = {c["name"] for c in insp.get_check_constraints("photo_assets")}
    portable_model_checks = {
        c.name for c in model.constraints
        if c.__class__.__name__ == "CheckConstraint"
        and c.name not in {"ck_photo_assets_sha256_hex", "ck_photo_assets_capture_source"}
    }
    assert portable_model_checks <= checks

    fks = {(fk["referred_table"], fk["options"].get("ondelete")) for fk in insp.get_foreign_keys("photo_assets")}
    assert fks == {("users", "RESTRICT"), ("projects", "RESTRICT")}

    run_op(engine, lambda m: m.downgrade())
    assert set(inspect(engine).get_table_names()) == before  # nothing else touched
    run_op(engine, lambda m: m.upgrade())  # up again
    assert "photo_assets" in inspect(engine).get_table_names()


def test_upgrade_does_not_alter_existing_tables():
    engine = fresh_engine()
    insp = inspect(engine)
    snapshot = {t: [c["name"] for c in insp.get_columns(t)] for t in insp.get_table_names()}
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    after = {t: [c["name"] for c in insp.get_columns(t)] for t in insp.get_table_names() if t != "photo_assets"}
    assert after == snapshot


def _offline_sql(*args: str) -> str:
    env = dict(os.environ, DATABASE_URL="postgresql+asyncpg://offline:offline@localhost:1/offline")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args, "--sql"],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True,
    ).stdout


def test_rendered_postgresql_ddl():
    up = _offline_sql("upgrade", "0030_surface_work_executions:0031_photo_assets")
    assert "CREATE TYPE photoassetstatus AS ENUM ('PENDING', 'READY', 'FAILED')" in up
    assert "CREATE TYPE photocontenttype AS ENUM ('image/jpeg', 'image/png', 'image/webp')" in up
    assert "captured_at TIMESTAMP WITHOUT TIME ZONE," in up
    for col in ("uploaded_at", "created_at", "updated_at"):
        assert f"{col} TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in up
    assert "archived_at TIMESTAMP WITH TIME ZONE," in up
    assert "sha256 CHAR(64) NOT NULL" in up
    assert "byte_size BIGINT NOT NULL" in up and "thumbnail_byte_size BIGINT NOT NULL" in up
    assert "storage_name VARCHAR(40) NOT NULL" in up
    assert "CHECK (sha256 ~ '^[0-9a-f]{64}$')" in up
    assert "REFERENCES users (id) ON DELETE RESTRICT" in up
    assert "REFERENCES projects (id) ON DELETE RESTRICT" in up
    assert "ALTER TABLE surface" not in up and "inspection_findings" not in up
    down = _offline_sql("downgrade", "0031_photo_assets:0030_surface_work_executions")
    assert "DROP TABLE photo_assets" in down
    assert "DROP TYPE IF EXISTS photocontenttype" in down and "DROP TYPE IF EXISTS photoassetstatus" in down
    assert down.count("DROP TABLE") == 1
