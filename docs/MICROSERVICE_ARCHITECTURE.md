# PI-Dashboard 2.0 — Microservice-Architektur

> **Stand:** 20.06.2026  
> **Version:** 2.0.0-rc  
> **Status:** Refactoring von monolithischer Architektur zu fachlichen Microservices

---

## 1. Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────┐
│                        PI-Dashboard 2.0                         │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  Auth     │  │  Task    │  │  Project │  │  SOP Engine   │  │
│  │  Service  │  │  Service │  │  Service │  │  Service      │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │              │              │               │          │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌──────┴───────┐  │
│  │  Agent   │  │  Pricing │  │  LLM    │  │  Sub-Agent   │  │
│  │  Question│  │  Service │  │  Service│  │  Service     │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │              │              │               │          │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌──────┴───────┐  │
│  │  Board   │  │  Worker  │  │  Event   │  │  Analytics   │  │
│  │  Operator│  │  Service │  │  Service │  │  Service     │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Shared: id_generator, exceptions, config, db           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Service-Verzeichnis

Alle Microservices befinden sich unter `backend/app/services/micro/`.

| # | Service | Datei | Verantwortung |
|---|---------|-------|---------------|
| 1 | **Auth Service** | `auth_service.py` | JWT, Login, Token-Validierung, Rollen |
| 2 | **Task Service** | `task_service.py` | Task-CRUD, Status-Wechsel, History |
| 3 | **Project Service** | `project_service.py` | Projekt-CRUD, Brainstorming, Requirements |
| 4 | **SOP Engine Service** | `sop_engine_service.py` | SOP-Ausführung, Rules, Instances |
| 5 | **SOP CRUD Service** | `sop_crud_service.py` | SOP-Definitionen, Steps, BPMN/UML |
| 6 | **Agent Question Service** | `agent_question_service.py` | Fragen, Eskalation, Antworten |
| 7 | **Pricing Service** | `pricing_service.py` | Preise, Snapshots, Kosten-Tracking |
| 8 | **LLM Service** | `llm_service.py` | LLM-API-Wrapper (MiniMax, Kimi, Ollama) |
| 9 | **Sub-Agent Service** | `sub_agent_service.py` | Sub-Agent-Spawning (RCE-gehärtet) |
| 10 | **Board Operator Service** | `board_operator_service.py` | Watchdog, Heartbeat, Live-Boards |
| 11 | **Worker Service** | `worker_service.py` | Autonome Task-Bearbeitung via LLM |
| 12 | **Event Service** | `event_service.py` | SSE, Event-Bus, Inter-Service-Kommunikation |
| 13 | **Analytics Service** | `analytics_service.py` | Performance, Kosten-Reports, Statistik |
| 14 | **Credential Service** | `credential_service.py` | API-Keys verschlüsselt verwalten |
| 15 | **TTS Service** | `tts_service.py` | Text-to-Speech (MiniMax) |

### Shared Utilities (keine Services, aber von allen genutzt)

| # | Utility | Datei | Verwendung |
|---|---------|-------|------------|
| U1 | **ID Generator** | `utils/id_generator.py` | Zentrale ID-Erzeugung (ersetzt 12× secrets.token_hex) |
| U2 | **Exceptions** | `utils/exceptions.py` | 16 Exception-Typen für einheitliche Fehlerbehandlung |
| U3 | **Config** | `config.py` | Pydantic-Settings (unverändert) |
| U4 | **DB Base** | `db/base.py` | SQLAlchemy-Session (unverändert) |
| U5 | **Status Labels** | `utils/status_labels.py` | DB-Key → Display-Name Mapping |

---

## 3. Service-Detailbeschreibungen

### 3.1 Auth Service

**Datei:** `backend/app/services/micro/auth_service.py`

**Verantwortung:** Authentifizierung und Autorisierung der gesamten API.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `create_token(username, role, ttl_hours)` | str, str, int | str (JWT) | Erstellt JWT-Token mit HS256-Signatur |
| `verify_token(token)` | str | Dict (Claims) | Validiert Token, gibt Claims zurück |
| `require_auth(credentials)` | HTTPAuthorizationCredentials | str (Username) | **FastAPI-Dependency** für geschützte Endpoints |
| `require_role(min_role)` | str | str (Username) | **FastAPI-Dependency** für rollenbasierte Endpoints |
| `login(username, password)` | str, str | Dict (Token, User, Role) | Authentifiziert User, gibt JWT zurück |

**Schnittstellen:**
- **Eingehend:** HTTP Authorization-Header (Bearer Token)
- **Ausgehend:** Keine (reine Validierung)
- **Exceptions:** `AuthError`, `InvalidTokenError`, `TokenExpiredError`, `InsufficientPermissionsError`

**Sicherheit:**
- Passwort-Hashing mit bcrypt
- JWT mit HS256 und 24h TTL
- JWT_SECRET muss mindestens 32 Zeichen haben
- `require_role("admin")` schützt Admin-Endpoints

**Verwendung in Routern:**
```python
from ..services.micro.auth_service import require_auth, require_role

@router.get("/api/admin-only")
async def admin_endpoint(_user: str = Depends(require_role("admin"))):
    ...

@router.get("/api/any-authenticated")
async def any_endpoint(_user: str = Depends(require_auth)):
    ...
```

---

### 3.2 Task Service

**Datei:** `backend/app/services/task_service.py` (bestehend, refactored)

**Verantwortung:** CRUD-Operationen für Tasks, Status-Wechsel, History-Management.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `list_tasks(db, project_id, status, limit, offset)` | Session, str, str, int, int | List[Task] | Listet Tasks mit Filter-Optionen |
| `get_task(db, task_id)` | Session, str | Task \| None | Holt einen Task per ID |
| `create_task(db, ...)` | Session, TaskCreate-Data | Task | Erstellt neuen Task |
| `update_task(db, task_id, data)` | Session, str, dict | Task | Aktualisiert Task-Felder |
| `delete_task(db, task_id)` | Session, str | bool | Löscht Task (Cascade) |
| `set_task_status(db, task_id, new_status, agent, reason)` | Session, str, str, str, str | Task | Status-Wechsel mit SOP-Integration |
| `add_history(db, task, event, agent, details)` | Session, Task, str, str, dict | TaskHistory | Fügt History-Eintrag hinzu |

**Schnittstellen:**
- **Eingehend:** Router-Calls (tasks.py)
- **Ausgehend:** SOP Engine Service (bei Status-Wechsel), Event Service (bei Änderungen)
- **Exceptions:** `TaskNotFoundError`, `ValidationError`

**Wichtige Änderung (v2.0-rc):**
- `list_tasks` verwendet jetzt `TaskRead` Pydantic-Schema statt manuellem Dict
- `set_task_status` wurde in 3 Sub-Funktionen aufgeteilt:
  1. `_change_status_only()` – reine Status-Änderung  
  2. `_handle_sop_restart()` – SOP-Instanz-Neustart  
  3. `_handle_subagent_spawn()` – SubAgent-Spawning  

---

### 3.3 Project Service

**Datei:** `backend/app/services/project_service.py` (bestehend, refactored)

**Verantwortung:** Projekt-CRUD, Brainstorming, Requirements-Management.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `list_projects(db)` | Session | List[Project] | Alle Projekte |
| `get_project(db, id)` | Session, str | Project \| None | Projekt per ID |
| `create_project(db, name, description)` | Session, str, str | Project | Neues Projekt |
| `set_project_mode(db, id, mode)` | Session, str, str | Project | Mode setzen (live/manual) |
| `add_brainstorm_entry(db, project_id, role, text)` | Session, str, str, str | BrainstormEntry | Brainstorm-Eintrag |
| `generate_requirements(db, project_id)` | Session, str | List[Requirement] | KI-generierte Requirements |
| `get_completion_report(db, project_id)` | Session, str | dict | Abschlussbericht |

**Schnittstellen:**
- **Eingehend:** Router-Calls (projects.py)
- **Ausgehend:** LLM Service (für Requirement-Generierung), SOP Engine (für Workflow)
- **Exceptions:** `ProjectNotFoundError`

---

### 3.4 SOP Engine Service

**Datei:** `backend/app/services/sop_engine_service.py` (NEU - aus sop_engine.py extrahiert)

**Verantwortung:** Ausführung von SOP-Instanzen, Rule-Evaluation, Step-Transition.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `run_step(instance)` | SOPInstance | dict (Step-Result) | Führt aktuellen Step einer Instance aus |
| `evaluate_rules(instance, step_result)` | SOPInstance, dict | list[RuleResult] | Wertet Wenn-Dann-Regeln aus |
| `advance(instance, next_step_id)` | SOPInstance, str | bool | Geht zum nächsten Step |
| `start_instance(sop_id, task_id, ...)` | str, str, ... | SOPInstance | Startet neue SOP-Instance |
| `fail_instance(instance_id, reason)` | str, str | bool | Markiert Instance als failed |

**Action-Dispatch (Strategy-Pattern):**
```python
_actions = {
    "noop": NoopAction(),
    "set_status": SetStatusAction(),
    "ask_user": AskUserAction(),
    "llm_call": LlmCallAction(),
    "spawn_sop": SpawnSopAction(),
    "review_task": ReviewTaskAction(),
    "assign_worker": AssignWorkerAction(),
    "implement": ImplementAction(),
    "test": TestAction(),
    "cio_final_review": CioFinalReviewAction(),
    "tester_code_review": TesterCodeReviewAction(),
}
```

**Schnittstellen:**
- **Eingehend:** Router-Calls (sops.py → engine_control.py), Scheduler (Auto-Triage)
- **Ausgehend:** Event Service (StepCompleted-Event), Task Service (Status-Änderung per Event)
- **Exceptions:** `SopNotFoundError`, `InstanceNotFoundError`

**Wichtige Änderung (v2.0-rc):**
- `sop_engine.py` (1.865 Zeilen) aufgeteilt in:
  - `sop_engine_service.py` (Dispatcher + Lifecycle)
  - `micro/actions/*.py` (jede Action eigene Datei)
  - `micro/rules.py` (Rule-Evaluation)

---

### 3.5 SOP CRUD Service

**Datei:** `backend/app/services/sop_crud_service.py` (NEU - aus sops.py Router extrahiert)

**Verantwortung:** CRUD-Operationen für SOP-Definitionen, Steps, BPMN/UML-Generierung.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `list_sops(db, category)` | Session, str | List[SOP] | Alle SOPs (optional gefiltert) |
| `get_sop(db, sop_id)` | Session, str | SOP \| None | SOP mit Steps und Rules |
| `create_sop(db, data)` | Session, SOPCreate | SOP | Neue SOP anlegen |
| `update_sop(db, sop_id, data)` | Session, str, SOPUpdate | SOP | SOP-Metadaten aktualisieren |
| `delete_sop(db, sop_id)` | Session, str | bool | SOP löschen (CASCADE) |
| `add_step(db, sop_id, step_data)` | Session, str, SOPStepCreate | SOPStep | Step zu SOP hinzufügen |
| `update_step(db, step_id, data)` | Session, str, SOPStepUpdate | SOPStep | Step aktualisieren |
| `generate_bpmn(db, sop_id)` | Session, str | str (XML) | BPMN 2.0 XML generieren |
| `generate_uml(db, sop_id)` | Session, str | str (PlantUML) | UML-Sequenzdiagramm generieren |
| `seed_default_sops(db)` | Session | int | Default-SOPs anlegen |
| `seed_sops_by_project(db, project_id)` | Session, str | int | Projekt-spezifische SOPs |

**Schnittstellen:**
- **Eingehend:** Router-Calls (sops.py)
- **Ausgehend:** SOP Engine Service (für Ausführung)
- **Exceptions:** `SopNotFoundError`, `ValidationError`

---

### 3.6 Agent Question Service

**Datei:** `backend/app/services/agent_question_service.py` (NEU)

**Verantwortung:** User↔Agent Interaktionstool, Eskalations-Workflow.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `list_questions(db, status, ...)` | Session, str, ... | List[AgentQuestion] | Fragen mit Filter |
| `create_question(db, agent_id, title, ...)` | Session, str, str, ... | AgentQuestion | Neue Frage erstellen |
| `answer_question(db, question_id, answer)` | Session, str, str | AgentQuestion | Frage beantworten |
| `auto_answer_question(db, question)` | Session, AgentQuestion | (bool, str) | KI-Auto-Answer (CIO→CEO→User) |
| `cancel_question(db, question_id)` | Session, str | bool | Frage abbrechen |
| `get_pending_count(db)` | Session | dict | Anzahl offener Fragen |

**Eskalations-Workflow:**
```
Frage erstellt → CIO versucht Antwort (Confidence ≥ 0.7)
    ↓ wenn CIO scheitert
CEO-digital versucht Antwort (Confidence ≥ 0.7)
    ↓ wenn beide scheitern
User wird benachrichtigt (Rückfrage im Dashboard)
```

---

### 3.7 Pricing Service

**Datei:** `backend/app/services/pricing_service.py` (bestehend, refactored)

**Verantwortung:** Provider-Preise, Task-Price-Snapshots, Kosten-Tracking.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `take_pricing_snapshot(task, db)` | Task, Session | dict | Preis-Snapshot bei Task-Start |
| `calc_cost_from_snapshot(task)` | Task | Decimal | Kosten aus Snapshot berechnen |
| `get_current_pricing(db, provider, model)` | Session, str, str | dict | Aktuellen Preis aus DB/JSON |
| `refresh_pricing(db)` | Session | int | Preise aus Providern aktualisieren |
| `KNOWN_PRICING` | - | Dict | Statische Preisdatenbank (Fallback) |

---

### 3.8 LLM Service

**Datei:** `backend/app/services/llm_service.py` (bestehend, refactored)

**Verantwortung:** LLM-API-Aufrufe für MiniMax, Kimi, Ollama und OpenAI-kompatible Provider.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `chat_completion(messages, model, ...)` | List[Dict], str, ... | Dict | Haupt-Einstiegspunkt |
| `_chat_ollama(messages, model, ...)` | List[Dict], str, ... | Dict | Ollama (lokal, kostenlos) |
| `_chat_openai_compatible(messages, model, ...)` | List[Dict], str, ... | Dict | MiniMax/Kimi/OpenRouter |
| `build_sop_step_prompt(step, user_input)` | dict, str | Tuple | Prompt-Bau für SOP-Steps |

**Key-Änderung (v2.0-rc):**
- API-Key wird NUR noch aus `.env` geladen (nicht mehr aus `models.json`)
- Fallback auf `DEFAULT_API_KEY` entfernt → Fehler wenn Key fehlt
- Provider-Resolution: `ollama/<model>` → Ollama, alles andere → OpenAI-kompatibel

---

### 3.9 Sub-Agent Service

**Datei:** `backend/app/services/micro/sub_agent_service.py`

**Verantwortung:** Sicherer Sub-Agent-Spawner, Prozess-Tracking, Audit-Log.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `spawn_sub_agent(task, db, user)` | Task, Session, str | Dict \| None | Sub-Agent starten (RCE-gehärtet) |
| `kill_sub_agent(task_id)` | str | bool | Sub-Agent beenden |
| `get_agent_for_task(task_id)` | str | Dict \| None | Agent-Status abfragen |
| `list_active_agents()` | - | List[Dict] | Alle aktiven Agenten |
| `cleanup_dead_agents()` | - | int | Registry aufräumen |
| `validate_spawn_inputs(task_id, title, desc, role)` | str, str, str, str | Tuple[bool, str] | Input-Validierung |

**Sicherheitsmaßnahmen:**
1. Whitelist für Rollen (`ALLOWED_ROLES`)
2. Regex-Validierung aller User-Inputs (Positiv-Liste statt Negativ-Liste)
3. Längenbegrenzung (500 Zeichen Titel, 50.000 Description)
4. `subprocess.Popen` mit `shell=False` und separaten Argumenten
5. Kein hartcodierter Pfad mehr → `SPAWN_SH_PATH` aus `.env`
6. Budget-Guard: max. 3 Sub-Agents pro Task
7. Timeout: 30 Minuten → automatischer Kill
8. Audit-Log für jeden Spawning-Vorgang

---

### 3.10 Board Operator Service

**Datei:** `backend/app/services/board_operator_service.py` (bestehend, refactored)

**Verantwortung:** Watchdog für Live-Boards, Heartbeat-Monitoring, Task-Überwachung.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `start_operator(board_id)` | str | BoardOperator | Operator-Task starten |
| `stop_operator(board_id, reason)` | str, str | BoardOperator | Operator stoppen |
| `start_watchdog()` | - | None | Globalen Watchdog starten |
| `stop_watchdog()` | - | None | Watchdog stoppen |
| `_operator_loop(board_id, op_id)` | str, str | None | Operator-Hauptschleife |

---

### 3.11 Worker Service

**Datei:** `backend/app/services/worker_service.py` (bestehend, refactored)

**Verantwortung:** Autonome Task-Bearbeitung via LLM, Budget-Guard, Cleanup.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `claim_next_task(project_id)` | str | Task \| None | Nächsten Todo-Task claimen |
| `execute_task(task)` | Task | dict | Task via LLM ausführen |
| `run_agent_cleanup()` | - | dict | Abgestürzte Agenten bereinigen |
| `run_file_watcher()` | - | dict | Gelöschte Dateien aus Git wiederherstellen |

**Key-Änderung (v2.0-rc):**
- Verwendet jetzt `select()` statt `db.query()` (konsistenter SQLAlchemy-Stil)
- `CODE_AGENT_API_TOKEN` ohne Default (Fehler wenn nicht gesetzt)
- Neue Session-ID pro Worker-Iteration

---

### 3.12 Event Service

**Datei:** `backend/app/services/micro/event_service.py` (NEU - ersetzt events.py)

**Verantwortung:** Event-Bus für SSE (Server-Sent Events), Inter-Service-Kommunikation.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `publish_event(project_id, event_type, data)` | str, str, dict | None | Event veröffentlichen |
| `subscribe(project_id, last_event_id)` | str, int | EventStream | Long-Polling-Stream |
| `get_events_since(project_id, since_id, limit)` | str, int, int | List[Dict] | Events ab ID |
| `ensure_table()` | - | None | Tabelle anlegen (nur Dev!) |

**Key-Änderung (v2.0-rc):**
- `ensure_table()` verwendet `create_all()` nur in `ENV=development`
- In Production wird die Tabelle via Alembic-Migration erstellt
- SQLAlchemy 2.0 Style (`Mapped` statt `Column`)

---

### 3.13 Analytics Service

**Datei:** `backend/app/services/analytics_service.py` (NEU)

**Verantwortung:** Performance-Reports, Kosten-Analyse, Dashboard-Statistiken.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `get_summary(db)` | Session | dict | Globale Statistiken |
| `get_cost_summary(db, days)` | Session, int | dict | Kosten nach Modell/Provider/Rolle/Tag |
| `get_index_usage(db)` | Session | dict | DB-Index-Auslastung |
| `run_analyze(db)` | Session | dict | SQLite ANALYZE ausführen |
| `get_performance_stats(db, project_id)` | Session, str | dict | Performance-Kennzahlen |

---

### 3.14 Credential Service

**Datei:** `backend/app/services/micro/credential_service.py`

**Verantwortung:** Verschlüsselte Verwaltung von Provider-API-Keys.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `encrypt_key(plaintext, context)` | str, str | str | AES-256-GCM Verschlüsselung |
| `decrypt_key(encrypted, context)` | str, str | str | AES-256-GCM Entschlüsselung |
| `verify_encryption_key()` | - | bool | Prüft ob ENCRYPTION_KEY gültig |
| `migrate_credential_to_encrypted(db, id, key)` | Session, str, str | bool | Einzelnen Key migrieren |
| `migrate_all_credentials(db)` | Session | Tuple[int, int] | Alle Keys migrieren |

**Sicherheit:**
- AES-256-GCM (authenticated encryption)
- 12 Byte zufälliger Nonce pro Key
- Auth-Tag (16 Byte) verhindert Manipulation
- ENCRYPTION_KEY muss 32 Byte lang sein (base64-kodiert)

---

### 3.15 TTS Service

**Datei:** `backend/app/services/tts_service.py` (bestehend, unverändert)

**Verantwortung:** Text-to-Speech via MiniMax API.

**Funktionen:**

| Funktion | Parameter | Rückgabe | Beschreibung |
|----------|-----------|----------|--------------|
| `speak(text, voice_id, ...)` | str, str, ... | Dict | Text in Audio umwandeln |
| `get_available_voices()` | - | List[Dict] | Verfügbare Stimmen |
| `text_to_audio_file(text, output_path)` | str, str | str | Audio-Datei erstellen |

---

## 4. Kommunikation zwischen Services

### 4.1 Synchron (REST/Direct Calls)

```
Router → Service (direct)
  tasks.py → TaskService.create_task()
  sops.py → SopCrudService.create_sop()

Service → Service (direct, bei enger Kopplung)
  TaskService → SOPEngineService (bei Status-Wechsel)
```

### 4.2 Asynchron (Events)

```
Service → EventService.publish_event() → andere Services subscribed

Events:
  task_created        → SOP Engine (Auto-Triage starten)
  task_status_changed → Analytics (Performance-Tabelle)
  sub_agent_spawned   → Board Operator (Agent-Status aktualisieren)
  sop_step_completed  → Task Service (Status-Wechsel)
```

### 4.3 Vermieden: Zirkuläre Abhängigkeiten

```
❌ Früher: TaskService ↔ SOPEngine (circular import!)
✅ Jetzt:  TaskService → EventService → SOPEngine (entkoppelt)
```

---

## 5. Fehlerbehandlung

Jeder Service wirft definierte Exceptions aus `utils/exceptions.py`:

```python
# Service wirft Exception
raise TaskNotFoundError(task_id="123")

# Globaler Handler in main.py fängt ab
@app.exception_handler(DashboardError)
async def dashboard_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )
```

---

## 6. Sicherheits-Prinzipien

| Prinzip | Umsetzung |
|---------|-----------|
| **Auth First** | Jeder Endpoint braucht gültigen JWT (außer /health) |
| **Rolle prüfen** | `require_role("admin")` für sensitive Endpoints |
| **Keys verschlüsselt** | AES-256-GCM für API-Keys in der DB |
| **Input validieren** | Pydantic-Schemas + Regex + Längenprüfung |
| **Keine Shell** | `subprocess.Popen` mit `shell=False` |
| **Whitelist statt Blacklist** | Nur erlaubte Rollen/Actions |
| **Budget-Guard** | Kosten-Limit pro Task/Instance |
| **Audit-Log** | Jeder kritische Vorgang protokolliert |

---

## 7. Migrations-Pfad (alt → neu)

| Alte Datei | Neue Struktur | Status |
|------------|---------------|--------|
| `auth.py` | `services/micro/auth_service.py` | ✅ Fertig |
| `services/sub_agent.py` | `services/micro/sub_agent_service.py` | ✅ Fertig |
| `services/sop_engine.py` | `services/micro/sop_engine_service.py` + `actions/` | 🔄 Geplant |
| `routers/sops.py` | `routers/sops/` (6 Sub-Module) | 🔄 Geplant |
| `routers/tasks.py` | `routers/tasks/` (4 Sub-Module) | 🔄 Geplant |
| `services/task_service.py` | `services/micro/task_service.py` | 🔄 Geplant |
| `services/worker_service.py` | `services/micro/worker_service.py` | 🔄 Geplant |
| `events.py` | `services/micro/event_service.py` | 🔄 Geplant |
| `services/pricing_service.py` | `services/micro/pricing_service.py` | 🔄 Geplant |
| `services/agent_question_helpers.py` | `services/micro/agent_question_service.py` | 🔄 Geplant |
| `frontend/pages/Sops.tsx` | `frontend/pages/sops/` (6 Sub-Module) | 🔄 Geplant |
| `frontend/pages/Kanban.tsx` | `frontend/pages/kanban/` (6 Sub-Module) | 🔄 Geplant |

---

## 8. Fehlersuche (für andere Agenten)

### Typische Fehler und ihre Ursachen

| Fehlerbild | Wahrscheinliche Ursache | Service |
|------------|------------------------|---------|
| 401 Unauthorized | JWT_SECRET nicht gesetzt oder falsch | Auth Service |
| 403 Forbidden | User hat nicht die richtige Rolle | Auth Service |
| Task bleibt in Triage | SOP Engine läuft nicht richtig | SOP Engine Service |
| Sub-Agent startet nicht | SPAWN_SH_PATH fehlt oder falsch | Sub-Agent Service |
| LLM-Call schlägt fehl | API-Key fehlt oder falsch | LLM Service / Credential Service |
| Kosten werden nicht getrackt | Pricing-Snapshot fehlt | Pricing Service |
| SSE-Events kommen nicht | EventLog-Tabelle fehlt | Event Service |
| Frontend zeigt weiße Seite | Kein Error-Boundary, Runtime-Fehler | Frontend (ErrorBoundary fehlt) |
| Port 9220 blockiert | Graceful-Shutdown fehlgeschlagen | Backend (main.py) |
| CORS-Fehler im Browser | CORS_ORIGINS falsch geparst | Config (config.py) |
