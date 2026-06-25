# Pi Dashboard 2.0 — Architektur

> **Status:** 15.06.2026 — v2.0-alpha (Setup)
> **Autor:** PI-Agent + User

## Übersicht

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (React 19 + Vite)                                      │
│  http://localhost:5181                                            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ REST + SSE
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (Python 3.14)                                  │
│  http://127.0.0.1:9220                                            │
│                                                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │  Routers   │  │  Services  │  │  Schemas   │                │
│  │ (HTTP/API) │  │ (Business) │  │ (Validate) │                │
│  └─────┬──────┘  └─────┬──────┘  └────────────┘                │
│        └──────┬───────┘                                           │
│               ▼                                                   │
│  ┌─────────────────────────┐                                    │
│  │  SQLAlchemy 2.0 ORM     │                                    │
│  │  (async + sync)        │                                    │
│  └─────┬───────────────────┘                                    │
└────────┼────────────────────────────────────────────────────────┘
         │ SQL
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Database                                                         │
│  - SQLite (dev): ./database/pi_dashboard.db                       │
│  - PostgreSQL (prod): via DATABASE_URL                            │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │ Alembic Migrations
         │
┌─────────────────────────────────────────────────────────────────┐
│  Migrations / Scripts                                             │
│  - scripts/migrate_v1_to_v2.py  (JSON → SQL)                     │
│  - scripts/backup_db.sh                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Datenbank-Schema (v2.0)

### Core-Tabellen

#### `projects`
| Spalte | Typ | Constraint | Beschreibung |
|--------|-----|------------|--------------|
| `id` | VARCHAR(32) | PK | UUID-Hash |
| `name` | VARCHAR(255) | NOT NULL | Projekt-Name |
| `description` | TEXT | | Kurzbeschreibung |
| `status` | VARCHAR(32) | DEFAULT 'active' | active/archived/closed |
| `mode` | VARCHAR(32) | DEFAULT 'preparation' | preparation/execution/paused/completed |
| `category` | VARCHAR(32) | DEFAULT 'new_request' | new_request/ticket/change (ITIL) |
| `created_at` | TIMESTAMP | NOT NULL | |
| `updated_at` | TIMESTAMP | NOT NULL | |
| `closed_at` | TIMESTAMP | NULL | Bei Status=closed |
| `metadata` | JSONB | | Flexibles JSON-Feld |

**Indizes:** `idx_projects_status`, `idx_projects_mode`, `idx_projects_created_at`

#### `tasks`
| Spalte | Typ | Constraint | Beschreibung |
|--------|-----|------------|--------------|
| `id` | VARCHAR(32) | PK | UUID-Hash |
| `project_id` | VARCHAR(32) | FK → projects.id | |
| `parent_id` | VARCHAR(32) | FK → tasks.id (self) | Sub-Tasks |
| `title` | VARCHAR(500) | NOT NULL | |
| `description` | TEXT | | |
| `status` | VARCHAR(32) | DEFAULT 'triage' | triage/todo/in_progress/review/block/done/waiting |
| `priority` | INT | DEFAULT 50 | 0-100 |
| `category` | VARCHAR(32) | DEFAULT 'new_request' | new_request/ticket/change (ITIL) |
| `assigned_role` | VARCHAR(64) | | pi-coder/pi-tester/... |
| `assigned_subagent` | VARCHAR(64) | | Konkreter Subagent |
| `iteration_count` | INT | DEFAULT 0 | |
| `order` | INT | DEFAULT 0 | Sortierung im Board |
| `created_at` | TIMESTAMP | NOT NULL | |
| `updated_at` | TIMESTAMP | NOT NULL | |
| `claimed_at` | TIMESTAMP | NULL | |
| `emergency` | BOOLEAN | DEFAULT FALSE | |
| `pricing_snapshot` | JSONB | NULL | Model, input/output_per_1m, snapshot_at, source |
| `tags` | JSONB | DEFAULT '[]' | Array von Tags |
| `success_criteria` | JSONB | DEFAULT '[]' | Array von Kriterien |
| `metadata` | JSONB | | |

**Indizes:**
- `idx_tasks_project_id` (FK)
- `idx_tasks_parent_id` (FK)
- `idx_tasks_status`
- `idx_tasks_priority` (DESC)
- `idx_tasks_assigned_role`
- `idx_tasks_created_at` (DESC)
- `idx_tasks_emergency` (partial WHERE emergency=TRUE)
- Composite: `idx_tasks_project_status` (project_id, status)

#### `task_history`
| Spalte | Typ | Constraint | Beschreibung |
|--------|-----|------------|--------------|
| `id` | BIGINT | PK auto-increment | |
| `task_id` | VARCHAR(32) | FK → tasks.id | |
| `ts` | TIMESTAMP | NOT NULL | |
| `event` | VARCHAR(64) | NOT NULL | status_changed/operator_dispatched/... |
| `agent` | VARCHAR(64) | | pi-coder, operator, system, user |
| `model` | VARCHAR(128) | | minimax/minimax-m3, ollama/gemma4:12b |
| `tokens_in` | INT | DEFAULT 0 | |
| `tokens_out` | INT | DEFAULT 0 | |
| `cost_usd` | DECIMAL(12,6) | DEFAULT 0 | |
| `details` | JSONB | | Event-spezifische Daten |

**Indizes:**
- `idx_history_task_id_ts` (task_id, ts DESC)
- `idx_history_event`
- `idx_history_agent`

#### `roles`
| Spalte | Typ | Constraint |
|--------|-----|------------|
| `id` | VARCHAR(32) | PK |
| `name` | VARCHAR(64) | UNIQUE NOT NULL |
| `description` | TEXT | |
| `provider` | VARCHAR(64) | |
| `model` | VARCHAR(128) | |
| `system_prompt` | TEXT | |
| `tool_whitelist` | JSONB | DEFAULT '[]' |
| `timeout_sec` | INT | DEFAULT 300 |
| `fresh_context` | BOOLEAN | DEFAULT TRUE |
| `estimated_savings_usd` | DECIMAL(10,4) | DEFAULT 0 |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

#### `token_usage` (Performance-Daten!)
| Spalte | Typ | Constraint | Beschreibung |
|--------|-----|------------|--------------|
| `id` | BIGINT | PK auto-increment | |
| `task_id` | VARCHAR(32) | FK → tasks.id | |
| `history_id` | BIGINT | FK → task_history.id | |
| `model` | VARCHAR(128) | NOT NULL | |
| `provider` | VARCHAR(64) | NOT NULL | |
| `role` | VARCHAR(64) | | |
| `tokens_in` | INT | NOT NULL | |
| `tokens_out` | INT | NOT NULL | |
| `cost_usd` | DECIMAL(12,6) | NOT NULL | |
| `input_per_1m` | DECIMAL(10,4) | | Snapshot-Preis |
| `output_per_1m` | DECIMAL(10,4) | Snapshot-Preis |
| `pricing_source` | VARCHAR(255) | | z.B. "platform.minimax.io" |
| `snapshot_at` | TIMESTAMP | | Wann Preis gesnapshottet |
| `recorded_at` | TIMESTAMP | NOT NULL | |

**Indizes:**
- `idx_token_task_id` (FK)
- `idx_token_model`
- `idx_token_provider`
- `idx_token_recorded_at` (DESC)
- `idx_token_role`

#### `model_pricing` (Provider-Preise persistent)
| Spalte | Typ | Constraint |
|--------|-----|------------|
| `id` | BIGINT | PK auto-increment |
| `provider` | VARCHAR(64) | NOT NULL |
| `model_id` | VARCHAR(128) | NOT NULL |
| `input_per_1m` | DECIMAL(10,4) | NOT NULL |
| `output_per_1m` | DECIMAL(10,4) | NOT NULL |
| `currency` | VARCHAR(8) | DEFAULT 'USD' |
| `source` | VARCHAR(255) | |
| `last_updated` | TIMESTAMP | NOT NULL |
| `note` | TEXT | |
| `is_default` | BOOLEAN | DEFAULT FALSE |

**Indizes:**
- UNIQUE `(provider, model_id)`
- `idx_pricing_provider`

### Weitere Tabellen

- `subtasks` — Relationen für Parent/Child
- `brainstorm_log` — Brainstorming-Einträge
- `requirements` — Anforderungsdokumente
- `review_pipelines` — 9-Schritt-Reviews
- `implementation_steps` — Implementation-Plan
- `completeness_clarifications` — Q&A aus NALABS-Review

## Warum SQL statt JSON?

| Vorteil | JSON | SQL |
|---------|------|-----|
| **Performance bei großen Datenmengen** | ❌ Lädt alles in den Speicher | ✅ Indizes, Pagination, Aggregationen |
| **Concurrent Writes** | ❌ Race-Conditions | ✅ Transaktionen, Row-Locks |
| **Schema-Evolution** | ❌ Ad-hoc | ✅ Alembic-Migrationen |
| **Analytics** | ❌ Manuelle Parsing | ✅ SQL-Views, Window-Functions |
| **Backup** | ✅ File-Copy | ✅ pg_dump / .backup |
| **Einfachheit** | ✅ Kein Setup | ⚠️ DB muss laufen |

**Für unseren Use-Case (Performance-Daten sammeln + analysieren) ist SQL klar überlegen.**

## Tech-Entscheidungen

### SQLite vs. PostgreSQL?

| | SQLite | PostgreSQL |
|--|--------|------------|
| **Setup** | Null (file-based) | Server nötig |
| **Concurrent Writes** | Eine zur Zeit | Multi |
| **Replication** | ❌ | ✅ |
| **JSONB** | Als Text (langsamer) | ✅ Native + Indizes |
| **Production-ready** | Single-User OK | Enterprise-grade |

**Entscheidung:** SQLite als **Default** (kein Server, file-based, perfekt für Single-User Dev). PostgreSQL **optional** für Multi-User / Production (Connection-String reicht).

### SQLAlchemy 2.0 Sync vs. Async?

**Entscheidung:** Beides unterstützen — Default **Sync** (einfacher für FastAPI-Routes), Async optional für SSE-Streams.

## Sicherheit

- **SQL-Injection:** SQLAlchemy-ORM verhindert automatisch (parametrisierte Queries)
- **API-Keys:** Bleiben in `~/.pi/agent/models.json` (außerhalb der DB)
- **Auth-Tokens:** Separate `auth.json` (außerhalb)
- **Backups:** Verschlüsselt + Off-site empfohlen

## SOP-Engine (Standard-Workflow)

**Modul:** `backend/app/services/sop_engine.py`
**Standard-SOP:** `7c86692be939` (8 Steps)

### Schritt-Verkettung

Die SOP `7c86692be939` ("Standard-Workflow Task") durchläuft **8 verkettete Steps**:

| Order | Step | Action | Agent | next_step_id | fail_step_id |
|-------|------|--------|-------|--------------|--------------|
| 0 | CIO Triage Review | llm_call | CIO | Step 1 | - |
| 1 | Worker Assignment | llm_call | pi-coder | Step 2 | Step 0 |
| 2 | Worker Implementation | spawn_swarm | pi-coder | Step 3 | Step 1 |
| 3 | Tester Code-Review | spawn_swarm | pi-tester | Step 4 | Step 2 |
| 4 | CIO Final-Review | spawn_swarm | CIO | Step 5 | Step 3 |
| 5 | Done | llm_call | system | Step 6 | - |
| 6 | Final Approval (CIO) | cio_final_review | CIO | Step 7 | Step 4 |
| 7 | Self-Evaluation | evaluate_outcome | system | - (End) | - |

### Defense-in-Depth: `_check_sop_completion()` (Task 7ce2066d5bd5, 25.06.2026)

**Problem:** Vor dem Fix hatten alle 8 Steps `next_step_id=None`. Damit endete die SOP-Instance nach dem ersten Step, und `_complete_instance()` setzte den Task pauschal auf `done` — **OHNE** dass Implementation, Review und Tests durchlaufen wurden.

**Fix:** Migration `scripts/migrate_sop_step_chaining.py` setzt `next_step_id` und `fail_step_id` für alle 8 Steps. Zusätzlich prüft `_check_sop_completion()` (Defense-in-Depth), ob die Instance alle Steps durchlaufen hat:

```python
if instance.task_id:
    sop_incomplete_reason = self._check_sop_completion(instance, step)
    if sop_incomplete_reason:
        # SOP unvollständig -> Task auf 'block', NICHT auf 'done'
        TaskService.set_status_sync(self.db, task.id, "block",
            reason=f"sop_incomplete:{instance.id}:{sop_incomplete_reason}")
```

**Verhalten:**
- Wenn `current_step.step_order < max_step_order`: Task auf `block` mit Reason `sop_incomplete`
- Wenn vorherige Steps fehlen in `sop_executions`: Task auf `block`
- Wenn alles OK: Task auf `done` (Normal-Flow)

**Migration-Script ausführen:**
```bash
python backend/scripts/migrate_sop_step_chaining.py --dry-run
python backend/scripts/migrate_sop_step_chaining.py  # Echter Lauf
python backend/scripts/migrate_sop_step_chaining.py --verify
```

**Regression-Tests:** `backend/tests/test_sop_step_chaining.py` (7 Tests, alle grün).

## Nächste Schritte

1. ✅ Schema-Design (dieses Dokument)
2. ⏭️ SQLAlchemy-Models implementieren
3. ⏭️ Alembic-Initial-Migration
4. ⏭️ Routers auf SQL umstellen
5. ⏭️ Migration-Script für v1.x → v2.0
6. ⏭️ Performance-Tests
7. ⏭️ Frontend anpassen
