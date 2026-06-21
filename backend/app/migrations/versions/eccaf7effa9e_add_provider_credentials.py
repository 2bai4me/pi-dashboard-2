"""add_provider_credentials

Revision ID: eccaf7effa9e
Revises: c7c59ce08057
Create Date: 2026-06-20 18:55:20.659974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eccaf7effa9e'
down_revision: Union[str, Sequence[str], None] = 'c7c59ce08057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'provider_credentials',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('provider_credentials', schema=None) as batch_op:
        batch_op.create_index('idx_provider_credentials_active', ['is_active'], unique=False)
        batch_op.create_index('idx_provider_credentials_label', ['label'], unique=False)
        batch_op.create_index('idx_provider_credentials_provider', ['provider'], unique=False)

    with op.batch_alter_table('provider_profile_role_mappings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('api_key_id', sa.String(length=32), nullable=True))
        batch_op.create_index('idx_pprm_api_key_id', ['api_key_id'], unique=False)
        batch_op.create_foreign_key('fk_pprm_api_key_id', 'provider_credentials', ['api_key_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('provider_profile_role_mappings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pprm_api_key_id', type_='foreignkey')
        batch_op.drop_index('idx_pprm_api_key_id')
        batch_op.drop_column('api_key_id')

    with op.batch_alter_table('provider_credentials', schema=None) as batch_op:
        batch_op.drop_index('idx_provider_credentials_provider')
        batch_op.drop_index('idx_provider_credentials_label')
        batch_op.drop_index('idx_provider_credentials_active')

    op.drop_table('provider_credentials')
