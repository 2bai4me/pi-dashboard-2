"""introduce_rueckfrage_warten_status

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15 22:00:00.000000

Fuehrt zwei neue Status ein und migriert bestehende Tasks:

  Alte Semantik (eine Spalte 'block'):
    block = "wartet auf Input" (CIO-Frage an CEO) ODER
            "wartet auf anderes Task-Ergebnis"

  Neue Semantik (zwei Spalten):
    rueckfrage = "CIO-Frage an CEO, Input benötigt"
    warten     = "wartet auf anderes Task-Ergebnis"

  Da die ueberwiegende Verwendung von 'block' in workflow.py + scheduler.py
  die CIO-Frage-Antwort-Mechanik ist (siehe commit history), werden
  bestehende 'block'-Tasks als 'rueckfrage' migriert. Das neue 'warten'
  muss explizit von anderen Prozessen gesetzt werden (z.B. aggregate_subtasks).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'd6e90ff9bb52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migriere 'block' -> 'rueckfrage'.

    'warten' wird nicht migriert, da es in der DB noch nicht vorkommt.
    """
    op.execute("UPDATE tasks SET status = 'rueckfrage' WHERE status = 'block'")


def downgrade() -> None:
    """Reverse: 'rueckfrage' -> 'block'."""
    op.execute("UPDATE tasks SET status = 'block' WHERE status = 'rueckfrage'")
