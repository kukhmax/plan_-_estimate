"""create clients table

Revision ID: 0002_create_clients
Revises: 0001_create_users
Create Date: 2026-09-08 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002_create_clients'
down_revision: Union[str, None] = '0001_create_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'clients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'owner_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'client_type',
            sa.Enum('PRIVATE_PERSON', 'COMPANY', name='clienttype'),
            nullable=False,
        ),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('company_name', sa.String(length=512), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('nip', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.String(length=4096), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_clients_owner_user_id', 'clients', ['owner_user_id'])
    op.create_index('ix_clients_company_name', 'clients', ['company_name'])
    op.create_index('ix_clients_phone', 'clients', ['phone'])
    op.create_index('ix_clients_owner_first_name', 'clients', ['owner_user_id', 'first_name'])
    op.create_index('ix_clients_owner_last_name', 'clients', ['owner_user_id', 'last_name'])


def downgrade() -> None:
    op.drop_index('ix_clients_owner_last_name', table_name='clients')
    op.drop_index('ix_clients_owner_first_name', table_name='clients')
    op.drop_index('ix_clients_phone', table_name='clients')
    op.drop_index('ix_clients_company_name', table_name='clients')
    op.drop_index('ix_clients_owner_user_id', table_name='clients')
    op.drop_table('clients')
    op.execute("DROP TYPE IF EXISTS clienttype")
