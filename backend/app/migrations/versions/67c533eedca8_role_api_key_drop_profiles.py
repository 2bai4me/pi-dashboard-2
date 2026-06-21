"""role_api_key_drop_profiles

Revision ID: 67c533eedca8
Revises: eccaf7effa9e
Create Date: 2026-06-20 19:42:23.618524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67c533eedca8'
down_revision: Union[str, Sequence[str], None] = 'eccaf7effa9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Neue Architektur: Rolle referenziert Credential direkt; Provider-Profile entfallen."""
    # 1) Rolle bekommt direkten API-Key-Referenz
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('api_key_id', sa.String(length=32), nullable=True))
        batch_op.create_index('idx_roles_api_key_id', ['api_key_id'], unique=False)
        batch_op.create_foreign_key('fk_roles_api_key_id', 'provider_credentials', ['api_key_id'], ['id'], ondelete='SET NULL')

    # 2) Provider-Profile-Tabellen entfernen (Mappings zuerst wegen FK)
    with op.batch_alter_table('provider_profile_role_mappings', schema=None) as batch_op:
        batch_op.drop_index('idx_pprm_api_key_id')
        batch_op.drop_index('idx_pprm_role_name')
        batch_op.drop_index('idx_pprm_profile_id')

    op.drop_table('provider_profile_role_mappings')

    with op.batch_alter_table('provider_profiles', schema=None) as batch_op:
        batch_op.drop_index('idx_provider_profiles_is_active')
        batch_op.drop_index('idx_provider_profiles_created_at')

    op.drop_table('provider_profiles')


def downgrade() -> None:
    """Provider-Profile wiederherstellen und direkte Role-Credential-Referenz entfernen."""
    # 1) Direkte Referenz auf Credential aus Rolle entfernen
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.drop_constraint('fk_roles_api_key_id', type_='foreignkey')
        batch_op.drop_index('idx_roles_api_key_id')
        batch_op.drop_column('api_key_id')

    # 2) Provider-Profile-Tabelle wiederherstellen
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

    # 3) Mapping-Tabelle wiederherstellen (inkl. api_key_id aus eccaf7effa9e)
    op.create_table(
        'provider_profile_role_mappings',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('profile_id', sa.String(length=32), nullable=False),
        sa.Column('role_name', sa.String(length=64), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('api_key_id', sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(['profile_id'], ['provider_profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['api_key_id'], ['provider_credentials.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('provider_profile_role_mappings', schema=None) as batch_op:
        batch_op.create_index('idx_pprm_profile_id', ['profile_id'], unique=False)
        batch_op.create_index('idx_pprm_role_name', ['role_name'], unique=False)
        batch_op.create_index('idx_pprm_api_key_id', ['api_key_id'], unique=False)
