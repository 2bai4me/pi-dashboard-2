"""Migration: token_usage.parent_task_id hinzufuegen

User-Direktive 23.06.2026 (Task 61ab3dfe26d3): Performance-Tabelle-Eintrag
welcher Subtask von welchem Haupttask eingestellt und bearbeitet wurde.

token_usage hat bereits task_id (FK auf tasks.id). Fuer Sub-Tasks ist
parent_task_id der Verweis auf den Hauptauftrag.
"""
from alembic import op
import sqlalchemy as sa


revision = "q8r9s0t1u2v3"
down_revision = "p7q8r9s0t1u2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("token_usage") as batch_op:
        batch_op.add_column(sa.Column("parent_task_id", sa.String(length=32), nullable=True))
    op.create_index("idx_token_usage_parent_task", "token_usage", ["parent_task_id"])


def downgrade():
    op.drop_index("idx_token_usage_parent_task", table_name="token_usage")
    with op.batch_alter_table("token_usage") as batch_op:
        batch_op.drop_column("parent_task_id")