"""Migration: app_port_allocations Tabelle

User-Direktive 23.06.2026 (Task 4bf7146b0780):
Port-Management-System fuer alle Apps. Jede App bekommt 10 Ports
reserviert (kann auch 2+ Bloecke haben).

Schema:
- id: PK
- app_name: z.B. 'pi-dashboard-2', 'smproducer', 'youtube-analyzer'
- port_start, port_end: Range (z.B. 9220-9229)
- task_id: Welcher Task hat die Ports reserviert
- allocated_at: Zeit der Reservierung
- released_at: NULL = noch belegt, sonst Zeit der Freigabe
- status: active / released
"""
from alembic import op
import sqlalchemy as sa


revision = "r9s0t1u2v3w4"
down_revision = "q8r9s0t1u2v3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_port_allocations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("app_name", sa.String(length=64), nullable=False),
        sa.Column("port_start", sa.Integer(), nullable=False),
        sa.Column("port_end", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=32)),
        sa.Column("allocated_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
        sa.Column("released_at", sa.DateTime()),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("notes", sa.Text()),
    )
    op.create_index("idx_port_allocations_app", "app_port_allocations", ["app_name"])
    op.create_index("idx_port_allocations_status", "app_port_allocations", ["status"])
    # Default-Allocations fuer bekannte Apps anlegen
    op.execute("""
        INSERT INTO app_port_allocations (id, app_name, port_start, port_end, status, notes)
        VALUES
            ('alloc-pi-dashboard-9220', 'pi-dashboard-2', 9220, 9229, 'active', 'Hauptentwicklungs-App'),
            ('alloc-pi-dashboard-9230', 'pi-dashboard-2', 9230, 9239, 'active', 'Erweiterungs-Bereich'),
            ('alloc-openbrain-9300',    'openbrain',     9300, 9309, 'active', 'OpenBrain-Container'),
            ('alloc-smproducer-9400',   'smproducer',    9400, 9409, 'active', 'SMproducer-3.0'),
            ('alloc-youtube-9500',      'youtube-analyzer', 9500, 9509, 'active', 'YouTube-Service'),
            ('alloc-generic-10000',     'generic',       10000, 10009, 'active', 'Reserve fuer neue Apps')
    """)


def downgrade():
    op.drop_index("idx_port_allocations_status", table_name="app_port_allocations")
    op.drop_index("idx_port_allocations_app", table_name="app_port_allocations")
    op.drop_table("app_port_allocations")