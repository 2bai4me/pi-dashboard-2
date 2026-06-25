# Implementation-Plan-Schema

> **Version:** 1.0
> **Stand:** 23.06.2026
> **Task:** [PI-Dashboard 2.0] JSON-Schema fuer `task.implementation_plan` definieren (`9f2f473bf1cc`)
> **Pydantic-Model:** `app.schemas.task.ImplementationPlan`
> **Status:** Offiziell, verbindlich fuer SOP Step 0 (CIO) und Step 1 (pi-architect)

---

## Ueberblick

Das `implementation_plan`-Feld eines Tasks speichert einen **strukturierten Implementierungsplan**, der vom CIO (in Triage/Step 0) und/oder vom pi-architect (in GO/Step 1) befuellt wird. Das Schema validiert die Struktur beim Speichern ueber den `PUT /api/kanban/tasks/{id}/implementation-plan`-Endpoint und gibt bei Fehlern HTTP 422 mit detaillierter Fehlerliste zurueck.

---

## Schema-Felder (vollstaendig)

| Feld | Typ | Pflicht | Default | Beschreibung |
|---|---|---|---|---|
| `summary` | str | ✅ | — | 1 Satz, was wird gemacht (1-500 Zeichen) |
| `context` | str | ❌ | `null` | Warum, Bezug zu Anforderungen (max 2000) |
| `affected_files` | List[FileChange] | ❌ | `[]` | Betroffene Dateien mit Change-Type |
| `api_changes` | List[ApiChange] | ❌ | `[]` | API-Endpoints, die geaendert werden |
| `db_changes` | List[DbChange] | ❌ | `[]` | Datenbank-Aenderungen |
| `sub_tasks` | List[SubTask] | ❌ | `[]` | Zerlegung in Teilaufgaben |
| `acceptance_criteria` | List[AcceptanceCriterion] | ❌ | `[]` | Messbare Akzeptanzkriterien |
| `risks` | List[Risk] | ❌ | `[]` | Risiken mit likelihood/impact |
| `dependencies` | List[Dependency] | ❌ | `[]` | Externe Abhaengigkeiten |
| `test_strategy` | str | ❌ | `null` | 1-2 Saetze zur Test-Strategie (max 2000) |
| `rollout_plan` | str | ❌ | `null` | 1-2 Saetze zu Rollout-Reihenfolge (max 2000) |
| `notes` | str | ❌ | `null` | Freitext-Notizen (max 5000) |
| `created_by` | str | ❌ | `null` | `'CIO'` \| `'pi-architect'` \| `'manual'` |
| `created_at` | datetime | ❌ | `null` | Wird beim Speichern auto-gesetzt |
| `version` | int | ❌ | `1` | Bei Updates inkrementieren |

---

## Sub-Schemas

### `FileChange` (affected_files)

```python
{
  "path": "src/api/foo.py",           # Pflicht, 1-500 Zeichen
  "change_type": "create|modify|delete",  # Enum
  "description": "Was wird geaendert"     # Pflicht, 1-1000 Zeichen
}
```

### `ApiChange` (api_changes)

```python
{
  "method": "GET|POST|PUT|PATCH|DELETE",  # Enum, Pattern-geprueft
  "path": "/api/kanban/tasks",            # Pflicht, 1-500 Zeichen
  "request_schema": "...",                # optional, JSON-Schema oder TS-Interface
  "response_schema": "...",               # optional
  "breaking": false                       # optional, default false
}
```

### `DbChange` (db_changes)

```python
{
  "type": "create_table|alter_table|add_index|drop_index|add_column|drop_column",  # Enum
  "target": "tasks",                       # Pflicht, 1-200 Zeichen
  "details": "ALTER TABLE tasks ADD COLUMN foo VARCHAR(100)"  # Pflicht, 1-2000 Zeichen
}
```

### `SubTask` (sub_tasks)

```python
{
  "id": "st1",                  # Pattern: st[1-9][0-9]*, EINDUTIG in der Liste
  "title": "Setup",             # Pflicht, 1-200 Zeichen
  "assigned_role": "pi-coder",  # Pflicht
  "depends_on": ["st0"],        # optional, IDs anderer Sub-Tasks
  "estimate_min": 30            # Pflicht, 1-480 (max 8h pro Sub-Task)
}
```

### `AcceptanceCriterion` (acceptance_criteria)

```python
{
  "id": "ac1",                  # Pattern: ac[1-9][0-9]*, EINDUTIG
  "description": "POST /api/auth/login liefert 200 + Token",  # Pflicht
  "test_method": "integration", # Pflicht (z.B. unit|integration|e2e|manual)
  "expected": "HTTP 200 mit JWT"  # Pflicht, MESSBAR
}
```

### `Risk` (risks)

```python
{
  "id": "r1",                   # Pattern: r[1-9][0-9]*
  "description": "Google OAuth kann ausfallen",  # Pflicht
  "likelihood": 2,              # Pflicht, 1-5
  "impact": 4,                  # Pflicht, 1-5
  "mitigation": "Fallback auf Email-Login"       # Pflicht
}
```

### `Dependency` (dependencies)

```python
{
  "type": "internal|external|service",  # Enum
  "ref": "service:oauth-provider",      # Pflicht
  "status": "ready|blocked|partial"     # Enum
}
```

---

## Beispiele

### Beispiel 1: Bugfix

```json
{
  "summary": "Bug: Login-Endpoint gibt 500 bei leerem Body",
  "context": "User-Report 22.06.2026, Prio hoch weil Production betroffen",
  "affected_files": [
    {
      "path": "backend/app/routers/auth.py",
      "change_type": "modify",
      "description": "Validierung fuer leeren Body ergaenzen"
    }
  ],
  "sub_tasks": [
    {
      "id": "st1",
      "title": "Reproduzieren + Validierung implementieren",
      "assigned_role": "pi-coder",
      "depends_on": [],
      "estimate_min": 60
    },
    {
      "id": "st2",
      "title": "Unit-Test fuer leeren Body",
      "assigned_role": "pi-tester",
      "depends_on": ["st1"],
      "estimate_min": 30
    }
  ],
  "acceptance_criteria": [
    {
      "id": "ac1",
      "description": "POST /api/auth/login mit {} liefert 400 nicht 500",
      "test_method": "integration",
      "expected": "HTTP 400 mit error-detail 'body is empty'"
    }
  ],
  "risks": [
    {
      "id": "r1",
      "description": "Fix bricht bestehende Clients",
      "likelihood": 2,
      "impact": 3,
      "mitigation": "Alte Clients sollten Body senden, was bei 400 mit klarer Fehlermeldung sichtbar wird"
    }
  ],
  "test_strategy": "Unit-Tests + Integration-Tests mit pytest + httpx",
  "rollout_plan": "Direkter Deploy, kein Feature-Flag noetig (Bugfix)",
  "created_by": "pi-architect",
  "version": 1
}
```

### Beispiel 2: Feature (OAuth2-Login)

```json
{
  "summary": "OAuth2-Login mit Google-Provider einbauen",
  "context": "User-Direktive 15.06.2026, Auth-Provider fehlt komplett",
  "affected_files": [
    {"path": "backend/app/services/oauth_service.py", "change_type": "create", "description": "OAuth-Client-Wrapper"},
    {"path": "backend/app/routers/auth.py", "change_type": "modify", "description": "Login-Endpoint mit OAuth-Flow"},
    {"path": "frontend/src/components/LoginButton.tsx", "change_type": "modify", "description": "Google-Button"}
  ],
  "api_changes": [
    {
      "method": "GET",
      "path": "/api/auth/oauth/google",
      "request_schema": null,
      "response_schema": "Redirect zu Google OAuth",
      "breaking": false
    },
    {
      "method": "GET",
      "path": "/api/auth/oauth/callback",
      "request_schema": "code (Query)",
      "response_schema": "TokenResponse { access_token, refresh_token, user }",
      "breaking": false
    }
  ],
  "db_changes": [
    {
      "type": "create_table",
      "target": "oauth_tokens",
      "details": "id, user_id, provider, access_token, refresh_token, expires_at, created_at"
    }
  ],
  "sub_tasks": [
    {"id": "st1", "title": "OAuth-Service + Google-Config", "assigned_role": "pi-coder", "depends_on": [], "estimate_min": 90},
    {"id": "st2", "title": "Login-Endpoint /oauth/google + /callback", "assigned_role": "pi-coder", "depends_on": ["st1"], "estimate_min": 120},
    {"id": "st3", "title": "Frontend Login-Button", "assigned_role": "pi-coder", "depends_on": ["st2"], "estimate_min": 60},
    {"id": "st4", "title": "Tests (Unit + Integration + E2E)", "assigned_role": "pi-tester", "depends_on": ["st3"], "estimate_min": 90}
  ],
  "acceptance_criteria": [
    {
      "id": "ac1",
      "description": "Login mit Google fuehrt zu erfolgreicher Authentifizierung + JWT-Token",
      "test_method": "e2e",
      "expected": "User wird eingeloggt, Token in localStorage, Redirect zu /dashboard"
    },
    {
      "id": "ac2",
      "description": "Bei OAuth-Fehler: User bekommt klare Fehlermeldung",
      "test_method": "integration",
      "expected": "Redirect zu /login?error=oauth_failed mit toast"
    }
  ],
  "risks": [
    {"id": "r1", "description": "Google OAuth-Service kann ausfallen", "likelihood": 2, "impact": 4, "mitigation": "Fallback Email-Login, Status-Monitor"},
    {"id": "r2", "description": "Token wird in DB gespeichert, Sicherheits-Risiko bei DB-Leak", "likelihood": 1, "impact": 5, "mitigation": "Tokens verschluesselt (Fernet), DB-Backup verschluesselt"}
  ],
  "dependencies": [
    {"type": "service", "ref": "service:google-oauth", "status": "ready"},
    {"type": "service", "ref": "service:fernet-key-management", "status": "ready"}
  ],
  "test_strategy": "Unit-Tests mit Mock-OAuth-Provider, E2E mit Google-Sandbox-Account",
  "rollout_plan": "Feature-Flag 'auth_oauth' zunaechst auf 10% User, dann 100% nach 1 Woche",
  "notes": "Security-Review zwingend erforderlich vor Rollout",
  "created_by": "pi-architect",
  "version": 1
}
```

### Beispiel 3: Refactor

```json
{
  "summary": "Refactor: Token-Usage-Store von JSON auf SQLite umstellen",
  "context": "Performance-Issue bei >10k Eintraegen, JSON-File zu langsam",
  "affected_files": [
    {"path": "backend/app/services/token_usage_store.py", "change_type": "modify", "description": "JSON-File-IO durch SQLite-Queries ersetzen"},
    {"path": "backend/app/db/migrations/versions/20260623_token_usage.py", "change_type": "create", "description": "Alembic-Migration"}
  ],
  "db_changes": [
    {"type": "create_table", "target": "token_usage", "details": "Migration: id, task_id, model, role, tokens_in, tokens_out, cost_usd, recorded_at"}
  ],
  "sub_tasks": [
    {"id": "st1", "title": "Alembic-Migration", "assigned_role": "pi-coder", "depends_on": [], "estimate_min": 30},
    {"id": "st2", "title": "TokenUsageStore-Refactor", "assigned_role": "pi-coder", "depends_on": ["st1"], "estimate_min": 90},
    {"id": "st3", "title": "Migration alter JSON-Daten", "assigned_role": "pi-coder", "depends_on": ["st2"], "estimate_min": 60},
    {"id": "st4", "title": "Performance-Vergleich vorher/nachher", "assigned_role": "pi-tester", "depends_on": ["st3"], "estimate_min": 30}
  ],
  "acceptance_criteria": [
    {
      "id": "ac1",
      "description": "Token-Usage-Queries < 100ms fuer 10k Eintraege",
      "test_method": "performance",
      "expected": "p95 latency < 100ms bei 10k Records"
    },
    {
      "id": "ac2",
      "description": "Alte JSON-Daten sind nach Refactor vollstaendig migriert",
      "test_method": "integration",
      "expected": "Row-Count alt == Row-Count neu"
    }
  ],
  "risks": [
    {"id": "r1", "description": "Migration schlaegt bei grossen Datenmengen fehl", "likelihood": 3, "impact": 4, "mitigation": "Batch-weise migrieren (1000 Records pro Batch), Transaction-Rollback"}
  ],
  "test_strategy": "Performance-Tests + Datenintegritaet-Tests",
  "rollout_plan": "Migration in Wartungsfenster, parallel JSON-File als Backup 7 Tage behalten",
  "created_by": "pi-architect",
  "version": 1
}
```

---

## API-Verwendung

### Plan setzen (CIO oder pi-architect)

```bash
PUT /api/kanban/tasks/{task_id}/implementation-plan
Authorization: Bearer dev
Content-Type: application/json

{
  "implementation_plan": {
    "summary": "Login mit OAuth2",
    "sub_tasks": [{"id": "st1", "title": "Setup", "assigned_role": "pi-coder", "estimate_min": 30}],
    "acceptance_criteria": [{"id": "ac1", "description": "Test", "test_method": "unit", "expected": "OK"}]
  }
}
```

**Antwort 200 OK:** Task-Read mit gespeichertem `implementation_plan`
**Antwort 422:** Validierungs-Fehler mit Detail-Liste

### Plan loeschen

```bash
PUT /api/kanban/tasks/{task_id}/implementation-plan
{ "implementation_plan": null }
```

### Validierungsfehler-Beispiel (HTTP 422)

```json
{
  "error": "http_error",
  "detail": {
    "error": "implementation_plan validation failed",
    "validation_errors": [
      {"loc": "summary", "msg": "String should have at least 1 character", "type": "string_too_short"},
      {"loc": "sub_tasks.0.id", "msg": "String should match pattern '^st[1-9][0-9]*$'", "type": "string_pattern_mismatch"},
      {"loc": "sub_tasks", "msg": "Value error, sub_tasks IDs nicht eindeutig: ['st1', 'st1']", "type": "value_error"}
    ]
  },
  "status_code": 422
}
```

---

## Integration mit SOP

| SOP-Step | Agent | Aktion |
|---|---|---|
| Step 0 (Triage) | CIO | Setzt initialen Plan (was + warum, grobe Skizze) |
| Step 1 (GO) | pi-architect | Detailliert den Plan, Output wird automatisch in `task.implementation_plan` geschrieben |
| Step 2 (Implementation) | pi-coder-lead | Liest Plan, verteilt Sub-Tasks an Worker |
| Step 3 (Test) | pi-test-lead | Liest `acceptance_criteria`, generiert Tests |
| Step 4 (Review) | pi-review-lead | Prueft Plan-Konsistenz |
| Step 5 (Auto-Fix) | pi-fixer | Findet Abweichungen, meldet in Plan |

---

## Versionierung

| Version | Datum | Aenderung |
|---|---|---|
| 1.0 | 23.06.2026 | Initial-Version (Task 9f2f473bf1cc): Pydantic-Schema, 11 Sub-Schemas, 11 Unit-Tests, 5 E2E-Tests |

---

## Referenzen

- Pydantic-Schema: `backend/app/schemas/task.py` (Klasse `ImplementationPlan`)
- Endpoint: `PUT /api/kanban/tasks/{id}/implementation-plan` (in `routers/tasks.py`)
- Unit-Tests: `backend/tests/test_implementation_plan.py` (11 Tests)
- SOP-Definition: `docs/SOP-ARCHITECTURE.md`
- Agent-Development-Guide: `docs/AGENT_DEVELOPMENT_GUIDE.md`
