"""add_agent_questions

Revision ID: h1i2j3k4l5m7
Revises: g1h2i3j4k5l6
Create Date: 2026-06-17 09:00:00.000000

User-Direktive 17.06.2026: AgentQuestion-Tool fuer User<->Agent Interaktion
auf allen Ebenen (C-Level, Worker, Subagent).

Tabellen:
  - agent_questions: Eine offene/beantwortete Frage
  - agent_question_attachments: Anhaenge (Dateien/Bilder) zu Fragen

Use-Cases:
  - Agent braucht Input vom User (z.B. "Welche Datenbank-URL?")
  - Agent moechte Bild/Screenshot vom User
  - Agent moechte Bestaetigung (ja/nein)
  - User haengt Datei/Bild als Antwort an
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h1i2j3k4l5m7'
down_revision: Union[str, Sequence[str], None] = 'g1h2i3j4k5l6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Erstellt die Tabellen agent_questions und agent_question_attachments."""
    op.create_table(
        'agent_questions',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column('agent_id', sa.String(length=64), nullable=False),
        sa.Column('agent_level', sa.String(length=16), nullable=False, server_default='Worker'),
        sa.Column('agent_label', sa.String(length=128), nullable=True),

        sa.Column('question_type', sa.String(length=32), nullable=False, server_default='text'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('options', sa.Text(), nullable=True),  # JSON in SQLite

        sa.Column('context', sa.Text(), nullable=True),  # JSON
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('priority', sa.String(length=16), nullable=False, server_default='medium'),

        sa.Column('answer_text', sa.Text(), nullable=True),
        sa.Column('answer_choice', sa.String(length=500), nullable=True),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('answered_by', sa.String(length=64), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_aq_agent_id', 'agent_questions', ['agent_id'])
    op.create_index('idx_aq_status', 'agent_questions', ['status'])
    op.create_index('idx_aq_priority', 'agent_questions', ['priority'])
    op.create_index('idx_aq_created_at', 'agent_questions', ['created_at'])
    op.create_index('idx_aq_agent_status', 'agent_questions', ['agent_id', 'status'])

    op.create_table(
        'agent_question_attachments',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column(
            'question_id', sa.String(length=32),
            sa.ForeignKey('agent_questions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('kind', sa.String(length=16), nullable=False, server_default='file'),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('mime_type', sa.String(length=128), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='agent'),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_aqa_question_id', 'agent_question_attachments', ['question_id'])


def downgrade() -> None:
    """Entfernt die Tabellen (in umgekehrter Reihenfolge wegen FK)."""
    op.drop_index('idx_aqa_question_id', table_name='agent_question_attachments')
    op.drop_table('agent_question_attachments')

    op.drop_index('idx_aq_agent_status', table_name='agent_questions')
    op.drop_index('idx_aq_created_at', table_name='agent_questions')
    op.drop_index('idx_aq_priority', table_name='agent_questions')
    op.drop_index('idx_aq_status', table_name='agent_questions')
    op.drop_index('idx_aq_agent_id', table_name='agent_questions')
    op.drop_table('agent_questions')
