"""floor substrates: SCREED, OLD_TILE, WOOD_BOARDS (UX walk B4, owner 2026-10-29 "стяжка, старая плитка, доски")

Revision ID: 0089_floor_substrates
Revises: 0088_owner_contract_terms
Create Date: 2026-10-29 21:00:00.000000

Three NEW values of the PostgreSQL enum `substrate` (shared by checklist templates, inspections, risk rules, communication phrases and the work plans of a wall and of a
room). PostgreSQL: committed before use (`ADD VALUE` cannot be used in the transaction that adds it), as in 0059 and 0077; elsewhere the column is a plain string. No existing row
changes. The checklists of the three substrates are not seeded here: like every checklist they are made by the catalogue bootstrap on its first read.

Reversible: the downgrade **refuses** while an inspection or a work plan has one of the new substrates (they are the owner's own input and are never dropped silently); otherwise it
removes the three bootstrapped checklists (sections, questions and options with them). The values of the PostgreSQL enum stay (a value cannot be taken out of an enum without
rebuilding it, and an unused one is harmless), as in 0059 and 0077.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0089_floor_substrates"
down_revision: str | None = "0088_owner_contract_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_SUBSTRATES = ("SCREED", "OLD_TILE", "WOOD_BOARDS")
IN_LIST = ", ".join(f"'{value}'" for value in NEW_SUBSTRATES)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for value in NEW_SUBSTRATES:
                op.execute(f"ALTER TYPE substrate ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    bind = op.get_bind()
    used = {
        table: bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE CAST(substrate AS TEXT) IN ({IN_LIST})")).scalar_one()
        for table in ("inspections", "room_work_plans", "surface_work_plans")
    }
    if any(used.values()):
        raise RuntimeError(
            f"cannot downgrade: rows with a floor substrate exist ({used}); they are the owner's own input and are never dropped silently"
        )
    template_ids = f"SELECT id FROM checklist_templates WHERE CAST(substrate AS TEXT) IN ({IN_LIST})"
    in_use = bind.execute(sa.text(f"SELECT count(*) FROM inspections WHERE template_id IN ({template_ids})")).scalar_one()
    if in_use:
        raise RuntimeError(f"cannot downgrade: {in_use} inspection(s) use a checklist of a floor substrate")
    bind.execute(sa.text(f"DELETE FROM checklist_options WHERE question_id IN (SELECT id FROM checklist_questions WHERE template_id IN ({template_ids}))"))
    bind.execute(sa.text(f"DELETE FROM checklist_questions WHERE template_id IN ({template_ids})"))
    bind.execute(sa.text(f"DELETE FROM checklist_sections WHERE template_id IN ({template_ids})"))
    bind.execute(sa.text(f"DELETE FROM checklist_templates WHERE CAST(substrate AS TEXT) IN ({IN_LIST})"))
