"""add provider profiles

Revision ID: c7c59ce08057
Revises: m4n5o6p7q8r9
Create Date: 2026-06-20 13:59:15.617835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7c59ce08057'
down_revision: Union[str, Sequence[str], None] = 'm4n5o6p7q8r9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Erstellt Tabellen für Provider-Profile und Rollen-Mappings."""
    op.create_table(
        'provider_profiles',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('provider_profiles', schema=None) as batch_op:
        batch_op.create_index('idx_provider_profiles_created_at', ['created_at'], unique=False)
        batch_op.create_index('idx_provider_profiles_is_active', ['is_active'], unique=False)

    op.create_table(
        'provider_profile_role_mappings',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('profile_id', sa.String(length=32), nullable=False),
        sa.Column('role_name', sa.String(length=64), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['profile_id'], ['provider_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('provider_profile_role_mappings', schema=None) as batch_op:
        batch_op.create_index('idx_pprm_profile_id', ['profile_id'], unique=False)
        batch_op.create_index('idx_pprm_role_name', ['role_name'], unique=False)


def downgrade() -> None:
    """Entfernt Tabellen für Provider-Profile und Rollen-Mappings."""
    with op.batch_alter_table('provider_profile_role_mappings', schema=None) as batch_op:
        batch_op.drop_index('idx_pprm_role_name')
        batch_op.drop_index('idx_pprm_profile_id')

    op.drop_table('provider_profile_role_mappings')

    with op.batch_alter_table('provider_profiles', schema=None) as batch_op:
        batch_op.drop_index('idx_provider_profiles_is_active')
        batch_op.drop_index('idx_provider_profiles_created_at')

    op.drop_table('provider_profiles')
