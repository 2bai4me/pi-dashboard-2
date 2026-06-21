"""add_credential_pricing

Revision ID: 390953cf5104
Revises: 67c533eedca8
Create Date: 2026-06-20 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '390953cf5104'
down_revision: Union[str, Sequence[str], None] = '67c533eedca8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fügt Kostenfelder (USD pro 1M Token) zu provider_credentials hinzu."""
    with op.batch_alter_table('provider_credentials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('input_cost_per_1m', sa.Numeric(precision=10, scale=4), nullable=True))
        batch_op.add_column(sa.Column('output_cost_per_1m', sa.Numeric(precision=10, scale=4), nullable=True))


def downgrade() -> None:
    """Entfernt Kostenfelder wieder."""
    with op.batch_alter_table('provider_credentials', schema=None) as batch_op:
        batch_op.drop_column('output_cost_per_1m')
        batch_op.drop_column('input_cost_per_1m')
