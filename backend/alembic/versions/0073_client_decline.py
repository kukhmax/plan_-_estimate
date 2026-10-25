"""V2-8b: the client may decline an estimate, and give a reason -- client_consents.kind ESTIMATE_DECLINED and client_consents.comment

Revision ID: 0073_client_decline
Revises: 0072_client_links
Create Date: 2026-10-26 12:00:00.000000

Changes ONE table, `client_consents`, and only adds: the allowed kinds gain ESTIMATE_DECLINED (the check of the subject says an estimate decision
points at an estimate and a proposal decision at a proposal), and a nullable ciphertext column `comment` holds the reason of a refusal (only a
refusal may carry one). No existing row changes.

Reversible: the downgrade deletes the rows of kind ESTIMATE_DECLINED (the older schema has no place for them) and drops the column (the reasons are
lost with it), then restores the two earlier checks.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_client_decline"
down_revision: str | None = "0072_client_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KIND = "kind IN ('ESTIMATE_ACCEPTED', 'PROPOSAL_ACCEPTED', 'PROPOSAL_DECLINED')"
OLD_SUBJECT = (
    "(kind = 'ESTIMATE_ACCEPTED' AND estimate_id IS NOT NULL AND proposal_id IS NULL)"
    " OR (kind <> 'ESTIMATE_ACCEPTED' AND proposal_id IS NOT NULL)"
)
NEW_KIND = "kind IN ('ESTIMATE_ACCEPTED', 'ESTIMATE_DECLINED', 'PROPOSAL_ACCEPTED', 'PROPOSAL_DECLINED')"
NEW_SUBJECT = (
    "(kind IN ('ESTIMATE_ACCEPTED', 'ESTIMATE_DECLINED') AND estimate_id IS NOT NULL AND proposal_id IS NULL)"
    " OR (kind IN ('PROPOSAL_ACCEPTED', 'PROPOSAL_DECLINED') AND proposal_id IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column("client_consents", sa.Column("comment", sa.Text(), nullable=True))
    op.drop_constraint("ck_client_consents_kind", "client_consents", type_="check")
    op.drop_constraint("ck_client_consents_subject", "client_consents", type_="check")
    op.create_check_constraint("ck_client_consents_kind", "client_consents", NEW_KIND)
    op.create_check_constraint("ck_client_consents_subject", "client_consents", NEW_SUBJECT)
    op.create_check_constraint(
        "ck_client_consents_comment_on_decline", "client_consents", "comment IS NULL OR kind IN ('ESTIMATE_DECLINED', 'PROPOSAL_DECLINED')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_client_consents_comment_on_decline", "client_consents", type_="check")
    op.drop_constraint("ck_client_consents_subject", "client_consents", type_="check")
    op.drop_constraint("ck_client_consents_kind", "client_consents", type_="check")
    op.execute("DELETE FROM client_consents WHERE kind = 'ESTIMATE_DECLINED'")
    op.create_check_constraint("ck_client_consents_kind", "client_consents", OLD_KIND)
    op.create_check_constraint("ck_client_consents_subject", "client_consents", OLD_SUBJECT)
    op.drop_column("client_consents", "comment")
