"""add_raci_and_position_to_sop_steps

Revision ID: g1h2i3j4k5l6
Revises: b2c3d4e5f6a7
Create Date: 2026-06-15 23:00:00.000000

User-Direktive 15.06.2026: BPMN-Designer soll interaktiv sein
(Drag & Drop von Nodes + RACI pro Step).

  - raci_r: Wer ist verantwortlich (Responsible) — 1 Agent
  - raci_a: Wer ist genehmigend (Accountable)  — 1 Agent (meist CIO/CEO)
  - raci_c: Wer wird konsultiert (Consulted)   — kommagetrennte Liste
  - raci_i: Wer wird informiert (Informed)     — kommagetrennte Liste
  - x, y:   Visuelle Position des Steps im BPMN-Designer (optional)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt RACI-Felder + x/y-Position zu sop_steps hinzu."""
    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('raci_r', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('raci_a', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('raci_c', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('raci_i', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('x', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('y', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Entfernt RACI-Felder + x/y-Position."""
    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.drop_column('x')
        batch_op.drop_column('y')
        batch_op.drop_column('raci_i')
        batch_op.drop_column('raci_c')
        batch_op.drop_column('raci_a')
        batch_op.drop_column('raci_r')
