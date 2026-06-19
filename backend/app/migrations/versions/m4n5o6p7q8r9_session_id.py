"""Migration: Session-ID in TaskTransition + TaskHistory

Felder:
- task_transitions.session_id: VARCHAR(64)
- task_history.session_id: VARCHAR(64)

Die Session-ID identifiziert, welche Konversation/Session eine Aenderung
ausgeloest hat. Wird vom Worker-Loop und Frontend automatisch gesetzt.

Format: "session-{uuid12}" oder "worker-{uuid8}" oder "user-{uuid8}"
"""
from alembic import op
import sqlalchemy as sa


revision = "m4n5o6p7q8r9"
down_revision = "l3m4n5o6p7q8"
branch_labels = None
depends_on = None


def upgrade():
    # task_transitions
    op.add_column("task_transitions", sa.Column("session_id", sa.String(length=64), nullable=True))
    op.create_index("idx_transition_session", "task_transitions", ["session_id"])

    # task_history
    op.add_column("task_history", sa.Column("session_id", sa.String(length=64), nullable=True))
    op.create_index("idx_history_session", "task_history", ["session_id"])


def downgrade():
    op.drop_index("idx_history_session", table_name="task_history")
    op.drop_column("task_history", "session_id")
    op.drop_index("idx_transition_session", table_name="task_transitions")
    op.drop_column("task_transitions", "session_id")
