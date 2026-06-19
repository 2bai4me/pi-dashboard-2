"""add_input_tool_to_sop_steps

Revision ID: j1k2l3m4n5o9
Revises: i1j2k3l4m5n8
Create Date: 2026-06-17 11:00:00.000000

User-Direktive 17.06.2026: SOP-Steps koennen ein User-Input-Tool
definieren. Wenn der Step ausgefuehrt wird:
  - Wenn input_tool_required=True UND context[input_tool_context_key] leer:
    -> AgentQuestion wird erstellt
    -> Engine wartet blockierend auf User-Antwort
    -> Antwort wird in instance.context[context_key] gespeichert
    -> Step wird als completed markiert, Engine geht zum naechsten Step

Use-Case: ISCP-SOP Step 0 "Beschreibung des Projektziels"
  -> CEO-digital fragt User nach dem Projektziel
  -> User antwortet im Tools-Tab
  -> Step complete, Worker-Assignment kann starten

Neue Felder:
  - input_tool_required: bool (default false)
  - input_tool_type: text|confirmation|choice|image|attachment
  - input_tool_prompt: TEXT (Frage an den User)
  - input_tool_options: TEXT (JSON-Liste, nur bei choice)
  - input_tool_context_key: VARCHAR(64) (Key in instance.context)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j1k2l3m4n5o9'
down_revision: Union[str, Sequence[str], None] = 'i1j2k3l4m5n8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt Input-Tool-Felder zu sop_steps hinzu."""
    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('input_tool_required', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('input_tool_type', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('input_tool_prompt', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('input_tool_options', sa.Text(), nullable=True))  # JSON
        batch_op.add_column(sa.Column('input_tool_context_key', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Entfernt Input-Tool-Felder."""
    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.drop_column('input_tool_context_key')
        batch_op.drop_column('input_tool_options')
        batch_op.drop_column('input_tool_prompt')
        batch_op.drop_column('input_tool_type')
        batch_op.drop_column('input_tool_required')
