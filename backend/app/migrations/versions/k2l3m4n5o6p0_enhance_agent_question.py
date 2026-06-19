"""enhance_agent_question

Revision ID: k2l3m4n5o6p0
Revises: j1k2l3m4n5o9
Create Date: 2026-06-17 12:00:00.000000

User-Direktive 17.06.2026: User-Input-Tool erweitert.

Neue Felder in agent_questions:
  - description: TEXT — zusaetzlicher Kontext zur Frage
  - recommendation: TEXT — vom Agent vorgeschlagene Antwort
  - options_config: TEXT (JSON) — welche Optionen sichtbar sind
    {
      "show_description": true,
      "show_recommendation": true,
      "show_tts": true,
      "allow_edit_recommendation": true,
      "answer_required": true,
      "recommendation_as_default": true
    }
  - answer_attachments: TEXT (JSON-Liste) — vom User zur Antwort hinzugefuegte Attachments

Neue Felder in sop_steps:
  - input_tool_description: TEXT — Default-Beschreibung
  - input_tool_recommendation: TEXT — Default-Empfehlung
  - input_tool_options_config: TEXT (JSON) — welche Optionen angezeigt werden
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k2l3m4n5o6p0'
down_revision: Union[str, Sequence[str], None] = 'j1k2l3m4n5o9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === agent_questions erweitern ===
    with op.batch_alter_table('agent_questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('recommendation', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('options_config', sa.Text(), nullable=True))  # JSON
        batch_op.add_column(sa.Column('answer_attachments', sa.Text(), nullable=True))  # JSON-Liste

    # === sop_steps erweitern ===
    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('input_tool_description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('input_tool_recommendation', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('input_tool_options_config', sa.Text(), nullable=True))  # JSON


def downgrade() -> None:
    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.drop_column('input_tool_options_config')
        batch_op.drop_column('input_tool_recommendation')
        batch_op.drop_column('input_tool_description')
    with op.batch_alter_table('agent_questions', schema=None) as batch_op:
        batch_op.drop_column('answer_attachments')
        batch_op.drop_column('options_config')
        batch_op.drop_column('recommendation')
        batch_op.drop_column('description')
