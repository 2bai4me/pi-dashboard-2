# Pi Dashboard 2.0

**Hermes-Style Web-Dashboard für den lokalen PI Coding Agent — mit SQL-Datenbank + Multi-Agent-Swarm**

> **Status:** ✅ **Production-Ready für Software-Entwicklung**
> **Version:** 2.0.0-rc (Multi-Agent-Swarm komplett)
> **Vorgänger:** [Pi Dashboard 1.x](https://github.com/2bai4me/pi-dashboard) (JSON-basiert)
> **Speicherort:** `D:\Entwicklung\PI-Dashboard 2`

---

## 🎯 Hauptfeatures

| Feature | Status | Details |
|---------|:------:|---------|
| **SQL-Datenbank** | ✅ | SQLite/PostgreSQL via SQLAlchemy 2.0 |
| **Multi-Agent-Swarm** | ✅ | 8-Stufen-SOP mit parallel + competitive Swarms |
| **Auto-Fix-Loop** | ✅ | Bei Score < 90 automatisch zur Stage 3 zurück |
| **Live-Updates** | ✅ | SSE-Events + Frontend-Polling |
| **Cost-Tracking** | ✅ | $1.55/Task, $5/Stunde global |
| **PostgreSQL-Support** | ✅ | Mit Alembic-Migration |
| **Echte LLM-Worker** | ✅ | Via `PI_SWARM_USE_REAL=1` |

---

## 🚀 Quickstart (5 Minuten)

```bash
# 1. Repository klonen
git clone https://github.com/2bai4me/pi-dashboard-2
cd "PI-Dashboard 2"

# 2. Backend starten
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
# MIT echten Workern (Multi-Agent-Swarm aktiviert):
set PI_SWARM_USE_REAL=1
python -m uvicorn app.main:app --host 127.0.0.1 --port 9220 --reload

# 3. Frontend starten (neues Terminal)
cd ../frontend
npm install
npm run dev
# → http://localhost:5181

# 4. Multi-Agent-Swarm testen
curl -X POST http://127.0.0.1:9220/api/swarms \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "dein-task-id",
    "stage_key": "stage2_implementation",
    "workers": [
      {"role": "pi-coder", "variant": "minimalist"},
      {"role": "pi-coder", "variant": "robust"},
      {"role": "pi-coder", "variant": "performant"}
    ]
  }'
```

---

## 🐝 Multi-Agent-Swarm (Kern-Feature)

### Architektur

Die Standard-SOP (`7c86692be939`) durchläuft **8 Stufen**:

```
#0  CIO Triage Review            [single]       $0.05
#1  Lead Planning (pi-architect)  [single]       $0.10
#2  Swarm Implementation         [parallel]     $0.50  (3× pi-coder)
#3  Multi-Test Swarm             [parallel]     $0.30  (3× pi-tester)
#4  Competitive Review           [competitive]  $0.20  (3× reviewer)
#5  Auto-Fix (Score < 90)        [single]       $0.30
#6  Final Approval (CIO)         [single]       $0.05
#7  Self-Evaluation              [single]       $0.05
─────────────────────────────────────────────────────
TOTAL                                                   $1.55/Task
```

### Swarm-Typen

| Typ | Workers | Merge | Wann nutzen |
|-----|---------|-------|-------------|
| `single` | 1 | n/a | Triage, Planning, Final |
| `parallel` | 2-5 | `reviewer_picks_best` / `merge_all` | Implementation, Tests |
| `competitive` | 2-3 | `consensus_score` | Review, Architektur |

### Worker-Varianten

| Swarm | Varianten | Zweck |
|-------|-----------|-------|
| **Implementation** | `minimalist`, `robust`, `performant` | 3 verschiedene Ansätze parallel |
| **Tests** | `unit`, `integration`, `performance` | 3 Test-Perspektiven |
| **Review** | `quality`, `bugs`, `robustness` | 3 Reviewer-Sichten |

### API-Endpoints

```bash
# Swarm starten (Stage-Default-Config)
POST /api/swarms
Body: {
  "task_id": "task-uuid",
  "stage_key": "stage2_implementation",  # oder volle workers-Liste
  "workers": [...],
  "max_cost_usd": 0.50
}

# Swarm-Status abfragen
GET /api/swarms/{swarm_id}

# Swarms für Task listen
GET /api/swarms?task_id={task_id}

# Live-Updates via SSE
GET /api/swarms/{swarm_id}/events
```

### Frontend-Integration

```tsx
import { SwarmStatusCard } from "../components/SwarmStatusCard"

<SwarmStatusCard taskId={task.id} />
```

Zeigt alle laufenden/abgeschlossenen Swarms eines Tasks mit Worker-Progress.

---

## 🛠️ Tech-Stack

- **Backend:** Python 3.14, FastAPI 0.136, SQLAlchemy 2.0.49, Alembic 1.18, Pydantic v2
- **Database:** SQLite (default) / PostgreSQL (production)
- **Frontend:** React 19, Vite 8, TanStack Query, Recharts
- **LLM-Integration:** SubAgent-Spawn via `subagent_service` (MCP-over-ZMQ)
- **Cost-Tracking:** Per-Task + Global Rate-Limit
- **Tests:** pytest (Backend), Vitest (Frontend)

---

## 📁 Verzeichnisstruktur

```
PI-Dashboard 2/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI-App
│   │   ├── services/
│   │   │   ├── swarm_spawner.py     # Phase 0-2: Multi-Agent-Swarm
│   │   │   ├── task_metrics.py      # Phase 5+7+8: Auto-Fix, Metriken, Cost-Guard
│   │   │   ├── sop_engine.py        # Phase 4: spawn_swarm-Action
│   │   │   └── subagent_service.py  # Phase 15: Echte SubAgent-Spawn
│   │   ├── routers/
│   │   │   ├── swarm.py             # POST/GET /api/swarms
│   │   │   └── swarm_events.py      # GET /api/swarms/{id}/events (SSE)
│   │   ├── models/                  # SQLAlchemy 2.0 Models (16 Tabellen)
│   │   └── migrations/               # Alembic (10+ Migrationen)
│   ├── tests/                        # 166 Tests grün
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── SwarmStatusCard.tsx  # Phase 6: Live-Swarm-Anzeige
│   │   ├── pages/                    # 28 Pages
│   │   └── api.ts                    # inkl. swarms.listByTask/spawn
│   └── package.json
├── docs/
│   ├── SWARM_SPAWNER_SPEC.md        # Komplette Architektur
│   ├── ARCHITECTURE.md
│   ├── QUALITY_STANDARD.md
│   └── evaluations/                  # 20+ Post-Task-Evals
└── scripts/
    └── migrate_v1_to_v2.py
```

---

## ⚙️ Konfiguration

### Backend (.env)

```env
# Database
DATABASE_URL=sqlite:///./database/pi_dashboard.db
# ODER PostgreSQL:
# DATABASE_URL=postgresql+psycopg://user:pass@localhost/pi_dashboard

# Auth
AUTH_ENABLED=false
JWT_SECRET=/bG+hvkjO0g9mf5QObv5WZzcEdTxxBkvmUdUFxZTvac=

# Multi-Agent-Swarm (Phase 15)
PI_SWARM_USE_REAL=1  # Echte SubAgent-Calls statt Mock (default: 0)

# MCP-over-ZMQ
PI_MCP_ROUTER_ENDPOINT=tcp://127.0.0.1:5555
PI_MCP_PUB_ENDPOINT=tcp://127.0.0.1:5556

# Rate-Limit (optional)
RATE_LIMIT_PER_MINUTE=120
```

### Frontend (vite.config.ts)

Frontend proxied `/api/*` → `http://127.0.0.1:9220`.

---

## 🧪 Tests

### Backend (pytest)
```bash
cd backend
pytest  # 166 Tests
pytest tests/test_swarm_spawner.py -v
pytest tests/test_task_metrics.py -v
```

### Frontend (Vitest)
```bash
cd frontend
npm test  # 26 Tests
npm run test:watch  # Live
npm run test:coverage  # Coverage-Report
```

---

## 📊 SOP-Stage-Cost-Limits

| Stage | Limit | Zweck |
|-------|-------|-------|
| Triage | $0.05 | Schnelle Bewertung |
| Planning | $0.10 | Architektur-Plan |
| Implementation | $0.50 | 3-Worker-Parallel |
| Multi-Test | $0.30 | 3-Worker-Parallel |
| Competitive Review | $0.20 | 3-Worker-Konsens |
| Auto-Fix | $0.30 | Iteration-Loop |
| Final Approval | $0.05 | Quality-Gate |
| Self-Evaluation | $0.05 | Metriken + OpenBrain |
| **Total** | **$1.55** | pro Task |

**Global Rate-Limit:** $5/Stunde (alle Swarms kombiniert).

---

## 🚦 Deployment

### Development
```bash
# Backend mit Hot-Reload
cd backend && uvicorn app.main:app --reload --port 9220

# Frontend mit HMR
cd frontend && npm run dev
```

### Production (PostgreSQL)

```bash
# 1. PostgreSQL vorbereiten
sudo -u postgres createdb pi_dashboard
sudo -u postgres createuser pi_dashboard

# 2. Migration
export DATABASE_URL="postgresql+psycopg://pi_dashboard:***@localhost/pi_dashboard"
cd backend
alembic upgrade head

# 3. Backend (via gunicorn)
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:9220

# 4. Frontend (statisches Build)
cd ../frontend
npm run build
# → dist/ auf nginx/Apache deployen
```

### Docker (geplant)

```dockerfile
# siehe docker-compose.yml (TODO)
```

---

## 📚 Dokumentation

- **[SWARM_SPAWNER_SPEC.md](docs/SWARM_SPAWNER_SPEC.md)** — Komplette Swarm-Architektur
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — System-Architektur
- **[QUALITY_STANDARD.md](docs/QUALITY_STANDARD.md)** — PI-Dashboard Quality Standard (PQS)
- **[OPENBRAIN_DEV_GUIDE.md](docs/OPENBRAIN_DEV_GUIDE.md)** — Agent-Development-Guide
- **[evaluations/](docs/evaluations/)** — 20+ Post-Task-Evals

---

## 🐛 Troubleshooting

### "Echte Worker spawnen nicht"

```bash
# Sicherstellen, dass PI_SWARM_USE_REAL gesetzt ist
set PI_SWARM_USE_REAL=1
# ODER per SwarmConfig
curl -X POST ... -d '{"use_real_workers": true, ...}'
```

### "Swarm cost > max_cost_usd"

Der Swarm hat sein Cost-Limit überschritten. Logs prüfen:
```bash
tail -f logs/backend-phase12.err.log | grep "Cost-Limit"
```

### "Worker timeout"

Default: 600s. Erhöhen via:
```json
{"timeout_sec": 1800, ...}
```

### "Auto-Fix-Loop triggert nicht"

Score muss < 90 sein UND `consensus_score` muss in `task.meta` persistiert sein (passiert automatisch bei Competitive-Swarm).

---

## 🤝 Contributing

1. Fork + Feature-Branch
2. Tests schreiben (`pytest` Backend, `vitest` Frontend)
3. PQS-Score ≥ C (siehe `docs/QUALITY_STANDARD.md`)
4. PR mit Post-Task-Evaluation (`docs/evaluations/`)

---

## 📜 Lizenz

MIT

---

## 🎉 Status

**Multi-Agent-Swarm komplett funktional** — von Spec bis Live-Test mit Task 13b322a2b926.

16 Phasen implementiert, 192 Tests grün, 150 Endpoints, 1 kritischer Bug gefixt.

**Bereit für Software-Entwicklungs-Einsatz.**