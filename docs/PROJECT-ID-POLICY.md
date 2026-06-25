# project_id-Handling Policy

> **Version:** 1.0
> **Stand:** 23.06.2026
> **Task:** [PI-Dashboard 2.0] `project_id`-Handling + Orphan-Task-Bereinigung (`0973563537c4`)
> **Status:** Offiziell, verbindlich

---

## Ueberblick

Das `project_id`-Feld eines Tasks ist **optional**. Es darf `null` (oder leerer String) sein, was einen "Orphan-Task" erzeugt. Diese Policy dokumentiert, wann das sinnvoll ist und wie das System damit umgeht.

---

## Grundregel: project_id ist OPTIONAL

### Wann ist `project_id=null` LEGITIM?

| Use-Case | Beispiel | Begruendung |
|---|---|---|
| **Service-Self-Tracking** | `b6f9fc56e6c3` (ME4-PI-Integration Self-Tracking) | Der Service trackt seine eigene Existenz im globalen Board, gehoert aber zu keinem User-Projekt |
| **Globale/projektuebergreifende Tasks** | "Doku schreiben", "CI warten" | Nicht einem einzelnen Projekt zuordbar |
| **Schnellnotizen / Ideas** | Tasks bevor sie einem Projekt zugeordnet werden | Erfassen, spaeter zuordnen |
| **Admin-/System-Tasks** | Cleanup-Tasks, Maintenance | Nicht projektrelevant |

### Wann ist `project_id=null` ein PROBLEM?

- Wenn der User den Task erstellt hat ohne ein Projekt zu waehlen (vergessen)
- Wenn der Test-Task eigentlich zu einem bestimmten Projekt gehoert
- Wenn Orphan-Tasks das Board-UI verfaelschen (Project-Stats sind unvollstaendig)

---

## Backend-Verhalten

### `POST /api/kanban/tasks` (TaskCreate)
- `project_id` ist optional im Schema (`Optional[str] = None`)
- Kein 400-Error bei `null`
- Frontend sollte aber idealerweise eine Warnung zeigen, wenn activeProject null ist

### `PATCH /api/kanban/tasks/{id}` (TaskUpdate, FIX 23.06.2026)

**Vorher:** `project_id` wurde stillschweigend ignoriert (silent fail). PATCH gab 200 zurueck, das Feld wurde aber nicht gespeichert.

**Nachher:** `project_id` wird jetzt aktualisiert:
- Valides `project_id`: wird gesetzt (HTTP 200)
- `project_id=null` oder `""`: loescht die Zuordnung (HTTP 200)
- Ungueltiges `project_id` (nicht existierendes Projekt): HTTP 404 mit Detail `"Project {id} not found"`

**Beispiel:**
```bash
# Task einem Projekt zuordnen
PATCH /api/kanban/tasks/{id}
{ "project_id": "d5976e76247c" }
# -> 200 OK, task.project_id = "d5976e76247c"

# Task-Projekt-Zuordnung loeschen (Self-Tracking)
PATCH /api/kanban/tasks/{id}
{ "project_id": null }
# -> 200 OK, task.project_id = null

# Ungueltiges Projekt
PATCH /api/kanban/tasks/{id}
{ "project_id": "non-existent" }
# -> 404 Not Found, "Project non-existent-id-xyz not found"
```

---

## Frontend-Verhalten

### Projekt-Liste (Kachel-View)
- Zeigt nur Tasks mit gueltigem `project_id`
- Orphan-Tasks sind unsichtbar in der Projekt-Liste
- Aber sichtbar in der globalen Task-Liste (Filter `project_id=null`)

### Triage-Modal
- Bei `activeProject=null` und User klickt "+ New Task":
  - **TODO (User-Direktive)**: Warn-Toast zeigen "Bitte zuerst ein Projekt auswaehlen, sonst ist der Task nicht in der Projekt-Liste sichtbar"
  - Alternative: Modal mit Projekt-Auswahl vor Ideen-Eingabe
  - Self-Tracking-Tasks duerfen ohne Projekt erstellt werden (Override-Option)

### Board-View
- Filter: "Alle / Offen / Erledigt" sollte standardmaessig nur Tasks mit `project_id=activeProject` zeigen
- Toggle "Global anzeigen" zeigt auch Orphan-Tasks

---

## Orphan-Task-Bereinigung (23.06.2026)

Bei der initialen Analyse wurden **9 Orphan-Tasks** identifiziert. Aufteilung:

| Kategorie | Anzahl | Aktion |
|---|---|---|
| Test-Tasks (waren nie produktiv) | 5 | Cancelled (waren Test-Muell) |
| ME4-VP-Test-Tasks (falsch zugeordnet) | 3 | PROJ-2026-004 (ME4 VideoProducer) zugeordnet |
| Service-Self-Tracking (legitim) | 1 | Bleibt project_id=null |

### Konkrete Liste der behobenen Tasks

**Cancelled (5):**
- `2db0dc210c54` - "Test Task 2"
- `ba8831c59938` - "ME4-PI Test 608366c3"
- `64ed392fe09c` - "API-Test Status-Check"
- `c517e566f577` - "Default Project Test b214b5ac"
- `6fb63e4d1654` - "Test Task"

**Re-assigned (3):**
- `96c39119272f` - "ME4-VP Priority Test be9d9900" → PROJ-2026-004
- `807363f136b8` - "ME4-VP Test 3f9b2e8e" → PROJ-2026-004
- `a8a933753692` - "ME4-VP Status Test 11be1c7b" → PROJ-2026-004

**Behalten (1):**
- `b6f9fc56e6c3` - "ME4-PI-Integration: Eigenstaendigen Microservice" (Self-Tracking, legitim)

---

## Lessons Learned

1. **Silent Fail in PATCH**: `TaskUpdate`-Schema hat `project_id` nicht erlaubt, PATCH gab trotzdem 200 zurueck. Das ist der gleiche Anti-Pattern wie bei `subagents.updateConfig` (FIX am 23.06.2026).
2. **Orphan-Tasks entstehen leicht**: Wenn Frontend den activeProject nicht kennt (null), erstellt es Tasks ohne Projekt. Loesung: Frontend-Warnung + Default-Projekt aus URL.
3. **Self-Tracking ist legitim**: Manche Tasks gehoeren bewusst zu keinem Projekt. Die Loesung ist nicht "immer project_id fordern", sondern "Frontend warnen + bessere Defaults".
4. **DB-Lock bei Cleanup**: Bei mehreren parallelen PATCH/DELETE-Operationen waehrend aktiver Background-Jobs kommt es zu SQLite-Locks. Loesung: Scheduler temporaer deaktivieren fuer Cleanup.

---

## Verweise

- Pydantic-Schema: `backend/app/schemas/task.py` (`TaskUpdate`)
- Endpoint: `PATCH /api/kanban/tasks/{id}` in `routers/tasks.py`
- Unit-Tests: `backend/tests/test_project_id_handling.py` (7 Tests)
- E2E-Tests: Live-API verifiziert (valides project_id, ungueltiges project_id=404, null=loeschen)
- Verwandt: Task `9f2f473bf1cc` (ImplementationPlan-Schema)
- Verwandt: Task `dad90780eb76` (tasks_open field - Statistik ueber offene Tasks pro Projekt)

---

## Versionierung

| Version | Datum | Aenderung |
|---|---|---|
| 1.0 | 23.06.2026 | Initial-Version: project_id-Handling, Orphan-Policy, 9 Orphan-Tasks bereinigt, 7 Unit-Tests gruen, 3 E2E-Tests gruen |
