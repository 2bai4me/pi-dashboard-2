"""Migration: Ideen-Tabelle fuer neue Idee-Page

User-Direktive 23.06.2026: Idee-Page braucht CRUD fuer Ideen.
Brainstorm-Eintraege (einzelne Saetze) sind nicht ausreichend.
"""
from alembic import op
import sqlalchemy as sa


revision = "p7q8r9s0t1u2"
down_revision = "o6p7q8r9s0t1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ideas",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("brainstorm", sa.Text()),
        sa.Column("requirements", sa.Text()),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("tags", sa.Text()),  # JSON-Array
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
    )
    op.create_index("idx_ideas_status", "ideas", ["status"])
    op.create_index("idx_ideas_created", "ideas", ["created_at"])


def downgrade():
    op.drop_index("idx_ideas_created", table_name="ideas")
    op.drop_index("idx_ideas_status", table_name="ideas")
    op.drop_table("ideas")