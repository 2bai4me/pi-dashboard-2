# PI-Dashboard 2.0 — Qualitäts- und Sicherheitsverbesserungen

> **Erstellt:** 20.06.2026  
> **Basis:** Vollständige Code-Analyse (20.608 Zeilen Python, 30+ Frontend-Pages, 16 DB-Migrationen)  
> **Status:** ⬜ Nicht begonnen | 🔄 In Arbeit | ✅ Abgeschlossen

---

## 📋 Gesamt-Checkliste

| # | Finding | Kategorie | Aufwand | Status |
|---|---------|-----------|---------|--------|
| 🔴 1 | Auth implementieren | Sicherheit | 2-4h | ⬜ |
| 🔴 2 | API-Keys aus .env entfernen | Sicherheit | 30min | ⬜ |
| 🔴 3 | Test-Suite aufbauen | Stabilität | 2-3 Tage | ⬜ |
| 🟠 4 | Monolithische Riesen-Files zerlegen | Wartbarkeit | 1-2 Tage | ⬜ |
| 🟠 5 | 107× bare except Exception eliminieren | Fehlerkultur | 4-8h | ⬜ |
| 🟠 6 | Einheitliches API-Exception-Handling | API-Qualität | 4h | ⬜ |
| 🟡 7 | SOP-Engine entflechten | Wartbarkeit | 2-3 Tage | ⬜ |
| 🟡 8 | CORS-Parsing-Fehler beheben | Funktionalität | 15min | ⬜ |
| 🟡 9 | Status-Labels + Duplikat bereinigen | Code-Qualität | 5min | ⬜ |
| 🟡 10 | Requirements bereinigen | Zukunftssicherheit | 30min | ⬜ |

---

# 🔴 Finding 1: Auth — API-Schutz

## Anforderung

Die gesamte API muss durch **JWT-Authentifizierung** geschützt werden. Ohne gültigen Token gibt es keinen Zugriff auf Endpunkte.

## Was genau gemacht werden muss

### 1. `config.py` anpassen

- `AUTH_ENABLED` Default auf `True` setzen (für Production)
- `JWT_SECRET` aus `.env` zwingend erforderlich machen → `Field(..., validation_alias="JWT_SECRET")`
- Wenn `JWT_SECRET` nicht gesetzt ist → App startet nicht (Exception beim Start)

### 2. `auth.py` neu schreiben

- Echte JWT-Validierung statt Stub
- Token-Erzeugung (`create_token()`) und -Validierung (`verify_token()`) implementieren
- Token-Payload: `sub` (Username), `role` (z.B. "admin"), `iat` (Issued-At), `exp` (Expiry)
- `require_auth` extrahiert `sub` aus dem Token und gibt User-Identität zurück

### 3. Login-Endpoint hinzufügen

- `POST /api/auth/login` → akzeptiert Username/Password → gibt JWT zurück
- `ADMIN_USER` und `ADMIN_PASSWORD` validieren (nicht mehr "admin"/"admin" als Default)

### 4. Health-Endpoints ausnehmen

- `GET /api/health` und `GET /api/version` bleiben ohne Auth (für Liveness-Probes)

## Ergebnis

- Kein API-Zugriff ohne gültigen JWT-Token
- Admin-Zugang via `POST /api/auth/login`
- JWT hat 24h TTL (konfigurierbar)
- `health`-Endpoints bleiben öffentlich

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ Kein Token → 401 | `curl http://localhost:9220/api/kanban/tasks` → `401 Unauthorized` |
| ✅ Ungültiger Token → 401 | `curl -H "Authorization: Bearer invalid" ...` → `401 Unauthorized` |
| ✅ Gültiger Token → 200 | Login vorher ausführen → Token holen → damit Request → `200 OK` |
| ✅ Health ohne Token | `curl http://localhost:9220/api/health` → `200 OK` (ohne Header) |
| ✅ Falsches Passwort → 401 | `POST /api/auth/login` mit falschem PW → `401 Unauthorized` |
| ✅ Abgelaufener Token → 401 | Token mit `exp` in der Vergangenheit → `401` |

## Betroffene Dateien

- `backend/app/auth.py` → Komplett-Neuschreibung
- `backend/app/config.py` → Defaults ändern, Validierung
- `backend/app/main.py` → Login-Router einbinden
- `backend/.env` → JWT_SECRET setzen

---

# 🔴 Finding 2: API-Keys aus .env entfernen

## Anforderung

Keine API-Keys mehr im Projekt-Quellcode. Keys werden ausschließlich via System-Umgebungsvariablen bezogen.

## Was genau gemacht werden muss

### 1. `.env` bereinigen

- `MINIMAX_API_KEY=` → Wert entfernen (nur `MINIMAX_API_KEY=` ohne Wert)
- `KIMI_API_KEY=` → Wert entfernen (nur `KIMI_API_KEY=` ohne Wert)

### 2. `config.py` anpassen

- `MINIMAX_API_KEY: str = ""` bleibt, aber ohne Default-Wert aus dem Code
- `KIMI_API_KEY: str = ""` analog

### 3. `llm_service.py` anpassen

- `_load_api_credentials()` soll KEINEN Fallback auf `DEFAULT_API_KEY` haben
- Wenn weder ENV noch `models.json` einen Key liefert → klarer Fehler: `RuntimeError("MINIMAX_API_KEY nicht gesetzt")`

### 4. `tts_service.py` anpassen

- Key-Prüfung analog zu `llm_service.py`

### 5. Dokumentation

- `README.md` oder `.env.example` zeigt: `MINIMAX_API_KEY=<dein-key>` (Platzhalter)
- Setup-Script erwähnen, dass Keys per System-ENV gesetzt werden müssen

## Ergebnis

- `.env` enthält keine Secrets mehr
- Bei leerem `.env` → App startet mit Hinweis: "Bitte MINIMAX_API_KEY setzen"
- Keys sind nur in der Windows-Umgebungsvariable (`$env:MINIMAX_API_KEY`)
- Bei Sicherheitsvorfall: Keys rotieren reicht, kein Code-Change nötig

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ `.env` ohne Key-Werte | `grep "=" backend/.env` → keine Base64-Zeichenketten nach dem `=` |
| ✅ LLM startet ohne ENV | `$env:MINIMAX_API_KEY=""` → App sagt "Fehler: Key fehlt" |
| ✅ LLM funktioniert mit ENV | `$env:MINIMAX_API_KEY="sk-..."` → App startet und LLM-Calls funktionieren |
| ✅ TTS analog getestet | Gleiches Prinzip wie LLM |
| ✅ `.env.example` hat Platzhalter | `MINIMAX_API_KEY=<dein-key>` in `.env.example` |
| ✅ Kein Fallback mehr | `models.json` wird nicht mehr als Key-Quelle verwendet (nur für Modell-Liste) |

## Betroffene Dateien

- `backend/.env` → Keys entfernen
- `backend/app/config.py` → Defaults prüfen
- `backend/app/services/llm_service.py` → Key-Fallback entfernen
- `backend/app/services/tts_service.py` → Key-Prüfung anpassen
- `backend/.env.example` → Platzhalter setzen

---

# 🔴 Finding 3: Test-Suite aufbauen

## Anforderung

Eine Test-Suite mit pytest + pytest-asyncio, die die Kern-Logik absichert und bei Refactoring Regression verhindert.

## Was genau gemacht werden muss

### 1. Test-Infrastruktur

- `backend/tests/` Verzeichnis anlegen
- `conftest.py` mit:
  - Test-Datenbank (separate SQLite-Datei `:memory:`)
  - Test-Session-Factory
  - Fixtures für Test-Tasks, Test-Projekte, Test-Rollen
- `pytest.ini` mit `asyncio_mode = auto`

### 2. Tests für Kernlogik (Priorität 1)

- `tests/test_task_service.py`:
  - `test_create_task_with_defaults` → Standard-Success-Criteria?
  - `test_create_task_with_user_criteria` → User-Kriterien + Standard-Kriterien?
  - `test_list_tasks_filter_by_status` → Filter funktioniert?
  - `test_list_tasks_filter_by_project` → Filter funktioniert?
- `tests/test_pricing_service.py`:
  - `test_take_snapshot` → Preis-Snapshot wird erstellt?
  - `test_calc_cost` → Kostenberechnung korrekt?

### 3. Tests für SOP-Engine (Priorität 2)

- `tests/test_sop_engine.py`:
  - `test_run_step_approve_triage` → Triaging funktioniert?
  - `test_run_step_question` → Rückfrage wird erzeugt?
  - `test_rule_evaluation_approve` → Rule "is_approved" matched?

### 4. API-Tests (Priorität 3)

- `tests/test_api_tasks.py`:
  - Mit TestClient (FastAPI TestClient)
  - CRUD für Tasks testen
  - Status-Wechsel testen
- Auth ist deaktiviert (für Test-Zwecke)

## Ergebnis

- pytest läuft ohne Fehler
- `pytest --cov` zeigt Coverage > 70% für Kernlogik
- Neue Features können mit Tests abgesichert werden
- CI/CD kann aufgesetzt werden (GitHub Actions)

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ Tests existieren | `ls backend/tests/` → mindestens 3 Test-Dateien |
| ✅ Tests laufen | `cd backend && pytest` → `100% passed` |
| ✅ Task-Service getestet | `test_task_service.py` hat 5+ Tests |
| ✅ SOP-Engine getestet | `test_sop_engine.py` hat 3+ Tests (wichtigster Bereich) |
| ✅ API-Tests | `test_api_tasks.py` mit FastAPI TestClient |
| ✅ Keine Production-DB in Tests | `conftest.py` verwendet `sqlite:///:memory:` |

## Betroffene Dateien

- `backend/tests/conftest.py` → Neu (Test-Infrastruktur)
- `backend/tests/test_task_service.py` → Neu (ca. 5 Tests)
- `backend/tests/test_sop_engine.py` → Neu (ca. 3 Tests)
- `backend/tests/test_api_tasks.py` → Neu (ca. 5 Tests)
- `backend/tests/test_pricing_service.py` → Neu (ca. 2 Tests)
- `backend/pytest.ini` → Neu

---

# 🟠 Finding 4: Monolithische Riesen-Files zerlegen

## Anforderung

Die 5 größten Dateien (6.485 Zeilen gesamt) werden in kleinere, fokussierte Module aufgeteilt.

### Betroffene Dateien (Ist-Zustand)

| Datei | Zeilen | Verantwortung |
|-------|--------|---------------|
| `sop_engine.py` | **1.865** | SOP-Ausführungs-Engine |
| `sops.py` (Router) | **1.478** | CRUD + BPMN + UML + Engine-Steuerung |
| `worker_service.py` | **1.274** | Task-Ausführung + File-Watcher + Budget |
| `task_service.py` | **934** | Task-CRUD + History + Pricing |
| `tasks.py` (Router) | **934** | Task-API + Status-Wechsel + SubAgents |
| **Summe** | **6.485** | 31% des gesamten Backends |

## Was genau gemacht werden muss

### 1. `sops.py` (1.478 Zeilen) → `/routers/sops/` Ordner

- `sops/__init__.py` → Router-Zusammenführung + Prefix/Tags
- `sops/crud.py` → CRUD-Endpoints (GET/POST/PUT/DELETE)
- `sops/bpmn.py` → BPMN-Export-Endpoint
- `sops/uml.py` → UML-Visualisierung
- `sops/engine_control.py` → Start/Run/Fail Instance
- `sops/steps.py` → Step-Updates/Tool-Config (das `update_step` mit den 20+ if-Blöcken)

### 2. `task_service.py` (934 Zeilen) → `/services/tasks/` Ordner

- `tasks/crud_service.py` → create/list/get/update/delete
- `tasks/history_service.py` → History-Einträge
- `tasks/pricing_service.py` → Pricing-Schnappschüsse
- `tasks/transition_service.py` → Status-Wechsel mit SOP

### 3. `tasks.py` (934 Zeilen) → `/routers/tasks/` Ordner

- Gleiche Struktur wie sops/ → CRUD, History, SubTasks, StatusWechsel
- **Kritisch:** `set_task_status` wird in 3 Funktionen aufgeteilt:
  1. `_validate_and_change_status()` → reine Status-Änderung
  2. `_handle_sop_restart()` → SOP-Instanz-Neustart (in SOP-Service auslagern)
  3. `_handle_subagent_spawn()` → SubAgent-Spawning (in SubAgent-Service)

### 4. Keine direkten Imports zwischen den neuen Modulen

- Sub-Module importieren nur Services, nicht andere Sub-Module
- `sops/steps.py` ruft `SOPEngine.update_step()` auf, hat keine Ahnung von BPMN

## Ergebnis

- Keine Datei im Projekt > 400 Zeilen
- Jedes Modul hat genau eine fachliche Verantwortung
- `set_task_status` ist in 3 fachliche Funktionen getrennt
- Neue Endpunkte können einfach hinzugefügt werden

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ sops.py existiert nicht mehr | `ls backend/app/routers/sops/` → 6 Dateien |
| ✅ Keine Datei > 400 Zeilen | `wc -l backend/app/**/*.py` → max 400 |
| ✅ set_task_status zerlegt | 3 Services statt 1 Monolith |
| ✅ Alle Tests laufen noch | `pytest` → grün (Regression!) |
| ✅ Importe sauber | `python -c "from app.routers.sops import ..."` → kein Fehler |

---

# 🟠 Finding 5: 107× bare except Exception eliminieren

## Anforderung

Jede bare `except Exception` wird analysiert und durch einen präzisen Ausnahme-Typ oder eine strukturierte Fehlerbehandlung ersetzt.

## Was genau gemacht werden muss

### 1. Kategorisierung der 107 Fundstellen

- **Critical (ca. 15):** Scheduler-Jobs, Worker-Loop → Fehler WERFEN statt loggen
- **Important (ca. 40):** Router-Endpunkte → HTTPException mit passendem Status
- **Cosmetic (ca. 52):** Hilfsfunktionen → Spezifische Exception-Typen

### 2. Critical-Fixes (scheduler.py)

```python
# VORHER:
try:
    await start_watchdog()
except Exception as e:
    logger.warning(f"Watchdog konnte nicht starten: {e}")

# NACHHER:
try:
    await start_watchdog()
except OSError as e:
    logger.error(f"Watchdog-Port belegt: {e}")
    raise  # ← WIRD GEWORFEN, App startet nicht ohne Watchdog
```

### 3. Important-Fixes (Router)

```python
# VORHER:
try:
    result = service.do_something()
except Exception as e:
    return {"error": str(e)}

# NACHHER:
try:
    result = service.do_something()
except ValueError as e:
    raise HTTPException(400, detail=str(e))
except DatabaseError as e:
    raise HTTPException(503, detail="Database unavailable")
```

### 4. Logger-Struktur verbessern

- `logger.warning()` → nur für erwartete, behebbare Situationen
- `logger.error()` → für unerwartete Fehler (Fehlerklasse + Stacktrace)
- `logger.critical()` → für Fehler die zum App-Abbruch führen

## Ergebnis

- Kein `except Exception` mehr ohne konkreten Type
- Scheduler-Jobs werden bei Fehlern sichtbar (werfen oder loggen kritisch)
- API-Endpoints geben konsistente HTTP-Fehler zurück
- Error-Logs enthalten immer Stacktrace (`exc_info=True`)

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ Kein bare except Exception | `grep -r "except Exception" backend/` → 0 Treffer |
| ✅ Critical-Fehler werden geworfen | Watchdog-Fehler → App startet nicht |
| ✅ API-Fehler sind HTTPExceptions | Fehler im Router → Client bekommt HTTP-Status |
| ✅ Logger hat exc_info | Logs zeigen Stacktraces bei `logger.error()` |

---

# 🟠 Finding 6: Einheitliches API-Exception-Handling

## Anforderung

Alle API-Endpoints verwenden ein **einheitliches Error-Response-Schema** und FastAPI's Exception-Handler.

## Was genau gemacht werden muss

### 1. Error-Schema definieren

```python
# schemas/error.py
class ErrorResponse(BaseModel):
    error: str          # Kurzer Fehlertitel (z.B. "task_not_found")
    detail: str         # Menschliche Beschreibung
    status_code: int    # HTTP-Status-Code
    timestamp: str      # ISO-Datum
```

### 2. Globalen Exception-Handler in `main.py`

```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error="http_error",
                detail=exc.detail,
                status_code=exc.status_code,
                timestamp=datetime.utcnow().isoformat()
            ).model_dump()
        )
    # Unerwartete Fehler → 500
    logger.error(f"Unerwarteter Fehler: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            detail="Ein unerwarteter Fehler ist aufgetreten",
            status_code=500,
            timestamp=datetime.utcnow().isoformat()
        ).model_dump()
    )
```

### 3. Pydantic-Schemas konsequent nutzen

- `tasks.py`: `list_tasks` verwendet `TaskRead` statt manuellem Dict
- `set_task_status`: `TaskStatusUpdate` Response nutzen
- Response-Format ist einheitlich: `{"item": TaskRead, "message": "..."}`

### 4. Validation-Errors (422) anpassen

- FastAPI's default 422-Response auf das `ErrorResponse`-Schema mappen

## Ergebnis

- Jeder API-Response hat konsistentes Format
- Unerwartete Fehler → 500 mit ErrorResponse (nie roher Stacktrace)
- `TaskRead` wird überall statt manuellem Dict verwendet
- Frontend kann einheitlich parsen: `response.error?.detail`

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ Einheitliches Error-Schema | `curl /api/kanban/tasks/INVALID` → `{"error": "task_not_found", "detail": "..."}` |
| ✅ TaskRead konsistent | `list_tasks` liefert `{"items": [TaskRead, ...]}` |
| ✅ Kein roher Stacktrace | `curl /api/...` bei 500 → nie roher Python-Error im Body |
| ✅ Globaler Handler | Jeder Fehler durchläuft `global_exception_handler` |

---

# 🟡 Finding 7: SOP-Engine entflechten

## Anforderung

Die SOP-Engine wird von einem Monolithen in eine modulare Architektur umgebaut: Action-Dispatch per Strategy-Pattern.

## Was genau gemacht werden muss

### 1. Action-Strategien (Strategy-Pattern)

```python
# services/sop/actions/__init__.py
class SOPAction(ABC):
    @abstractmethod
    async def execute(self, instance: SOPInstance, step: SOPStep, db: Session) -> dict: ...

# services/sop/actions/review_task.py
class ReviewTaskAction(SOPAction):
    async def execute(self, instance, step, db) -> dict:
        # Bisherige 300+ Zeilen run_step-Logik hier
        result = _check_cio_heuristic(db, task)
        # ...
        return {"ok": True, "new_status": "todo"}

# services/sop/actions/assign_worker.py
class AssignWorkerAction(SOPAction):
    async def execute(self, instance, step, db) -> dict:
        # SubAgent auswählen, assigned_role setzen
        ...
```

### 2. SOPEngine auf Dispatcher reduzieren

```python
class SOPEngine:
    _actions: dict[str, SOPAction] = {
        "review_task": ReviewTaskAction(),
        "assign_worker": AssignWorkerAction(),
        "implement": ImplementAction(),
        "test": TestAction(),
    }

    async def run_step(self, instance, db) -> dict:
        step = self._get_current_step(instance)
        action = self._actions.get(step.action)
        if not action:
            raise ValueError(f"Unbekannte Action: {step.action}")
        return await action.execute(instance, step, db)
```

### 3. Nebenwirkungen über Events

```python
# services/sop/events.py
@dataclass
class StepCompleted:
    instance_id: str
    task_id: str
    new_status: str
    reason: str

class EventBus:
    _handlers: dict[str, list[Callable]]

    def on(self, event_type: str, handler: Callable):
        ...

    async def emit(self, event: Any):
        ...
```

### 4. Task-Service entkoppeln

- `SOPEngine` ändert nie direkt `task.status`
- Stattdessen: Event `StepCompleted` → TaskService subscribed → ändert Status
- `sop_engine.py` importiert `task_service.py` nicht mehr → keine Circular Imports

## Ergebnis

- Neue Actions können per `class MyAction(SOPAction)` hinzugefügt werden (Open-Closed-Prinzip)
- SOPEngine ist testbar (jede Action einzeln testbar)
- Keine Circular Imports mehr zwischen SOP-Engine und Task-Service
- `run_step()` ist 20 Zeilen Dispatcher + 100-200 Zeilen pro Action statt 300 Zeilen Monolith

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ Action-Klassen existieren | `ls backend/app/services/sop/actions/` → 5+ Dateien |
| ✅ SOPEngine ist 100 Zeilen | `wc -l sop_engine.py` → unter 100 |
| ✅ Jede Action testbar | `pytest tests/test_sop_actions.py` → jede Action hat Test |
| ✅ Kein circular import | `python -c "from app.services.sop import SOPEngine"` → kein ImportError |
| ✅ EventBus existiert | `from app.services.sop.events import EventBus` → funktioniert |

---

# 🟡 Finding 8: CORS-Parsing-Fehler beheben

## Anforderung

`CORS_ORIGINS` wird korrekt als Liste von Strings aus `.env` eingelesen.

## Was genau gemacht werden muss

### 1. `.env` Format anpassen

```
# VORHER (kaputt):
CORS_ORIGINS=["http://localhost:5181","http://127.0.0.1:5181"]

# NACHHER (funktioniert):
CORS_ORIGINS=http://localhost:5181,http://127.0.0.1:5181
```

### 2. `config.py` Validator hinzufügen

```python
@field_validator("CORS_ORIGINS", mode="before")
@classmethod
def parse_cors_origins(cls, v):
    if isinstance(v, str):
        # JSON-String: "[...]" → parsen
        if v.startswith("[") and v.endswith("]"):
            import json
            return json.loads(v)
        # Komma-separiert: "a,b,c"
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, list):
        return v
    return ["http://localhost:5181"]  # Fallback
```

### 3. Testen

- `.env` mit JSON-Format → funktioniert (Rückwärtskompatibel)
- `.env` mit Komma-Format → funktioniert
- Ohne `.env` → Default-Liste funktioniert

## Ergebnis

- `CORS_ORIGINS` ist immer eine Liste von Strings
- Frontend kann Backend erreichen (kein CORS-Error mehr im Browser)
- Rückwärtskompatibel: Alte `.env`-Konfiguration funktioniert noch

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ CORS als Liste | `python -c "from app.config import settings; print(type(settings.CORS_ORIGINS))"` → `<class 'list'>` |
| ✅ Frontend erreichbar | Browser-Console zeigt keinen CORS-Error |
| ✅ Rückwärtskompatibel | Alte `.env` mit JSON-Array → funktioniert trotzdem |

---

# 🟡 Finding 9: Status-Labels Production-Code säubern

## Anforderung

`status_labels.py` wird bereinigt: Test-Code entfernt, Production-Code sauber.

## Was genau gemacht werden muss

### 1. `_run_tests()` unter `if __name__` setzen

```python
# status_labels.py — Ende der Datei
if __name__ == "__main__":
    _run_tests()
```

### 2. `print()` durch `logger.info()` ersetzen

- Wenn `_run_tests()` erhalten bleiben soll: `logger.info()` statt `print()`

### 3. Duplikat bereinigen

- `frontend/src/pages/Selfimprovment.tsx` → löschen (Tippfehler-Version)
- `frontend/src/pages/SelfImprovement.tsx` → behalten (korrekte Version)
- In `App.tsx`: Import auf korrekte Version umbiegen

### 4. Alternative (besser)

- Das gesamte `status_labels.py` kann durch ein reines Mapping-Dict ersetzt werden
- Keine Funktionen, nur `DB_TO_DISPLAY: dict[str, str]` und evtl. `display_status()` → 15 Zeilen statt 183

## Ergebnis

- Server startet ohne Test-Output auf stdout
- `status_labels.py` ist entweder 15 Zeilen (nur Mapping) oder sauber strukturiert
- Frontend hat nur eine Page für SelfImprovement

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ Kein Test-Output bei Start | Server starten → stdout zeigt nur Logs, keine "=== Tests ===" |
| ✅ `__name__` Guard | `python -c "from app.utils.status_labels import display_status"` → kein Output |
| ✅ Nur eine SelfImprov-Page | `ls frontend/src/pages/Self*` → nur `SelfImprovement.tsx` |

---

# 🟡 Finding 10: Requirements bereinigen

## Anforderung

`requirements.txt` ist korrekt, doppelte Einträge entfernt, fehlende Dependencies ergänzt, Versionen gepinnt.

## Was genau gemacht werden muss

### 1. `requirements.txt` bereinigen

```txt
# VORHER:
sse-starlette==2.1.3
sse-starlette==2.1.3  # ← Doppelt!

# NACHHER:
sse-starlette==2.1.3  # ← Einmal
```

### 2. Fehlende Dependencies ergänzen

```txt
# Fehlt aktuell:
slowapi>=0.1.10       # Rate-Limiting (wird importiert, fehlt in requirements.txt)
```

### 3. `requirements.lock` erstellen (optional, empfohlen)

```bash
cd backend
pip freeze > requirements.lock
```

Enthält ALLE installierten Packages mit exakten Versionen (inklusive transitiver Dependencies)

### 4. `package.json` prüfen

- Keine Duplikate
- Version-Pins sind semver-konform (sind bereits gut aufgesetzt bei React/Vite)

## Ergebnis

- `sse-starlette` nur einmal in `requirements.txt`
- `slowapi` ist in `requirements.txt` enthalten
- `requirements.lock` existiert für reproduzierbare Installationen
- Bei `pip install -r requirements.txt` werden Rate-Limiting und SSE korrekt installiert

## Akzeptanzkriterien

| Kriterium | Prüfung |
|-----------|---------|
| ✅ Kein Duplikat | `grep -c "sse-starlette" backend/requirements.txt` → `1` |
| ✅ slowapi vorhanden | `grep "slowapi" backend/requirements.txt` → `slowapi==0.1.10` |
| ✅ requirements.lock | `ls backend/requirements.lock` → existiert |
| ✅ Saubere Installation | `pip install -r requirements.txt` → kein Fehler |

---

## 📋 Empfohlene Reihenfolge

1. ⚡ **Quick Wins (ca. 1h):**
   - Finding 2: API-Keys aus .env entfernen
   - Finding 8: CORS-Parsing-Fehler
   - Finding 9: Status-Labels + Duplikat
   - Finding 10: Requirements bereinigen

2. 🛡️ **Sicherheit (2-4h):**
   - Finding 1: Auth implementieren

3. 🧪 **Stabilität (2-3 Tage):**
   - Finding 3: Test-Suite aufbauen
   - Finding 6: Einheitliches Error-Handling

4. 🏗️ **Architektur (3-5 Tage):**
   - Finding 4: Riesen-Files zerlegen
   - Finding 5: except Exception bereinigen
   - Finding 7: SOP-Engine entflechten

---

> **Nächste Schritte:** Beginne mit den Quick Wins, um schnell erste Verbesserungen sichtbar zu machen.
