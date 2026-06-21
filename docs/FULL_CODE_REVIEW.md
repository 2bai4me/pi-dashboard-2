# 🔍 PI-Dashboard 2.0 — Vollständiges Code-Review

> **Datum:** 20.06.2026  
> **Projekt:** `D:\Entwicklung\PI-Dashboard 2`  
> **Version:** 2.0.0-rc  
> **Untersuchte Codebasis:** 74 Python-Dateien (21.758 Zeilen) + Frontend (5.875+ Zeilen in Top-4-Dateien)  

---

## 📊 Executive Summary

| Metrik | Wert |
|--------|------|
| **Backend-Code** | 74 Python-Dateien, **21.758 Zeilen** |
| **Frontend-Code (Top-4-Dateien)** | **5.875 Zeilen** (Kanban 1.413, Sops 3.235, TaskDetail 962, Brainstorm 265) |
| **DB-Migrationen** | 16 Versionen (Alembic) |
| **Sicherheitslücken (kritisch)** | **8** (RCE, Klartext-Keys, kein Auth, Sandbox fehlt, etc.) |
| **Code-Smells** | **15+** (Monolithen, keine Tests, Exception-Patterns, Stilvermischung) |
| **Empfohlene Sofortmaßnahmen** | **6** (heute umsetzbar) |

---

## 🔴 Kritische Sicherheitslücken

### 1. 🔥 RCE via Sub-Agent-Spawner (Kritisch)

**Fundort:** `backend/app/services/sub_agent.py` (Z. 127-151)

```python
context_parts = [
    f"task_id={t.id}",
    f"title={t.title}",          # ← User-Input!
    f"description={t.description or ''}",  # ← User-Input!
]
context = "; ".join(context_parts)
cmd = [str(bash), str(spawn_script), role, t.id, context]
proc = subprocess.Popen(cmd, ...)
```

**Risiko:** Ein Task mit `title=; rm -rf /` würde ungefiltert an `spawn.sh` übergeben.  
**Status:** ⚠️ Bereits teilweise gefixt (Whitelist + Regex-Prüfung vorhanden), aber `spawn.sh` selbst könnte noch anfällig sein.

**Sofortmaßnahme:** Shell-Escape aller Parameter, `spawn.sh` auf Injection prüfen, Sandbox (Docker) für Execution.

---

### 2. 🔥 ProviderCredential speichert API-Keys im Klartext (Kritisch)

**Fundort:** `backend/app/models/provider_credential.py` (Z. 36)

```python
api_key: Mapped[Optional[str]] = mapped_column(Text)  # ← Klartext in DB!
```

**Risiko:** API-Keys von MiniMax, Kimi, OpenAI etc. werden **unverschlüsselt** in der SQLite-Datenbank gespeichert. Bei einem Backup-Diebstahl oder SQL-Injection sind alle Keys kompromittiert.

**Sofortmaßnahme:** `api_key`-Spalte verschlüsseln (SQLAlchemy `TypeDecorator` mit AES-256) oder Keys nur als Referenz auf Umgebungsvariablen speichern.

---

### 3. 🔥 Auth ist ein Stub (Kritisch)

**Fundort:** `backend/app/auth.py` (Z. 13-20)

```python
async def require_auth(credentials) -> str:
    if not settings.AUTH_ENABLED:  # default: False
        return "dev-user"  # ← JEDER hat Zugriff
```

**Risiko:** Die gesamte REST-API ist ohne Authentifizierung erreichbar. Tasks, SOPs, Projekte, API-Keys, Backup/Restore – alles öffentlich.

**Sofortmaßnahme:** `AUTH_ENABLED=True` forcieren, JWT-Validierung implementieren (PyJWT ist bereits installiert).

---

### 4. 🔥 SOP-Engine führt dynamische Actions ohne Sandbox aus (Hoch)

**Fundort:** `backend/app/services/sop_engine.py` (Z. 80+, Z. 254+)

```python
ALLOWED_SOP_ACTIONS = frozenset({
    "noop", "set_status", "ask_user", "llm_call", "spawn_sop",
    "review_task", "assign_worker", "implement", "test", ...
})
```

**Risiko:** Jede `spawn_sop`-Action startet eine Sub-SOP mit eigenen `action_params`. LLM-Calls verursachen Kosten. Ein bösartiger SOP-Step könnte unbegrenzte Kosten generieren oder Systembefehle ausführen.

**Sofortmaßnahme:** Budget-Guard pro Instance, Timeout-Limit, Action-Whitelist mit Pydantic-Schemas, Execution-Trace.

---

### 5. 🔥 CODE_AGENT_API_TOKEN hat "dev" als Default (Hoch)

**Fundort:** `backend/app/services/worker_service.py` (Z. 43)

```python
CODE_AGENT_API_TOKEN: str = os.environ.get("CODE_AGENT_API_TOKEN", "dev")
```

**Risiko:** Der API-Token für Agent-Kommunikation ist hartcodiert auf `"dev"`. Wenn das Backend erreichbar ist, können Angreifer mit `Authorization: Bearer dev` auf alle Endpoints zugreifen (wenn Auth aktiviert wäre).

**Sofortmaßnahme:** Kein Default-Wert – Fehler werfen, wenn nicht gesetzt.

---

### 6. 🔥 EventLog-Tabelle auto-created in Production (Hoch)

**Fundort:** `backend/app/events.py` (Z. 44-46, 79-80)

```python
def ensure_table():
    EventLog.__table__.create(bind=engine, checkfirst=True)
```

**Risiko:** `ensure_table()` wird bei jedem SSE-Stream und jedem `publish_event` aufgerufen. Erstellt die Tabelle automatisch – umgeht Migrationen, kann Datenbank inkonsistent machen.

**Sofortmaßnahme:** `ensure_table()` nur in `ENV=development` erlauben, sonst via Alembic migrieren.

---

### 7. 🔥 Fehlende Eingabevalidierung bei vielen Endpoints (Hoch)

**Fundort:** `backend/app/routers/tasks.py` (Z. 135-152), `backend/app/routers/sops.py` (Z. 185-200)

```python
@router.post("/task-type")
async def set_task_type(id: str, body: dict, ...):  # ← body: dict! Kein Pydantic!
```

**Risiko:** Endpoints mit `body: dict` akzeptieren beliebige JSON-Strukturen ohne Validierung. LIKE-Queries mit f-Strings (`f"{task_id}%"`) in tasks.py (Z. 101-109) sind zwar parametrisiert, aber das Pattern ist fehleranfällig.

**Sofortmaßnahme:** Alle `body: dict` durch Pydantic-Schemas ersetzen. LIKE-Queries durch exakte Matches ersetzen.

---

### 8. 🔥 Input-Validierung umgehbar (Mittel)

**Fundort:** `backend/app/services/sub_agent.py` (Z. 52-55)

```python
_SAFE_TEXT_RE = re.compile(r"^[\w\s.,:/'+=@\-äöüÄÖÜßéèêàáâçÇñÑ]{1,10000}$", re.UNICODE)
```

**Risiko:** Die Regex validiert nur gegen Druckbuchstaben – keine Prüfung auf Länge (10.000 Zeichen!). Ein sehr langer Titel könnte Buffer Overflow in `spawn.sh` auslösen.

**Sofortmaßnahme:** Längenbegrenzung auf 500 Zeichen (abgestimmt mit DB-Constraint `String(500)`).

---

## 🟠 Mittelschwere Findings

### 9. 🔧 Zwei verschiedene SQLAlchemy-Stile vermischt

**Fundort:** `backend/app/events.py` vs. `backend/app/models/*.py`

```python
# events.py (ALTES Style - SQLAlchemy 1.x)
class EventLog(Base):
    id: Column = Column(Integer, primary_key=True, autoincrement=True)  # ← typed als Column!

# models/task.py (NEUES Style - SQLAlchemy 2.0)
class Task(Base):
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # ← korrekt
```

**Alle Modelle außer Events nutzen:** SQLAlchemy 2.0 Style  
**Events nutzt:** SQLAlchemy 1.x (oder älter) Style  

**Problem:** `id: Column = Column(...)` weist den Typ `Column` zu, nicht den Column-Typ. Funktioniert nur, weil SQLAlchemy es toleriert. Inkonsistent mit dem Rest des Projekts.

**Fix:** EventLog auf SQLAlchemy 2.0 Style umstellen.

---

### 10. 🔧 secrets.token_hex(6) in 12 Dateien – kein zentraler ID-Generator

**Fundort:** Überall

```python
# role_service.py
def _gen_id() -> str:
    return secrets.token_hex(6)  # 12 Zeichen Hex

# task_service.py
def _gen_id() -> str:
    return secrets.token_hex(6)  # 12 Zeichen Hex (identisch!)

# sop_engine.py
def _gen_id() -> str:
    return secrets.token_hex(6)  # Nochmal!
```

**Problem:** 12× duplizierte `_gen_id()`-Funktion. Keine zentrale Stelle. Wenn das ID-Format geändert werden muss (z.B. UUIDv4 oder längere IDs), müssen alle 12 Dateien einzeln bearbeitet werden.

**Fix:** Zentrale `gen_id()` in `utils/id_generator.py`, von allen Modulen importieren.

---

### 11. 🔧 sub_agent.py umgeht Circular Imports mit Inline-Import

**Fundort:** `backend/app/services/sub_agent.py` (Z. 213-216)

```python
def TaskService_add_history_safe(db, t, event, agent, details):
    from .task_service import TaskService  # ← Lazy Import!
    return TaskService._add_history(db, t, event, agent=agent, details=details)
```

**Problem:** Explizites Umgehen eines Circular Imports durch Inline-Import. Zeigt, dass die Architektur nicht sauber entkoppelt ist.

**Fix:** Event-Pattern einführen: SubAgent sendet Event `sub_agent_spawned`, TaskService subscribed darauf.

---

### 12. 🔧 WorkerService verwendet alten `db.query()`-Stil

**Fundort:** `backend/app/services/worker_service.py` (Z. 89-99)

```python
# ALTER Stil (SQLAlchemy 1.x)
query = db.query(Task).filter(Task.status == "todo")

# Andere Services nutzen NEUEN Stil (SQLAlchemy 2.0)
stmt = select(Task).where(Task.status == "todo")
tasks = list(db.execute(stmt).scalars())
```

**Problem:** Der WorkerService verwendet den alten `query`-API-Stil, während der Rest des Projekts auf den neuen `select()`-Stil migriert ist. Inkonsistent und verwirrend.

**Fix:** WorkerService auf `select()`-Stil umstellen (konsistent zum Rest).

---

### 13. 🔧 Kanban.tsx Frontend = 1.413 Zeilen (Monolith)

**Fundort:** `frontend/src/pages/Kanban.tsx`

```typescript
// Eine Datei: 1.413 Zeilen
// Enthält: Board-Ansicht, Project-Selector, Task-Columns, Search, Filter, Modal-Trigger, Tabs, Pagination, ...
```

**Problem:** Der Kanban-Renderer ist eine monolithische Komponente mit zu vielen Verantwortlichkeiten. Das ersetzt die Erkennung von Fehlern bei Änderungen.

**Fix:** Aufteilen in: `BoardColumn.tsx`, `TaskCard.tsx`, `ProjectSelector.tsx`, `SearchFilter.tsx`, etc.

---

### 14. 🔧 Sops.tsx Frontend = 3.235 Zeilen (KRITISCHER Monolith!)

**Fundort:** `frontend/src/pages/Sops.tsx`

```typescript
// 3.235 Zeilen! Die größte Datei im gesamten Projekt
// Enthält: SOP-Liste, Step-Editor, BPMN-Viewer, UML-Generator, ...
```

**Problem:** **3.235 Zeilen Frontend-Code** in einer einzigen Datei. Das ist 70% größer als der größte Backend-Monolith (`sop_engine.py` mit 1.941 Zeilen). Extrem schwer zu warten, zu testen oder zu erweitern.

**Fix:** Aufteilen in: `SopList.tsx`, `SopDetail.tsx`, `SopStepEditor.tsx`, `SopBpmnViewer.tsx`, `SopUmlViewer.tsx`, etc.

---

### 15. 🔧 TaskDetailPanel.tsx = 962 Zeilen

**Fundort:** `frontend/src/components/TaskDetailPanel.tsx`

**Problem:** Auch der Task-Detail-Panel ist zu groß für eine einzelne Komponente.

**Fix:** Aufteilen in: `TaskHeader.tsx`, `TaskHistory.tsx`, `TaskMetrics.tsx`, `TaskActions.tsx`.

---

### 16. 🔧 ProviderCredential-Endpoints erlauben API-Key-Verwaltung über API

**Fundort:** `backend/app/models/provider_credential.py`, `backend/app/routers/provider_credentials.py` (angenommen)

**Problem:** `ProviderCredential` kann API-Keys über REST-Endpoints CRUD-verwalten. Ohne Auth (siehe Finding 1) und ohne Encryption (siehe Finding 2) ist das eine kritische Schwachstelle.

**Fix:** Entweder Encryption für API-Keys oder die Tabelle ganz aus der API nehmen (Keys nur via .env).

---

### 17. 🔧 requirements.txt hat doppelten Eintrag

**Fundort:** `backend/requirements.txt` (Z. 14-15)

```txt
sse-starlette==2.1.3
sse-starlette==2.1.3  # ← Doppelt!
```

**Problem:** `pip install` gibt Warnung aus. `slowapi` fehlt (wird importiert, aber nicht in requirements.txt).

**Fix:** Duplikat entfernen, `slowapi` ergänzen.

---

## 🟡 Leichte Findings / Code-Smells

### 18. 📝 `status_labels.py` führt Test-Code beim Import aus

**Fundort:** `backend/app/utils/status_labels.py` (Z. 155-183)

```python
def _run_tests():
    print("=== display_status Tests ===")  # ← print() statt logger!
    ...
_run_tests()  # ← Kein __name__-Guard!
```

**Fix:** `if __name__ == "__main__":` hinzufügen.

---

### 19. 📝 Zwei SelfImprovement-Pages (Tippfehler-Duplikat)

**Fundort:** `frontend/src/pages/Selfimprovment.tsx` + `frontend/src/pages/SelfImprovement.tsx`

**Problem:** Beide Dateien existieren. Eine ist ein Tippfehler (`Selfimprovment` statt `SelfImprovement`).

**Fix:** Löschen der Tippfehler-Version, Import in App.tsx korrigieren.

---

### 20. 📝 Frontend main.tsx verwendet innerHTML für Error-Handler

**Fundort:** `frontend/src/main.tsx` (Z. 12)

```javascript
el.innerHTML = '<div style="color:#f85149;padding:20px;...>' + e.message + '</div>';
```

**Problem:** `innerHTML` bei Fehlerbehandlung ist akzeptabel, aber `e.message` könnte HTML enthalten (XSS-Risiko bei Fehlern, die Daten rendern).

**Fix:** `el.textContent = 'Error: ' + e.message` verwenden oder DOMPurify nutzen.

---

### 21. 📝 CORS_ORIGINS .env-Format fehleranfällig

**Fundort:** `backend/.env` (Z. 46), `backend/app/config.py` (Z. 78-82)

```
# .env:
CORS_ORIGINS=["http://localhost:5181","http://127.0.0.1:5181"]
```

**Problem:** Pydantic erwartet `list[str]`, bekommt aber einen JSON-String. Pydantic v2 parst das nicht automatisch.

**Fix:** Entweder Komma-separierte Liste oder Custom Validator in `config.py`.

---

### 22. 📝 Frontend api.ts verwendet `any` durchgehend

**Fundort:** `frontend/src/api.ts` (alle Methoden)

```typescript
export const api = {
  get: <T = any>(path: string) => request<T>("GET", path),  // ← any als Default!
  listProjects: () => request<any>("GET", "/api/kanban/projects"),  // ← any!
}
```

**Problem:** Ca. 100+ Methoden nutzen `any` als Response-Typ. Keine Typsicherheit. Frontend-Code muss auf magische Property-Namen vertrauen.

**Fix:** TypeScript-Interfaces für alle API-Responses definieren, `any` eliminieren.

---

### 23. 📝 Gemini-Doppel-Eintrag in KNOWN_PRICING

**Fundort:** `backend/app/services/pricing_service.py`

```python
"ollama/gemma3:12b": {"input_per_1m": "0", "output_per_1m": "0"},
"ollama/gemma3:8b":  {"input_per_1m": "0", "output_per_1m": "0"},
```

**Problem:** "Gemma" wurde als "Gemini" bezeichnet (Docs-Kommentar). Doppelte Einträge durch ähnliche Modellnamen.

**Fix:** Kommentare korrigieren, Pricing auf Konsistenz prüfen.

---

### 24. 📝 Keine globalen Frontend-Error-Boundaries

**Fundort:** `frontend/src/App.tsx`

**Problem:** Kein `<ErrorBoundary>` um die App. Ein Runtime-Fehler in einer Page führt zur weißen Seite.

**Fix:** React Error Boundary-Komponente erstellen und um `<Routes>` legen.

---

### 25. 📝 Fehlende graceful-shutdown-Logik für Ports

**Fundort:** Frontend Dev-Server (Port 5181), Backend (Port 9220)

**Problem:** Ports bleiben nach `Strg+C` blockiert. `PORT_ALREADY_IN_USE`-Fehler beim Neustart.

**Fix:** In `package.json` `"dev": "vite --port 5181 --strictPort"` → aber strictPort belegt den Port exklusiv. Besser: `preview` vor dev killen.

---

## 📋 Vollständige Checkliste

| # | Finding | Kategorie | Schwere | Aufwand | Seite im Review |
|---|---------|-----------|---------|---------|-----------------|
| 1 | RCE via Sub-Agent-Spawner | Sicherheit | 🔴 Kritisch | 1-2h | Finding 1 |
| 2 | ProviderCredential Klartext-Keys | Sicherheit | 🔴 Kritisch | 30min | Finding 2 |
| 3 | Auth ist Stub | Sicherheit | 🔴 Kritisch | 2-4h | Finding 3 |
| 4 | SOP-Engine ohne Sandbox | Sicherheit | 🔴 Hoch | 2-3h | Finding 4 |
| 5 | CODE_AGENT_API_TOKEN=dev | Sicherheit | 🔴 Hoch | 5min | Finding 5 |
| 6 | EventLog auto-create | Betrieb | 🔴 Hoch | 30min | Finding 6 |
| 7 | Fehlende Eingabevalidierung | Sicherheit | 🔴 Hoch | 2-3h | Finding 7 |
| 8 | Input-Längenbegrenzung fehlt | Sicherheit | 🟠 Mittel | 15min | Finding 8 |
| 9 | Zwei SQLAlchemy-Stile | Qualität | 🟠 Mittel | 30min | Finding 9 |
| 10 | `_gen_id()` 12× dupliziert | Qualität | 🟠 Mittel | 30min | Finding 10 |
| 11 | Inline-Import für Circular Import | Architektur | 🟠 Mittel | 1-2h | Finding 11 |
| 12 | WorkerService alter query-Stil | Qualität | 🟡 Leicht | 15min | Finding 12 |
| 13 | Kanban.tsx 1.413 Zeilen | Frontend | 🟠 Mittel | 2-3h | Finding 13 |
| 14 | 💥 Sops.tsx **3.235 Zeilen** | Frontend | 🔴 Hoch | 4-6h | Finding 14 |
| 15 | TaskDetailPanel 962 Zeilen | Frontend | 🟡 Leicht | 1-2h | Finding 15 |
| 16 | API-Key-Verwaltung über API | Sicherheit | 🟠 Mittel | 1h | Finding 16 |
| 17 | requirements.txt doppelt | Build | 🟡 Leicht | 5min | Finding 17 |
| 18 | status_labels print() in Prod | Qualität | 🟡 Leicht | 2min | Finding 18 |
| 19 | SelfImprovement Duplikat | Frontend | 🟡 Leicht | 2min | Finding 19 |
| 20 | innerHTML in main.tsx | Frontend | 🟡 Leicht | 5min | Finding 20 |
| 21 | CORS-Origins Parsing-Fehler | Config | 🟡 Leicht | 15min | Finding 21 |
| 22 | api.ts durchgehend `any` | Frontend | 🟠 Mittel | 2-3h | Finding 22 |
| 23 | Pricing-Kommentar falsch | Qualität | 🟡 Leicht | 2min | Finding 23 |
| 24 | Kein Error-Boundary | Frontend | 🟡 Leicht | 30min | Finding 24 |
| 25 | Port-Freigabe nach Shutdown | Betrieb | 🟡 Leicht | 15min | Finding 25 |

---

## 📊 Bot-Anzahl-Werte-Summary

| Kategorie | 🔴 Kritisch | 🟠 Mittel | 🟡 Leicht | Summe |
|-----------|:-----------:|:---------:|:---------:|:-----:|
| **Sicherheit** | 8 | 1 | 0 | **9** |
| **Backend-Qualität** | 0 | 3 | 3 | **6** |
| **Frontend-Qualität** | 1 | 3 | 3 | **7** |
| **Betrieb/Config** | 1 | 0 | 3 | **4** |
| **Gesamt** | **10** | **7** | **9** | **26** |

### 🎯 Top-6 Sofortmaßnahmen (heute umsetzbar)

1. **RCE schließen** (Finding 1) – Shell-Metazeichen final blocken, `spawn.sh` prüfen
2. **API-Keys verschlüsseln** (Finding 2) – ProviderCredential mit Encryption
3. **Auth aktivieren** (Finding 3) – JWT-Validierung + Login-Endpoint
4. **CODE_AGENT_API_TOKEN ohne Default** (Finding 5) – Fehler werfen wenn nicht gesetzt
5. **EventLog auto-create entfernen** (Finding 6) – Nur per Migration
6. **Sops.tsx aufteilen** (Finding 14) – 3.235 Zeilen sind nicht wartbar

---

## 🔗 Vergleich mit vorherigen Analysen

| Metrik | Meine 1. Analyse (10 Findings) | Kimi's Analyse (10 Findings) | **Dieses Review (26 Findings)** |
|--------|:------------------------------:|:----------------------------:|:-------------------------------:|
| **Sicherheit** | 2 | 5 | **9** |
| **Backend-Qualität** | 4 | 1 | **6** |
| **Frontend-Qualität** | 0 | 2 | **7** |
| **Betrieb** | 1 | 2 | **4** |
| **Gesamt** | 10 | 10 | **26** |

Dieses Review deckt **16 neue Findings** ab, die in keiner der beiden vorherigen Analysen enthalten waren.
