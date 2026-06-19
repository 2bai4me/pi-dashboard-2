"""add_cio_triage_fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-16 08:30:00.000000

User-Direktive 16.06.2026: "Schritt 0 CIO Triage Review" — die Aufgaben des
CIO muessen genauer beschrieben werden. Dafuer brauchen wir strukturierte
Felder in der SOP-Step-Definition und im Task, plus eine neue Tabelle
fuer persistente Standardvorgaben (architecture_rules).

NEU in sop_steps (4 JSON-Felder):
  - task_types:           Liste erlaubter Task-Typen, die der CIO klassifizieren soll
                          (z.B. ["new_request", "change", "ticket", "bugfix"])
  - standards_refs:       Liste von Standardvorgaben-Referenzen, die der CIO pruefen soll
                          (z.B. ["SOA", "Microservices", "FastAPI"] — Verweise auf
                          architecture_rules.id oder openbrain-tags)
  - change_requirements:  Strukturierte Vorgaben fuer die Aenderungsbeschreibung
                          (z.B. [{"field": "files_to_change", "required": true}, ...])
  - subagent_requirements:Was der Subagent braucht (gem. Swarm-Anforderungen)
                          (z.B. [{"name": "model", "required": true}, ...])

NEU in tasks (1 Spalte + 3 JSON-Felder):
  - task_type:            Konkreter Typ, vom CIO klassifiziert
                          (z.B. "new_request" | "change" | "ticket" | "bugfix")
  - implementation_plan:  Strukturierte App-Aenderungs-Beschreibung (CIO ergaenzt)
                          (z.B. {"files": [...], "routes": [...], "api_changes": [...]})
  - standards_check:      Ergebnis der OpenBrain-Pruefung (CIO bewertet)
                          (z.B. {"checked_at": "...", "matches": [...], "missing": [...]})
  - subagent_readiness:   Bewertung der Subagent-Readiness (CIO prueft)
                          (z.B. {"model": "minimax-m3", "branch": "task/123", ...})

NEU Tabelle architecture_rules (Standardvorgaben persistent):
  - id, name, description, source (openbrain-tag | url | hardcoded),
    category (architecture | security | style | process | data),
    severity (must | should | may), is_active, created_at
  - Default-Seed mit den ME4-OpenBrain-Vorgaben
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === sop_steps: 4 JSON-Felder hinzufuegen ===
    op.add_column("sop_steps", sa.Column("task_types", sa.Text(), nullable=True))
    op.add_column("sop_steps", sa.Column("standards_refs", sa.Text(), nullable=True))
    op.add_column("sop_steps", sa.Column("change_requirements", sa.Text(), nullable=True))
    op.add_column("sop_steps", sa.Column("subagent_requirements", sa.Text(), nullable=True))

    # === tasks: task_type Spalte + 3 JSON-Felder ===
    op.add_column("tasks", sa.Column("task_type", sa.String(32), nullable=True))
    op.add_column("tasks", sa.Column("implementation_plan", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("standards_check", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("subagent_readiness", sa.Text(), nullable=True))

    # Index fuer task_type (haeufig gefiltert)
    op.create_index("idx_tasks_task_type", "tasks", ["task_type"], unique=False)

    # === Neue Tabelle architecture_rules (Standardvorgaben) ===
    op.create_table(
        "architecture_rules",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(64), nullable=False, server_default="openbrain"),
        # source: "openbrain" | "url" | "hardcoded" | "user"
        sa.Column("source_ref", sa.String(255), nullable=True),
        # source_ref: z.B. "openbrain-tag:SOA" oder "https://..."
        sa.Column("category", sa.String(64), nullable=False, server_default="architecture", index=True),
        # category: "architecture" | "security" | "style" | "process" | "data"
        sa.Column("severity", sa.String(16), nullable=False, server_default="should"),
        # severity: "must" (PFLICHT) | "should" (EMPFOHLEN) | "may" (OPTIONAL)
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_arch_rules_category_active", "architecture_rules",
                    ["category", "is_active"], unique=False)

    # === Default-Seed: ME4-OpenBrain-Vorgaben ===
    # Diese Vorgaben sind im OpenBrain als "Standardvorgaben für unsere Entwicklung"
    # festgelegt (User-Direktive 16.06.2026).
    op.execute("""
        INSERT INTO architecture_rules (id, name, description, source, source_ref, category, severity, is_active)
        VALUES
        ('arch-soa',           'Service-Oriented Architecture (SOA)',
         'Alles wird im Architektur-Geiste von SOA entwickelt. Lose gekoppelte Services mit klar definierten Verträgen.',
         'openbrain', 'openbrain-tag:SOA', 'architecture', 'must', 1),

        ('arch-microservices', 'Microservices-Architektur',
         'Jeder Service besteht aus Microservices. Eigenständige Deployments, eigene Datenhaltung, kein Shared-State zwischen Services.',
         'openbrain', 'openbrain-tag:Microservices', 'architecture', 'must', 1),

        ('arch-fastapi',       'Python 3.11+ / FastAPI als Backend-Standard',
         'Backend-Sprache/Framework: Python 3.11+ / FastAPI. Konsistenz mit ME4-Stack, ausgenommen explizite User-Direktive.',
         'openbrain', 'openbrain-tag:ME4-Stack', 'architecture', 'should', 1),

        ('arch-no-nodejs',     'Kein Node.js im Backend',
         'Backend-Konsistenz-Entscheidung: kein Node.js. Falls TypeScript noetig, dann als separater Service mit klarer Begruendung.',
         'openbrain', 'openbrain-tag:Stack-Policy', 'architecture', 'should', 1),

        ('arch-llm-primary',   'LLM: MiniMax M3 als PRIMARY, Ollama als Fallback',
         'Sub-Agents laufen mit MiniMax M3 (Provider: minimax). Ollama ist nur Fallback, nicht Standard.',
         'openbrain', 'openbrain-tag:LLM-Standard', 'architecture', 'should', 1),

        ('arch-swarm-roles',   'Sub-Agent-Rollen-Set',
         'Verfuegbare Sub-Agent-Rollen: pi-coder, pi-tester, pi-reviewer, pi-fixer, CIO, CEO-digital. Neue Rollen muessen dokumentiert sein.',
         'openbrain', 'openbrain-tag:Sub-Agents', 'process', 'must', 1),

        ('arch-cost-tracking', 'Token-Budget + Cost-Limit pro Sub-Agent',
         'Jeder Sub-Agent bekommt ein explizites Token-Budget und Cost-Limit. Cost-Tracking via cost-tracker Extension ist Pflicht.',
         'openbrain', 'openbrain-tag:Cost-Policy', 'process', 'must', 1),

        ('arch-git-branch',    'Git-Branch pro Task (Rollback-Sicherheit)',
         'Jeder Sub-Agent arbeitet in einem eigenen Git-Branch. Hauptbranch (main) wird nicht direkt veraendert. Rollback jederzeit moeglich.',
         'openbrain', 'openbrain-tag:Git-Workflow', 'process', 'must', 1),

        ('arch-task-locking',  'Task-Locking mit TTL',
         'Backend-API braucht LOCKED_BY-Feld + TTL, damit nicht zwei Worker den gleichen Task bearbeiten.',
         'openbrain', 'openbrain-tag:Concurrency', 'process', 'should', 1),

        ('arch-multi-tenant',  'Multi-Tenant-Architektur (Schema-per-Tenant)',
         'Mandantenfaehigkeit: Schema-per-Tenant. Kein Tenant sieht Daten eines anderen. Self-Hosting-Option muss moeglich sein.',
         'openbrain', 'openbrain-tag:Multi-Tenancy', 'architecture', 'should', 1)
    """)


def downgrade() -> None:
    # architecture_rules: Inhalte loeschen + Tabelle droppen
    op.drop_index("idx_arch_rules_category_active", table_name="architecture_rules")
    op.drop_table("architecture_rules")

    # tasks: 4 Spalten zurueck
    op.drop_index("idx_tasks_task_type", table_name="tasks")
    op.drop_column("tasks", "subagent_readiness")
    op.drop_column("tasks", "standards_check")
    op.drop_column("tasks", "implementation_plan")
    op.drop_column("tasks", "task_type")

    # sop_steps: 4 Spalten zurueck
    op.drop_column("sop_steps", "subagent_requirements")
    op.drop_column("sop_steps", "change_requirements")
    op.drop_column("sop_steps", "standards_refs")
    op.drop_column("sop_steps", "task_types")
