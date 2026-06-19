"""add_emoji_to_roles

Revision ID: a1b2c3d4e5f6
Revises: f05c21f4e9e7
Create Date: 2026-06-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f05c21f4e9e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add emoji column to roles table (nullable, max 8 chars)."""
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('emoji', sa.String(length=8), nullable=True))


def downgrade() -> None:
    """Remove emoji column from roles table."""
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.drop_column('emoji')
