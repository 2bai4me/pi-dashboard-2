"""Migration: Development SOP - neue Task-Felder

Aenderungen an der Task-Tabelle:
- worker_understanding: TEXT - Auftragsbestaetigung des Bearbeiters in seinen Worten
- worker_understanding_at: DATETIME - Wann der Bearbeiter sein Understanding abgegeben hat
- worker_understanding_confirmed: BOOLEAN - CIO hat das Understanding bestaetigt
- review_findings: TEXT (JSON) - Liste der Findings vom Code-Review
- review_iteration_count: INTEGER - Anzahl Review-Iterationen
- bza_findings: TEXT (JSON) - Maengelliste des CIO bei BZA
- bza_iteration_count: INTEGER - Anzahl BZA-Iterationen
- last_rejection_reason: TEXT - Begruendung der letzten Ablehnung (durch CIO)
- dev_sop_phase: VARCHAR(32) - Aktuelle Phase im Dev-Workflow
  (triage | worker_understanding | implementing | review | bza | done | rejected)
- dev_sop_current_step: VARCHAR(32) - ID des aktuellen SOP-Steps

Performance-Tracking:
- Bestehende TaskTransition-Tabelle wird weiter genutzt
- Jeder Phase-Change wird automatisch dokumentiert mit agent, reason, details
"""
from alembic import op
import sqlalchemy as sa


revision = "l3m4n5o6p7q8"
down_revision = "k2l3m4n5o6p0"
branch_labels = None
depends_on = None


def upgrade():
    # === Task-Felder fuer Development-SOP-Workflow ===
    op.add_column("tasks", sa.Column("worker_understanding", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("worker_understanding_at", sa.DateTime(), nullable=True))
    op.add_column("tasks", sa.Column("worker_understanding_confirmed", sa.Boolean(), default=False, nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("review_findings", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("review_iteration_count", sa.Integer(), default=0, nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("bza_findings", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("bza_iteration_count", sa.Integer(), default=0, nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("last_rejection_reason", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("dev_sop_phase", sa.String(length=32), nullable=True))
    op.add_column("tasks", sa.Column("dev_sop_current_step", sa.String(length=32), nullable=True))

    # === Index fuer schnelle Filterung nach Phase ===
    op.create_index("idx_tasks_dev_sop_phase", "tasks", ["dev_sop_phase"])


def downgrade():
    op.drop_index("idx_tasks_dev_sop_phase", table_name="tasks")
    op.drop_column("tasks", "dev_sop_current_step")
    op.drop_column("tasks", "dev_sop_phase")
    op.drop_column("tasks", "last_rejection_reason")
    op.drop_column("tasks", "bza_iteration_count")
    op.drop_column("tasks", "bza_findings")
    op.drop_column("tasks", "review_iteration_count")
    op.drop_column("tasks", "review_findings")
    op.drop_column("tasks", "worker_understanding_confirmed")
    op.drop_column("tasks", "worker_understanding_at")
    op.drop_column("tasks", "worker_understanding")
