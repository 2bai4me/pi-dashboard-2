"""add_board_operators

Revision ID: i1j2k3l4m5n8
Revises: h1i2j3k4l5m7
Create Date: 2026-06-17 10:00:00.000000

User-Direktive 17.06.2026: Eigenstaendiger Watchdog-Operator pro Live-Board.

Tabelle board_operators: 1:1 zu projects
  - agent_status: not_started | starting | active | stale | stopped | error
  - last_heartbeat: vom Operator alle 5s aktualisiert
  - stats: checks_total, stale_tasks_found, alerts_sent, questions_asked
  - config_json: optional per-Board-Konfig (Schwellwerte, Intervalle)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i1j2k3l4m5n8'
down_revision: Union[str, Sequence[str], None] = 'h1i2j3k4l5m7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Erstellt die Tabelle board_operators."""
    op.create_table(
        'board_operators',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column(
            'board_id', sa.String(length=32),
            sa.ForeignKey('projects.id', ondelete='CASCADE'),
            nullable=False, unique=True,
        ),
        sa.Column('agent_status', sa.String(length=16), nullable=False, server_default='not_started'),
        sa.Column('error_message', sa.Text(), nullable=True),

        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),

        sa.Column('checks_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stale_tasks_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('alerts_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('questions_asked', sa.Integer(), nullable=False, server_default='0'),

        sa.Column('config_json', sa.Text(), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_bo_board_id', 'board_operators', ['board_id'], unique=True)
    op.create_index('idx_bo_status', 'board_operators', ['agent_status'])
    op.create_index('idx_bo_heartbeat', 'board_operators', ['last_heartbeat'])


def downgrade() -> None:
    """Entfernt die Tabelle board_operators."""
    op.drop_index('idx_bo_heartbeat', table_name='board_operators')
    op.drop_index('idx_bo_status', table_name='board_operators')
    op.drop_index('idx_bo_board_id', table_name='board_operators')
    op.drop_table('board_operators')
