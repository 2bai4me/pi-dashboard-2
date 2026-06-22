"""Migration: Swarm-Spawner-Tabellen hinzufuegen

User-Direktive 22.06.2026: Multi-Agent-Swarm fuer SOP 7c86692be939.
Erstellt zwei Tabellen:
  - swarm_runs: ein Swarm-Lauf pro Task/Step
  - swarm_workers: einzelne Worker innerhalb eines Swarms

Beide werden vom swarm_spawner.Service verwaltet.
"""
from alembic import op
import sqlalchemy as sa


revision = "o6p7q8r9s0t1"
# Merge-Head: baut auf n5o6p7q8r9s0 (Phase-Migration) auf
down_revision = "n5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "swarm_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("task_id", sa.String(length=32)),
        sa.Column("sop_instance_id", sa.String(length=32)),
        sa.Column("step_id", sa.String(length=32)),
        sa.Column("swarm_type", sa.String(length=32), nullable=False),
        sa.Column("workers_config", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("merge_strategy", sa.String(length=32)),
        sa.Column("consensus_threshold", sa.Float(), server_default="75.0"),
        sa.Column("auto_approve_threshold", sa.Float(), server_default="90.0"),
        sa.Column("result", sa.Text()),
        sa.Column("total_cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
    )
    op.create_index("idx_swarm_runs_task", "swarm_runs", ["task_id"])

    op.create_table(
        "swarm_workers",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("swarm_run_id", sa.String(length=32), nullable=False),
        sa.Column("subagent_role", sa.String(length=64), nullable=False),
        sa.Column("variant", sa.String(length=64)),
        sa.Column("weight", sa.Float(), server_default="1.0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("output", sa.Text()),
        sa.Column("cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("score", sa.Float()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["swarm_run_id"], ["swarm_runs.id"]),
    )
    op.create_index("idx_swarm_workers_run", "swarm_workers", ["swarm_run_id"])


def downgrade():
    op.drop_index("idx_swarm_workers_run", table_name="swarm_workers")
    op.drop_table("swarm_workers")
    op.drop_index("idx_swarm_runs_task", table_name="swarm_runs")
    op.drop_table("swarm_runs")