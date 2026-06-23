"""Migration: Eindeutige Projektnummer fuer jedes Projekt.

User-Direktive 23.06.2026 (Task 260326669e82):
- Neues Feld project_number in projects-Tabelle
- Format: PROJ-YYYY-NNN (z.B. PROJ-2026-001)
- Eindeutig pro Projekt
- Backfill fuer bestehende Projekte
- API liefert project_number mit
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "s0t1u2v3w4x5"
down_revision = "r9s0t1u2v3w4"
branch_labels = None
depends_on = None


def upgrade():
    # Spalte hinzufuegen (zunaechst nullable fuer Backfill)
    op.add_column("projects", sa.Column("project_number", sa.String(length=32), nullable=True))
    op.create_index("idx_projects_project_number", "projects", ["project_number"], unique=True)

    # Backfill: generiere Nummern fuer bestehende Projekte nach created_at
    # Format: PROJ-YYYY-NNN (NNN = 3-stellige laufende Nummer)
    current_year = datetime.now().year
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, created_at FROM projects WHERE project_number IS NULL ORDER BY created_at"
    )).fetchall()
    counter = 1
    for row in rows:
        # Jahr aus created_at extrahieren
        year = current_year
        if row.created_at:
            try:
                year = row.created_at.year
            except (AttributeError, TypeError):
                pass
        project_number = f"PROJ-{year}-{counter:03d}"
        conn.execute(sa.text(
            "UPDATE projects SET project_number = :pn WHERE id = :id"
        ), {"pn": project_number, "id": row.id})
        counter += 1

    # Sequence-Table fuer fortlaufende Nummer
    op.create_table(
        "project_number_sequences",
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("last_number", sa.Integer(), server_default="0", nullable=False),
    )
    # Initialisiere mit aktuellem Counter
    op.execute(
        f"INSERT INTO project_number_sequences (year, last_number) VALUES ({current_year}, {counter - 1})"
    )


def downgrade():
    op.drop_table("project_number_sequences")
    op.drop_index("idx_projects_project_number", table_name="projects")
    op.drop_column("projects", "project_number")