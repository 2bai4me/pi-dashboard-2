# PostgreSQL Setup Guide (Pi Dashboard 2.0)

> **Stand:** 15.06.2026
> **Status:** Doku-Complete, Live-Test ausstehend (kein PG-Server lokal vorhanden)

## Schnellstart (3-Schritte)

### 1. PostgreSQL installieren

```bash
# Windows: PostgreSQL 16+ von postgresql.org
# Linux: sudo apt install postgresql-16
# macOS: brew install postgresql@16
# Docker (empfohlen fuer Dev):
docker run -d --name pi-dashboard-pg -p 5432:5432 \
  -e POSTGRES_USER=pi_dashboard -e POSTGRES_PASSWORD=dev-password \
  -e POSTGRES_DB=pi_dashboard postgres:16
```

### 2. Connection-String setzen

In `backend/.env` (aus `.env.example` kopieren):

```bash
# SQLite (default, kein Server noetig)
# DATABASE_URL=sqlite:///D:/Entwicklung/PI-Dashboard 2/database/pi_dashboard.db

# PostgreSQL (production)
DATABASE_URL=postgresql+psycopg://pi_dashboard:dev-password@localhost:5432/pi_dashboard
```

### 3. Migrationen ausfuehren

```bash
cd backend
alembic upgrade head
# Tabellen werden automatisch angelegt (oder gemigrated)
```

Backend starten:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 9220
```

## Architektur-Unterschiede SQLite vs PostgreSQL

| Aspekt | SQLite | PostgreSQL |
|--------|--------|-------------|
| **Concurrency** | Single-Writer | Multi-Writer mit Row-Locks |
| **JSON-Spalten** | `Text` (kein JSONB) | `JSONB` mit Indizes |
| **Full-Text-Search** | FTS5 (separat) | `tsvector` (nativ) |
| **Replication** | Nein | Ja (Streaming + Logical) |
| **Backups** | `.backup()` API | `pg_dump` + WAL-Archiving |
| **Production-Skalierung** | ~100k Rows | Milliarden Rows |
| **Connection-String** | `sqlite:///path/to/db.db` | `postgresql+psycopg://user:pw@host/db` |

## Code-Anpassungen fuer PostgreSQL

### 1. JSON-Spalten (TypeDecorator)

Aktuelle Implementierung in `backend/app/models/task.py`:

```python
class JSONType(TypeDecorator):
    """JSON-Typ, der fuer SQLite zu Text serialisiert und fuer PostgreSQL JSONB nutzt."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None: return None
        if dialect.name == "postgresql": return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def process_result_value(self, value, dialect):
        if value is None: return None
        if dialect.name == "postgresql": return value
        if isinstance(value, (dict, list)): return value
        try: return json.loads(value)
        except (json.JSONDecodeError, TypeError): return value
```

**Verhalten:**
- SQLite: `Text` (serialisiert Python-Listen/-Dicts zu JSON-String)
- PostgreSQL: `JSONB` (nativ, mit Index-Support fuer `@@ jsonb_path_ops`)

### 2. Alembic-Migrationen

Alembic-Autogenerate funktioniert fuer beide DBs. Beim Generieren der ersten PG-Migration:

```bash
# Mit SQLite-DB:
alembic revision --autogenerate -m "initial_schema"
# Alembic erstellt saubere CREATE TABLE-Anweisungen

# Mit PostgreSQL-DB:
alembic upgrade head  # Erst SQLite-Schema anwenden
alembic revision --autogenerate -m "initial_schema_pg"
# Alembic erkennt Unterschiede (z.B. JSONB statt Text) und generiert Migration
```

### 3. Connection-Pooling

Aktuelle Config in `backend/app/config.py`:

```python
DB_POOL_SIZE: int = 5
DB_MAX_OVERFLOW: int = 10
```

**PostgreSQL-Empfehlung:**
- `DB_POOL_SIZE=20` (mehr parallele Connections)
- `DB_MAX_OVERFLOW=40` (Spitzenlast)
- `pool_pre_ping=True` (Connection-Health-Check)

## Haeufige Probleme + Loesungen

### Problem 1: `psycopg2-binary` nicht installiert
```
ImportError: No module named 'psycopg2'
```
**Loesung:** `pip install psycopg2-binary` (bereits in `requirements.txt`)

### Problem 2: Connection refused
```
sqlalchemy.exc.OperationalError: could not connect to server: Connection refused
```
**Loesung:** PG-Server muss laufen. Check: `pg_isready -h localhost -p 5432`

### Problem 3: Auth-Fehler
```
psycopg2.OperationalError: FATAL: password authentication failed for user "pi_dashboard"
```
**Loesung:** User + Passwort in `.env` korrekt setzen. PG: `ALTER USER pi_dashboard PASSWORD 'new-pw';`

### Problem 4: JSONB-Spalten nicht nutzbar
Aktueller TypeDecorator funktioniert, aber fuer Performance bei haeufigen JSON-Queries sollte man in v2.0-stable:
- `JSONB_PATH_OPS` Index hinzufuegen
- `GIN`-Index fuer Key-Lookups

## Migrations-Script fuer SQLite → PostgreSQL

```python
# scripts/migrate_sqlite_to_postgres.py (TODO v2.0-stable)
import sqlite3
import psycopg2
from pathlib import Path

def migrate():
    sqlite_conn = sqlite3.connect('database/pi_dashboard.db')
    pg_conn = psycopg2.connect(...)
    # Tables in korrekter Reihenfolge (Foreign-Key-Constraints)
    tables = ['roles', 'projects', 'tasks', 'task_history', 'token_usage',
              'model_pricing', 'brainstorm_entries', 'requirement_docs',
              'review_pipelines', 'implementation_steps', 'event_log']
    for table in tables:
        # Schema kopieren
        # Daten kopieren (mit JSON-Deserialisierung)
        # Indices neu erstellen
    print('Migration complete')
```

## Performance-Empfehlungen (PostgreSQL)

```sql
-- 1. JSONB GIN-Index fuer schnelle Key-Lookups
CREATE INDEX idx_tasks_meta_gin ON tasks USING GIN (meta);

-- 2. Partial Index fuer haeufige Filter
CREATE INDEX idx_tasks_emergency_true ON tasks (priority DESC, created_at)
  WHERE emergency = TRUE;

-- 3. Materialized View fuer teure Analytics
CREATE MATERIALIZED VIEW mv_task_cost_summary AS
SELECT
    project_id, model, provider, role,
    SUM(tokens_in) as tokens_in_total,
    SUM(tokens_out) as tokens_out_total,
    SUM(cost_usd) as cost_total,
    COUNT(*) as calls
FROM token_usage
GROUP BY project_id, model, provider, role;
-- Refresh: REFRESH MATERIALIZED VIEW CONCURRENTLY mv_task_cost_summary;

-- 4. EXPLAIN-Query fuer Query-Plan-Analyse
EXPLAIN (ANALYZE, BUFFERS)
SELECT t.*, COUNT(h.id) as events
FROM tasks t LEFT JOIN task_history h ON h.task_id = t.id
WHERE t.project_id = $1 AND t.status = $2
GROUP BY t.id;
```

## Backup-Strategie (PostgreSQL)

```bash
# Taeglich (cronjob)
pg_dump -h localhost -U pi_dashboard pi_dashboard | gzip > /backup/pi_dashboard-$(date +\%Y\%m\%d).sql.gz

# Point-in-Time-Recovery (PITR): WAL-Archiving aktivieren
# postgresql.conf: wal_level=replica, archive_mode=on, archive_command='cp %p /wal-archive/%f'
```

## Nächste Schritte

1. **PostgreSQL-Server bereitstellen** (Docker, lokal, oder Cloud)
2. **DATABASE_URL in `.env` setzen** (Connection-String siehe oben)
3. **`alembic upgrade head`** ausfuehren
4. **Backend starten + Health-Check** (`GET /api/health`)
5. **Migration-Test:** SQLite-DB nach PostgreSQL importieren (siehe `migrate_sqlite_to_postgres.py`)
6. **Performance-Vergleich:** SQLite vs PostgreSQL mit EXPLAIN ANALYZE
