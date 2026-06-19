"""add_default_sop_id_to_projects

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-16 08:00:00.000000

Fuegt das Feld default_sop_id zur projects-Tabelle hinzu.

Hintergrund (User-Direktive 15.06.2026):
  Im UI soll links neben dem Mode-Switcher (live/Warten/Abgeschlossen)
  ein Dropdown stehen, mit dem der User die Standard-SOP fuer das
  Projekt auswaehlen kann. Diese Auswahl wird hier persistiert.

  Die Rule-Engine (SOP-Funktion, kommt spaeter) liest dieses Feld
  und nutzt es, um den Prozessdurchlauf gemaess SOP-Vorgaben zu steuern.

  Bis dahin hat das Feld KEINE funktionale Wirkung — es ist reine
  Konfiguration (SOP-Aufbau-Phase).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt default_sop_id Spalte + Index zur projects-Tabelle hinzu."""
    op.add_column(
        "projects",
        sa.Column("default_sop_id", sa.String(32), nullable=True)
    )
    op.create_index(
        "idx_projects_default_sop",
        "projects",
        ["default_sop_id"],
        unique=False,
    )


def downgrade() -> None:
    """Entfernt default_sop_id Spalte + Index wieder."""
    op.drop_index("idx_projects_default_sop", table_name="projects")
    op.drop_column("projects", "default_sop_id")
