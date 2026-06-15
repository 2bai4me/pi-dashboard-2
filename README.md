# Pi Dashboard 2.0

**Hermes-Style Web-Dashboard für den lokalen PI Coding Agent — mit SQL-Datenbank-Backend**

> **Status:** 🚧 In Planung / Setup (15.06.2026)
> **Version:** 2.0.0-alpha
> **Vorgänger:** [Pi Dashboard 1.x](https://github.com/2bai4me/pi-dashboard) (JSON-basiert)
> **Speicherort:** `D:\Entwicklung\PI-Dashboard 2`

---

## Was ist neu in 2.0?

| Aspekt | v1.x (aktuell) | v2.0 (diese Version) |
|--------|----------------|----------------------|
| **Persistenz** | JSON-Dateien (`tasks.json`, etc.) | **SQL-Datenbank** (SQLAlchemy 2.0 + SQLite/PostgreSQL) |
| **Performance-Daten** | In-Memory, schwer analysierbar | Persistente Tabellen, indizierbar, aggregierbar |
| **Schema-Migrationen** | Keine | **Alembic** für versionierte Schema-Changes |
| **Concurrency** | Race-Conditions bei Multi-Worker | Transaktionen, Row-Locks, Connection-Pool |
| **Backup-Strategie** | File-Copy | `pg_dump` (PG) / `.backup` (SQLite) |
| **Token-Analytics** | Manuell aus Logs | SQL-Views für Cost-per-Task, Per-Model, Per-Role |
| **Task-Historie** | JSON-Array im Task | Separate Tabelle mit Indizes |

**Alle anderen Features bleiben gleich:** Kanban, Echtzeit-Updates, Sub-Agents, Pricing-Snapshots, CIO-Rollen, etc.

---

## Tech-Stack

- **Backend:** Python 3.14, FastAPI 0.136, SQLAlchemy 2.0.49, Alembic 1.18, Pydantic v2
- **Database:** SQLite (default, file-based) oder PostgreSQL (production, optional)
- **Frontend:** React 19, Vite, TanStack Query, Recharts, TailwindCSS
- **ORM:** SQLAlchemy 2.0 mit Async Support (aiosqlite / asyncpg)
- **Migrationen:** Alembic
- **Tests:** pytest, pytest-asyncio

---

## Verzeichnisstruktur

```
PI-Dashboard 2/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI-App
│   │   ├── config.py            # Settings (Pydantic)
│   │   ├── db/
│   │   │   ├── base.py          # SQLAlchemy Base + Session
│   │   │   └── init_db.py       # DB-Initialization
│   │   ├── models/              # SQLAlchemy Models
│   │   │   ├── project.py
│   │   │   ├── task.py
│   │   │   ├── history.py
│   │   │   ├── role.py
│   │   │   ├── token_usage.py
│   │   │   ├── pricing.py
│   │   │   └── ...
│   │   ├── schemas/             # Pydantic-Schemas (Request/Response)
│   │   ├── routers/             # FastAPI-Routes
│   │   ├── services/            # Business-Logic (Operator, Dispatcher, etc.)
│   │   └── migrations/          # Alembic-Migrationen
│   ├── tests/
│   ├── requirements.txt
│   ├── alembic.ini
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/               # React-Pages
│   │   ├── components/          # Wiederverwendbare Komponenten
│   │   └── api/                 # API-Client
│   ├── package.json
│   └── vite.config.ts
├── database/
│   ├── pi_dashboard.db          # SQLite-Datei (dev)
│   └── migrations/              # SQL-Dumps fuer Backup
├── docs/
│   ├── ARCHITECTURE.md
│   ├── MIGRATION_PLAN.md
│   └── CHANGELOG.md
├── scripts/
│   ├── migrate_v1_to_v2.py      # JSON → SQL Migration
│   ├── backup_db.sh
│   └── restore_db.sh
├── .gitignore
└── README.md
```

---

## Quickstart (dev)

```bash
# 1. Repository klonen
git clone <repo-url>
cd "PI-Dashboard 2"

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# DB-Initialisierung + Migrationen
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 9220 --reload

# 3. Frontend (neues Terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5181

# 4. Migration von v1.x (optional)
python scripts/migrate_v1_to_v2.py
```

---

## Migration v1.x → v2.0

Wenn 2.0 stabil läuft, können alle Daten aus der JSON-basierten v1 automatisch migriert werden:

```bash
python scripts/migrate_v1_to_v2.py \
  --source "C:/Users/uwean/.pi/agent/kanban" \
  --target "D:/Entwicklung/PI-Dashboard 2/database/pi_dashboard.db"
```

**Was wird migriert:**
- ✅ Projects (mit Brainstorming, Requirements)
- ✅ Tasks (inkl. History, Sub-Tasks, Pricing-Snapshots)
- ✅ Roles + Sub-Agents
- ✅ Cost-Tracking (Token + USD)
- ✅ Review-Pipelines
- ✅ Implementation-Records

**Was bleibt v1-spezifisch:**
- ❌ Settings (bleiben in `~/.pi/agent/settings.json`)
- ❌ Models (bleiben in `~/.pi/agent/models.json`)
- ❌ Sessions (separates System, wird evtl. später migriert)

---

## Roadmap

| Phase | Status | Inhalt |
|-------|--------|--------|
| **v2.0-alpha** (Q2 2026) | 🚧 Setup | Verzeichnis, Schema, Migrations-Tool |
| **v2.0-beta** (Q3 2026) | 📋 Geplant | Backend-Endpoints auf SQL umstellen, Frontend anpassen |
| **v2.0-rc** (Q3 2026) | 📋 Geplant | Performance-Tests, Alembic-Migrationen, Backup-Strategie |
| **v2.0-stable** (Q4 2026) | 📋 Geplant | Migration aller v1-Daten, v1 deprecation |

---

## Lizenz

MIT
