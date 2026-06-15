# v1.x → v2.0 Deprecation Timeline

> **Status:** Aktiv (15.06.2026)
> **Betrifft:** Pi Dashboard 1.x (JSON-basiert)
> **Nachfolger:** Pi Dashboard 2.0 (SQL-basiert, Port 9220)

## Zeitplan

| Datum | Event | Aktion erforderlich |
|-------|-------|---------------------|
| 15.06.2026 | v2.0.0-rc released | Migration jetzt moeglich (siehe unten) |
| 15.07.2026 | v2.0.0-stable | Empfehlung: alle v1-Setups migrieren |
| 15.08.2026 | v1-Setups werden read-only | Kein neuer Task-Create mehr via v1 |
| 15.09.2026 | v1-Endpoint eingeschraenkt | GET /api/kanban/* gibt 410 Gone zurueck |
| 15.10.2026 | v1-Repository archived | https://github.com/2bai4me/pi-dashboard als deprecated markiert |
| 15.12.2026 | v1-Read-Only-Layer entfernt | Nur noch v2-Repository aktiv |

## Was passiert beim Wechsel?

### v1-Architektur
- **Backend:** Python 3.11, JSON-Dateien (`~/.pi/agent/kanban/tasks.json`, etc.)
- **Frontend:** React 19 + Vite auf Port 5180
- **Datenformat:** Flat JSON-Arrays pro Entity

### v2-Architektur
- **Backend:** Python 3.14, FastAPI + SQLAlchemy 2.0, SQLite/PostgreSQL auf Port 9220
- **Frontend:** React 19 + Vite auf Port 5181
- **Datenformat:** SQL-Tabellen (Projects, Tasks, TaskHistory, Roles, TokenUsage, ModelPricing, BrainstormEntry, RequirementDoc, ReviewPipeline, ImplementationStep, EventLog)
- **Alembic-Migrationen:** Versioniertes Schema
- **Pricing-Snapshot-Pattern:** Cost-Berechnung mit beim Task-Start eingefrorenem Preis
- **SSE Live-Updates:** SQLite-basiertes Long-Polling
- **SQL Cost-Aggregation:** by_model, by_role, by_provider, by_day

## Migrations-Schritte (manuell)

### Schritt 1: Migration-Script ausfuehren

```bash
cd "D:/Entwicklung/PI-Dashboard 2"
python scripts/migrate_v1_to_v2.py
# Output: 2 Projects, 45 Tasks, 47 History-Eintraege, 10 Pricing-Records migriert
```

Was wird migriert:
- ✅ Projects (inkl. Brainstorming, Requirements, Status, Mode)
- ✅ Tasks (inkl. Title, Description, Status, Priority, Category [ITIL])
- ✅ Task-History (v1 hatte JSON-Array, v2 hat dedizierte Tabelle)
- ✅ Roles (6 Default + Custom)
- ✅ Model-Pricing (provider/model/input/output/USD)
- ⚠️ TokenUsage: leer (v1 erfasste Tokens nicht)
- ⚠️ Sessions: NICHT migriert (separates System, v2 hat keine Sessions)
- ⚠️ Sub-Tasks: bleiben erhalten (parent_id)

### Schritt 2: Beide Backends parallel laufen lassen (1 Woche)

```bash
# v1 (Port 9219, JSON-File-basiert)
python /c/Users/uwean/.pi-kanban/pi-kanban.py --port 9219

# v2 (Port 9220, SQL-basiert)
cd "D:/Entwicklung/PI-Dashboard 2/backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 9220
```

Waehrend dieser Woche:
- v1 ist Read-Write (Hauptsystem)
- v2 ist Read-Only (zur Verifikation, dass Migration korrekt ist)
- Frontend kann zwischen v1 (Port 5180) und v2 (Port 5181) wechseln

### Schritt 3: Cutover

```bash
# v1 stoppen
powershell -Command "Get-Process python | Where-Object { \$_.CommandLine -like '*pi-kanban*' } | Stop-Process"

# v2 ist jetzt das Hauptsystem
# DATABASE_URL aus .env sicherstellen: sqlite:///D:/Entwicklung/PI-Dashboard 2/database/pi_dashboard.db
```

### Schritt 4: v1-Read-Only-Layer (1 Monat, ab 15.08.)

v1-Endpoints geben 410 Gone zurueck, mit Hinweis auf v2.

### Schritt 5: v1-Archivierung (15.10.2026)

GitHub-Repository wird als "deprecated" markiert:
- README mit grossem Warnhinweis
- Issues werden geschlossen
- PRs werden nicht mehr akzeptiert

## Was wird NICHT migriert?

- **Sessions:** v2 hat keine Sessions (anderes Auth-Modell)
- **CronJobs:** v1 hatte crons.json, v2 hat sie nicht (TODO v2.1)
- **Webhooks:** v1 hatte webhooks.json, v2 hat sie nicht (TODO v2.1)
- **MCPServers:** v1 hatte mcp.json, v2 hat sie nicht (TODO v2.1)
- **OpenBrain-Thoughts:** Bleiben in OpenBrain (extern)

## Bei Problemen: Rollback

Falls die Migration fehlschlaegt:

```bash
# v1 ist noch da (JSON-File-basiert, nie angefasst)
# v2-DB loeschen + neu migrieren
rm database/pi_dashboard.db
alembic upgrade head
python scripts/migrate_v1_to_v2.py
```

## Haeufige Probleme

### Problem 1: v1-Tasks haben andere Category-Werte
v1 hatte keine ITIL-Kategorien. v2 setzt default `new_request` fuer alle migrierten Tasks. Manuell nachjustieren via UI oder:
```sql
UPDATE tasks SET category = 'change' WHERE title LIKE '%Migration%' AND category = 'new_request';
```

### Problem 2: Pricing-Snapshots fehlen bei migrierten Tasks
v1 hatte keine Pricing-Snapshots. v2-Tasks haben `pricing_snapshot=null` nach Migration. Das ist OK — Cost wird dann mit aktuellem Provider-Preis berechnet. Loesung: Tasks neu auto-claimen (PUT /status=todo), dann wird Snapshot angelegt.

### Problem 3: Sub-Tasks ohne Parent
Falls v1-Tasks mit Sub-Tasks migriert wurden, aber der Parent-Task wurde geloescht: Sub-Tasks haben `parent_id` auf nicht-existenten Task. Loesung: Cleanup-Script laufen lassen:
```python
# scripts/cleanup_orphan_subtasks.py (TODO)
UPDATE tasks SET parent_id = NULL
WHERE parent_id NOT IN (SELECT id FROM tasks);
```

## Fragen?

GitHub Issues: https://github.com/2bai4me/pi-dashboard-2/issues
OpenBrain: `openbrain_search("v1 v2 migration")` fuer vorhandene Diskussionen
