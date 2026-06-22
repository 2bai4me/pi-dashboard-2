"""Migration: SOP-Step-Phasen auf Kanban-Phasen umstellen

User-Direktive 22.06.2026: 'Die Phasen sollen die Phasen aus dem KANBAN sein.
Projekt/Board'. Bisher hartcodierte Phases werden auf die Kanban-Spalten
gemappt, die in frontend/src/constants/kanban.ts definiert sind.

Mapping (alt -> neu):
  Task         -> triage       (Standard-Schritt, neue Tasks starten hier)
  Decision     -> go           (Task ist freigegeben)
  Sub-SOP      -> in_progress  (Task wird aktuell bearbeitet)
  Wait         -> warten       (Task wartet auf externe Bedingung)
  Notification -> rueckfrage   (Rueckfrage blockiert den Workflow)
  End          -> done         (Task ist abgeschlossen)

Downgrade: rueckfaertig (neu -> alt).

Diese Migration ist idempotent: Falls ein Wert bereits im neuen Format
vorliegt, wird er nicht nochmal gemappt (WHERE-Bedingung).
"""
from alembic import op


revision = "n5o6p7q8r9s0"
# Merge-Migration: fuehrt die beiden Branches e5f6a7b8c9d0 (role_display_name)
# und m4n5o6p7q8r9 (session_id) zusammen. Beide waren parallel im Repo.
down_revision = ("e5f6a7b8c9d0", "m4n5o6p7q8r9")
branch_labels = None
depends_on = None


# Mapping alt -> neu
PHASE_MIGRATION_MAP = {
    "Task": "triage",
    "Decision": "go",
    "Sub-SOP": "in_progress",
    "Wait": "warten",
    "Notification": "rueckfrage",
    "End": "done",
}

# Reverse-Mapping fuer Downgrade (neu -> alt)
PHASE_REVERSE_MAP = {v: k for k, v in PHASE_MIGRATION_MAP.items()}


def upgrade():
    # Idempotente Updates mit WHERE-Bedingung
    for old_value, new_value in PHASE_MIGRATION_MAP.items():
        op.execute(
            f"UPDATE sop_steps SET phase = '{new_value}' WHERE phase = '{old_value}'"
        )


def downgrade():
    # Rueckgaengig (Downgrade)
    for new_value, old_value in PHASE_REVERSE_MAP.items():
        op.execute(
            f"UPDATE sop_steps SET phase = '{old_value}' WHERE phase = '{new_value}'"
        )