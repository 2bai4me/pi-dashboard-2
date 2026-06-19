"""add_task_transitions_performance_table

Revision ID: ef4378441a72
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15 22:02:49.346500

User-Direktive 15.06.2026: Zentrale Performance-Tabelle fuer Status-Wechsel
+ 5-Sekunden-Verzoegerung zwischen Wechsel und Weiterverarbeitung.

Tabelle `task_transitions` dokumentiert JEDEN Status-Wechsel eines JEDEN
Tasks mit Projekt-ID, Timestamps (transition/processing/completed),
from/to-Status, Delay, Agent, Reason.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = 'ef4378441a72'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: zentrale Performance-Tabelle fuer Status-Wechsel."""
    op.create_table(
        'task_transitions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.String(length=32), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=True),
        sa.Column('from_status', sa.String(length=32), nullable=False),
        sa.Column('to_status', sa.String(length=32), nullable=False),
        sa.Column('transition_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processing_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delay_s', sa.Float(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('agent', sa.String(length=64), nullable=True),
        sa.Column('reason', sa.String(length=128), nullable=True),
        sa.Column('details', sa.JSON().with_variant(sa.Text(), 'sqlite'), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('task_transitions', schema=None) as batch_op:
        batch_op.create_index('idx_transition_task', ['task_id'], unique=False)
        batch_op.create_index('idx_transition_project', ['project_id'], unique=False)
        batch_op.create_index('idx_transition_project_at', ['project_id', 'transition_at'], unique=False)
        batch_op.create_index('idx_transition_task_at', ['task_id', 'transition_at'], unique=False)
        batch_op.create_index('idx_transition_to_status', ['to_status'], unique=False)
        batch_op.create_index('idx_transition_from_status', ['from_status'], unique=False)
        batch_op.create_index('idx_transition_at', ['transition_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema: entfernt task_transitions Tabelle + Indizes."""
    with op.batch_alter_table('task_transitions', schema=None) as batch_op:
        batch_op.drop_index('idx_transition_at')
        batch_op.drop_index('idx_transition_from_status')
        batch_op.drop_index('idx_transition_to_status')
        batch_op.drop_index('idx_transition_task_at')
        batch_op.drop_index('idx_transition_project_at')
        batch_op.drop_index('idx_transition_project')
        batch_op.drop_index('idx_transition_task')
    op.drop_table('task_transitions')
