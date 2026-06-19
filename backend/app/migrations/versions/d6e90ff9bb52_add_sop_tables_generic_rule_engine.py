"""add_sop_tables_generic_rule_engine

Revision ID: d6e90ff9bb52
Revises: ef4378441a72
Create Date: 2026-06-16 06:29:46.188657

User-Direktive 15.06.2026: Generisches SOP-System fuer wiederverwendbare
Regelprozesse. Ersetzt den hartcodierten Workflow durch eine
konfigurierbare Engine.

Tabellen:
  - sops: SOP-Definitionen (Vorlagen)
  - sop_steps: Geordnete Schritte (Phase, Trigger, Action, Agent, Expected, Rules)
  - sop_step_rules: Wenn-Dann-Regeln pro Step
  - sop_instances: Laufende SOP-Instanzen (an Projekt/Task gebunden)
  - sop_executions: Audit-Log der Ausfuehrungen
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision: str = 'd6e90ff9bb52'
down_revision: Union[str, Sequence[str], None] = 'ef4378441a72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: SOP-Tabellen anlegen."""
    # === sops ===
    op.create_table(
        'sops',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('parent_sop_id', sa.String(length=32), nullable=True),
        sa.Column('is_template', sa.Boolean(), nullable=False),
        sa.Column('bpmn_xml', sa.Text(), nullable=True),
        sa.Column('uml_sequence_diagram', sa.Text(), nullable=True),
        sa.Column('default_delay_s', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['parent_sop_id'], ['sops.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sops', schema=None) as batch_op:
        batch_op.create_index('idx_sops_category', ['category'], unique=False)
        batch_op.create_index('idx_sops_parent', ['parent_sop_id'], unique=False)
        batch_op.create_index('idx_sops_name_version', ['name', 'version'], unique=False)
        batch_op.create_index('ix_sops_name', ['name'], unique=False)

    # === sop_steps ===
    op.create_table(
        'sop_steps',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('sop_id', sa.String(length=32), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('phase', sa.String(length=64), nullable=False),
        sa.Column('trigger', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('action_params', sa.JSON().with_variant(sa.Text(), 'sqlite'), nullable=True),
        sa.Column('agent', sa.String(length=64), nullable=False),
        sa.Column('expected_result', sa.Text(), nullable=True),
        sa.Column('success_criteria', sa.JSON().with_variant(sa.Text(), 'sqlite'), nullable=True),
        sa.Column('next_step_id', sa.String(length=32), nullable=True),
        sa.Column('fail_step_id', sa.String(length=32), nullable=True),
        sa.Column('on_sub_sop_step_id', sa.String(length=32), nullable=True),
        sa.Column('delay_s', sa.Float(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['sop_id'], ['sops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['next_step_id'], ['sop_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['fail_step_id'], ['sop_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['on_sub_sop_step_id'], ['sop_steps.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.create_index('idx_sop_steps_sop_order', ['sop_id', 'step_order'], unique=False)
        batch_op.create_index('ix_sop_steps_sop_id', ['sop_id'], unique=False)

    # === sop_step_rules ===
    op.create_table(
        'sop_step_rules',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('step_id', sa.String(length=32), nullable=False),
        sa.Column('rule_order', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('condition_field', sa.String(length=128), nullable=False),
        sa.Column('condition_operator', sa.String(length=16), nullable=False),
        sa.Column('condition_value', sa.JSON().with_variant(sa.Text(), 'sqlite'), nullable=True),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('action_target', sa.String(length=255), nullable=True),
        sa.Column('action_params', sa.JSON().with_variant(sa.Text(), 'sqlite'), nullable=True),
        sa.ForeignKeyConstraint(['step_id'], ['sop_steps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sop_step_rules', schema=None) as batch_op:
        batch_op.create_index('ix_sop_step_rules_step_id', ['step_id'], unique=False)

    # === sop_instances ===
    op.create_table(
        'sop_instances',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('sop_id', sa.String(length=32), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=True),
        sa.Column('task_id', sa.String(length=32), nullable=True),
        sa.Column('current_step_id', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('parent_instance_id', sa.String(length=32), nullable=True),
        sa.Column('context', sa.JSON().with_variant(sa.Text(), 'sqlite'), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sop_id'], ['sops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_step_id'], ['sop_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_instance_id'], ['sop_instances.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sop_instances', schema=None) as batch_op:
        batch_op.create_index('idx_sop_inst_project', ['project_id'], unique=False)
        batch_op.create_index('idx_sop_inst_task', ['task_id'], unique=False)
        batch_op.create_index('idx_sop_inst_status', ['status'], unique=False)
        batch_op.create_index('idx_sop_inst_parent', ['parent_instance_id'], unique=False)
        batch_op.create_index('ix_sop_instances_sop_id', ['sop_id'], unique=False)

    # === sop_executions ===
    op.create_table(
        'sop_executions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('instance_id', sa.String(length=32), nullable=False),
        sa.Column('step_id', sa.String(length=32), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('agent', sa.String(length=64), nullable=True),
        sa.Column('details', sa.JSON().with_variant(sa.Text(), 'sqlite'), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['instance_id'], ['sop_instances.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['step_id'], ['sop_steps.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sop_executions', schema=None) as batch_op:
        batch_op.create_index('idx_sop_exec_instance_ts', ['instance_id', 'ts'], unique=False)
        batch_op.create_index('idx_sop_exec_event', ['event'], unique=False)
        batch_op.create_index('idx_sop_exec_step', ['step_id'], unique=False)
        batch_op.create_index('ix_sop_executions_instance_id', ['instance_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema: SOP-Tabellen entfernen (in umgekehrter Reihenfolge)."""
    with op.batch_alter_table('sop_executions', schema=None) as batch_op:
        batch_op.drop_index('ix_sop_executions_instance_id')
        batch_op.drop_index('idx_sop_exec_step')
        batch_op.drop_index('idx_sop_exec_event')
        batch_op.drop_index('idx_sop_exec_instance_ts')
    op.drop_table('sop_executions')

    with op.batch_alter_table('sop_instances', schema=None) as batch_op:
        batch_op.drop_index('ix_sop_instances_sop_id')
        batch_op.drop_index('idx_sop_inst_parent')
        batch_op.drop_index('idx_sop_inst_status')
        batch_op.drop_index('idx_sop_inst_task')
        batch_op.drop_index('idx_sop_inst_project')
    op.drop_table('sop_instances')

    with op.batch_alter_table('sop_step_rules', schema=None) as batch_op:
        batch_op.drop_index('ix_sop_step_rules_step_id')
    op.drop_table('sop_step_rules')

    with op.batch_alter_table('sop_steps', schema=None) as batch_op:
        batch_op.drop_index('ix_sop_steps_sop_id')
        batch_op.drop_index('idx_sop_steps_sop_order')
    op.drop_table('sop_steps')

    with op.batch_alter_table('sops', schema=None) as batch_op:
        batch_op.drop_index('ix_sops_name')
        batch_op.drop_index('idx_sops_name_version')
        batch_op.drop_index('idx_sops_parent')
        batch_op.drop_index('idx_sops_category')
    op.drop_table('sops')
