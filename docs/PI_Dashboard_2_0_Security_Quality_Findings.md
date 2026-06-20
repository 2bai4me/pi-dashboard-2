# 🔍 PI Dashboard 2.0 — Code-Analyse: Top 10 Findings

**Projekt:** `D:\Entwicklung\PI-Dashboard 2`  
**Analysedatum:** 20.06.2026  
**Version:** 2.0.0-rc  
**Tech-Stack:** FastAPI (Python 3.14), SQLAlchemy 2.0, SQLite/PostgreSQL, React 19, Vite 8

---

## Executive Summary

| Aspekt | Bewertung |
|---|---|
| **Architektur** | FastAPI-Backend + React/Vite-Frontend, SQLAlchemy 2.0 mit SQLite, Alembic-Migrationen |
| **Funktionsumfang** | Sehr umfangreich (Kanban, SOP-Engine, Sub-Agent-Spawner, Analytics, TTS, Agent-Questions, Board-Operator-Watchdog) |
| **Sicherheit** | ⚠️ **Kritisch mangelhaft** — Auth ist ein Stub, RCE-Pfade vorhanden, keine Eingabevalidierung |
| **Code-Qualität** | ⚠️ **Mittel bis schlecht** — viele `any`-Typen, fehlende Tests, viele `try/except pass`-Blöcke, duplizierter Code |
| **Zukunftssicherheit** | ⚠️ **Mittel** — gute Modularisierung, aber fehlende Tests, hartkodierte Pfade, unsaubere Build-Prozesse |

---

## Priorisierte Findings-Übersicht

| # | Finding | Kategorie | Schweregrad | Geschätzter Aufwand |
|---|---|---|---|---|
| 1 | Authentifizierung & Autorisierung sind nur ein Stub | Sicherheit | 🔴 Kritisch | 2–3 Tage |
| 2 | Sub-Agent-Spawner ermöglicht potenzielle Code-Ausführung | Sicherheit | 🔴 Kritisch | 1–2 Tage |
| 3 | SOP-Engine führt dynamische Aktionen ohne Sandbox aus | Sicherheit | 🔴 Hoch | 2–3 Tage |
| 4 | Fehlende Eingabevalidierung an vielen API-Endpunkten | Sicherheit / Qualität | 🔴 Hoch | 2–3 Tage |
| 5 | Hartkodierte Secrets und unsichere Defaults | Sicherheit | 🔴 Kritisch | 0,5–1 Tag |
| 6 | Automatische Tabellenerstellung in Produktion | Qualität / Sicherheit | 🟠 Hoch | 0,5 Tag |
| 7 | Kein Rate-Limiting, zu permissive CORS, fehlende Timeouts | Sicherheit | 🟠 Mittel-Hoch | 0,5–1 Tag |
| 8 | Keine automatisierten Tests | Qualität / Zukunftssicherheit | 🔴 Hoch | 3–5 Tage |
| 9 | Frontend verwendet `any` überall und hat keine Input-Sanitierung | Qualität / Sicherheit | 🟠 Mittel | 2–3 Tage |
| 10 | Duplizierte Abhängigkeiten, Build-Artefakte im Repo, hartkodierte Pfade | Zukunftssicherheit | 🟡 Mittel | 1 Tag |

---

## Finding 1 — Authentifizierung & Autorisierung sind nur ein Stub

### Problem

`backend/app/auth.py` implementiert keine echte Authentifizierung. `AUTH_ENABLED` ist in `.env.example` default `false`. Wenn aktiviert, wird der übergebene Token nicht validiert, sondern einfach zurückgegeben. Es gibt keine Rollenprüfung, keine Berechtigungen, keine Session-Verwaltung.

### Belege im Code

- `backend/app/auth.py` Zeile 13–20: `require_auth` gibt bei `AUTH_ENABLED=false` immer `"dev-user"` zurück, bei `true` wird der Token nicht validiert.
- `backend/.env.example` Zeile 27: `AUTH_ENABLED=false`.

### Anforderung (was gemacht werden muss)

- `backend/app/auth.py` vollständig neu implementieren.
- JWT-Validierung mit `pyjwt` oder `python-jose` einbauen.
- Passwort-Hashing für Admin-User mit `bcrypt` oder `argon2`.
- Rollenmodell einführen: mindestens `admin`, `cio`, `ceo`, `viewer`.
- Jeder API-Endpoint bekommt eine Rollen-Prüfung (`Depends(require_role(...))`).
- `AUTH_ENABLED` wird in Produktion standardmäßig `true`.
- Login-Endpoint `/api/auth/login` und Token-Refresh implementieren.
- Frontend-Login-Maske bauen und Token im `Authorization`-Header mitsenden.

### Erwartetes Ergebnis

- Nicht authentifizierte Requests erhalten `401 Unauthorized`.
- Benutzer sehen nur Funktionen, die ihrer Rolle erlaubt sind.
- Passwörter liegen nie im Klartext vor.
- Sessions/Token haben eine begrenzte Lebensdauer.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `curl http://127.0.0.1:9220/api/kanban/projects` ohne Token liefert `401`.
- Login mit falschem Passwort liefert `401`, mit korrekten Daten ein JWT.
- Ein Viewer kann keine Tasks löschen (liefert `403`).
- `pytest` enthält Tests für Login, ungültige Token und Rollenverweigerung.
- Kein `return "dev-user"` mehr in `auth.py`.

---

## Finding 2 — Sub-Agent-Spawner ermöglicht potenzielle Code-Ausführung

### Problem

`backend/app/services/sub_agent.py` startet externe Bash-Prozesse über `subprocess.Popen`. Task-ID, Titel und Description werden als Argumente an ein externes `spawn.sh`-Skript übergeben. Es gibt keine Validierung, keine Sandbox, keine Whitelist für erlaubte Rollen/Skripte. Ein Angreifer, der Tasks erstellen kann, könnte Shell-Metazeichen in Titel/Description einschleusen.

### Belege im Code

- `backend/app/services/sub_agent.py` Zeile 127–138: `context_parts` enthält `t.title` und `t.description`, wird mit `;` verbunden und als Argument übergeben.
- Zeile 142–151: `subprocess.Popen([bash, spawn_script, role, t.id, context], ...)` ohne Escaping/Validierung.

### Anforderung (was gemacht werden muss)

- Alle Eingaben (`task_id`, `title`, `description`, `role`) vor Spawning validieren.
- Erlaubte `role`-Werte auf eine Whitelist beschränken (z. B. `pi-coder`, `pi-tester`, `pi-reviewer`).
- Pfad zum `spawn.sh` über `.env` konfigurierbar machen und zur Laufzeit validieren.
- Keine Shell-Metazeichen in `title`/`description` erlauben (Regex-Prüfung).
- `subprocess.Popen` nur mit separaten Argumenten und `shell=False` verwenden.
- Audit-Log für jeden Spawning-Vorgang mit User/Rolle/Zeitpunkt.
- Optional: Sub-Agenten in einer Sandbox (Docker/Windows-Job-Objekt) laufen lassen.

### Erwartetes Ergebnis

- Ein Task mit bösartigem Titel wie `; rm -rf /` wird abgelehnt oder bereinigt.
- Nur vordefinierte Rollen können Sub-Agenten starten.
- Der Spawner-Pfad ist nicht mehr hartkodiert.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- Test `test_spawn_rejects_shell_injection` ist grün.
- `sub_agent.py` enthält eine `ALLOWED_ROLES`-Whitelist.
- Audit-Log enthält Einträge wie `sub_agent_spawned` mit Rollen-Info.
- `ps` zeigt den gestarteten Prozess nur mit sauberen, einzelnen Argumenten.

---

## Finding 3 — SOP-Engine führt dynamische Aktionen ohne Sandbox aus

### Problem

Die SOP-Engine (`backend/app/services/sop_engine.py`) interpretiert Steps mit `action` und `action_params`. Aktionen wie `spawn_sop`, `llm_call`, `ask_user`, `set_status` können über die API erstellt werden. Es gibt keine Validierung, ob eine Aktion erlaubt ist, und ob `action_params` sicher sind. Ein bösartiger SOP-Step könnte beliebige Systembefehle oder unbegrenzte LLM-Kosten verursachen.

### Belege im Code

- `backend/app/routers/sops.py` Zeile 185–200: `StepCreate` erlaubt beliebige `action`- und `action_params`-Werte.
- `backend/app/services/sop_engine.py` Zeile 254+: `run_step` delegiert Actions ohne Whitelist/Validierung.

### Anforderung (was gemacht werden muss)

- Erlaubte `action`-Werte in der SOP-Engine whitelisten (z. B. `noop`, `set_status`, `ask_user`, `llm_call`, `spawn_sop`).
- Für jede Action ein eigenes Pydantic-Schema für `action_params` definieren.
- Unbekannte Actions führen zu einem Fehler (`400 Bad Request`).
- Budget-Guard pro SOP-Instance: maximale Kosten und maximale Laufzeit.
- SOP-Ausführungen in einem Execution-Trace protokollieren.
- Neue SOPs müssen vor Aktivierung validiert werden.

### Erwartetes Ergebnis

- Die SOP-Engine führt nur explizit erlaubte und validierte Actions aus.
- Eine SOP-Instance stoppt automatisch, wenn Budget oder Timeout überschritten wird.
- Jeder Step wird in `sop_executions` nachvollziehbar protokolliert.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `SOPEngine.run_step` hat am Anfang eine Action-Whitelist-Prüfung.
- Test `test_sop_unknown_action_rejected` liefert `400`.
- `sop_executions`-Tabelle enthält für jede Instance einen vollständigen Trace.
- Ein Budget-Limit von 0.01 USD stoppt eine LLM-Action nach Erreichen.

---

## Finding 4 — Fehlende Eingabevalidierung an vielen API-Endpunkten

### Problem

Viele Router akzeptieren `body: dict` statt Pydantic-Schemas. In `tasks.py` werden LIKE-Abfragen mit f-Strings gebaut. Obwohl SQLAlchemy `like()` parametrisiert, ist das Muster fehleranfällig. Es gibt keine Längenbegrenzungen für Titel/Beschreibungen, keine Validierung von `project_id`, `task_id`.

### Belege im Code

- `backend/app/routers/tasks.py` Zeile 135–152: `body: dict` bei `/task-type`.
- Zeile 101–109: `Task.id.like(f"{task_id}%")`.
- Zeile 577–608: History-Abfrage mit `task_id.like(f"{task_id}%")` bei kurzen IDs.

### Anforderung (was gemacht werden muss)

- Alle `body: dict`-Parameter durch Pydantic-Schemas ersetzen.
- IDs (`task_id`, `project_id`, `sop_id`) auf Format prüfen (Hex, 12 Zeichen).
- `title` auf max. 255 Zeichen, `description` auf max. 50.000 Zeichen begrenzen.
- `limit`/`offset` bei Listen-Endpunkten begrenzen (bereits teilweise vorhanden, konsistent machen).
- LIKE-Suchen durch exakte Validierung oder parametrisierte Suche ersetzen.
- Für alle Endpoints `422 Unprocessable Entity` bei invaliden Daten.

### Erwartetes Ergebnis

- Kein Endpoint akzeptiert mehr unstrukturierte `dict`-Bodys.
- Alle IDs haben ein definiertes Format.
- SQL-Injection über Suchparameter ist nicht mehr möglich.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `grep -r "body: dict" backend/app/routers/` liefert keine Treffer mehr.
- `grep -r "\.like(f\"" backend/app/` liefert keine Treffer mehr.
- `pytest` enthält Tests für zu lange Titel, ungültige IDs und SQL-Injection-Versuche.
- Swagger-UI zeigt für jeden Endpoint ein Request-Schema an.

---

## Finding 5 — Hartkodierte Secrets und unsichere Defaults

### Problem

`.env.example` enthält einen hartkodierten JWT-Secret (`change-me-to-a-random-32-byte-base64-secret`) und Admin-Passwort (`admin`). `models.json` speichert API-Keys optional im Home-Verzeichnis, aber `llm_service.py` lädt sie aus `~/.pi/agent/models.json` ohne Berechtigungsprüfung.

### Belege im Code

- `backend/.env.example` Zeile 28–31: JWT_SECRET, ADMIN_USER, ADMIN_PASSWORD.
- `backend/app/services/llm_service.py` Zeile 24–43: API-Key aus `~/.pi/agent/models.json`.

### Anforderung (was gemacht werden muss)

- `.env.example` darf keine realen Defaults für Secrets enthalten, nur Platzhalter wie `JWT_SECRET=__CHANGE_ME__`.
- `JWT_SECRET` muss beim Start auf Mindestlänge (z. B. 32 Bytes) und Entropie geprüft werden.
- `ADMIN_PASSWORD` muss beim ersten Start gehasht und nicht mehr im Klartext gespeichert werden.
- API-Keys dürfen nicht in `models.json` liegen, sondern in `.env` oder einem Secret-Manager.
- `llm_service.py` liest API-Keys nur aus Umgebungsvariablen oder einem Secret-Manager.
- Berechtigungen von Konfigurationsdateien prüfen (nur Owner readable).

### Erwartetes Ergebnis

- Keine Secrets im Repository.
- App startet nicht, wenn `JWT_SECRET` unsicher ist.
- API-Keys sind nicht mehr in der `models.json` sichtbar.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `git grep -i "change-me\|admin\|password" backend/.env.example` liefert keine Treffer außer Platzhaltern.
- Start mit `JWT_SECRET=short` bricht mit klarer Fehlermeldung ab.
- `models.json` enthält kein `apiKey`-Feld mehr.
- `pytest` prüft, dass Secrets nicht im Code oder in Defaults auftauchen.

---

## Finding 6 — Automatische Tabellenerstellung in Produktion

### Problem

`init_db()` in `backend/app/db/base.py` ruft `Base.metadata.create_all()` beim App-Start auf. Das ist für die Entwicklung bequem, in Produktion gefährlich: Es kann Tabellen/Spalten hinzufügen oder im schlimmsten Fall inkonsistente Zustände erzeugen, ohne Migration. Außerdem importiert `init_db` nicht alle Modelle.

### Belege im Code

- `backend/app/db/base.py` Zeile 52–61: `init_db()` mit `Base.metadata.create_all`.
- `backend/app/main.py` Zeile 56: `init_db()` wird im Lifespan aufgerufen.

### Anforderung (was gemacht werden muss)

- `init_db()` darf `Base.metadata.create_all()` nur bei `ENV=development` aufrufen.
- In Produktion (`ENV=production`) wird `create_all` nicht ausgeführt.
- Stattdessen muss `alembic upgrade head` vor dem Start laufen.
- Alle Modelle müssen in Alembic-Migrationen abgedeckt sein.
- `init_db()` importiert alle Modelle konsistent oder verwendet ein zentrales Registry-Pattern.

### Erwartetes Ergebnis

- Produktionsstart erstellt keine Tabellen automatisch.
- Datenbankschema wird ausschließlich über versionierte Migrationen verwaltet.
- Kein Datenverlust oder inkonsistentes Schema durch automatische `create_all`.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `ENV=production` startet die App auch dann, wenn Tabellen fehlen — mit klarer Fehlermeldung.
- `ENV=development` ruft weiterhin `create_all` auf.
- `alembic upgrade head` bringt eine leere Datenbank auf den aktuellen Stand.
- `pytest` prüft, dass `init_db()` in Produktion kein `create_all` aufruft.

---

## Finding 7 — Kein Rate-Limiting, zu permissive CORS, fehlende Timeouts

### Problem

Rate-Limiting ist default deaktiviert (`RATE_LIMIT_PER_MINUTE=0`). CORS erlaubt `localhost:5173` und `localhost:5181`, was in Produktion nicht geeignet ist. Die SSE-Events und LLM-Endpoints können zu Ressourcen-Exhaustion führen.

### Belege im Code

- `backend/app/config.py` Zeile 89: `RATE_LIMIT_PER_MINUTE: int = 0`.
- Zeile 78–82: CORS_ORIGINS enthält localhost-URLs.
- `backend/app/main.py` Zeile 127–140: Rate-Limiting nur optional und mit `slowapi`.

### Anforderung (was gemacht werden muss)

- `RATE_LIMIT_PER_MINUTE` bekommt einen sinnvollen Default (z. B. `120`).
- Rate-Limiting für alle API-Endpoints aktivieren (außer explizit freigegebene wie `/api/health`).
- CORS-Origins in `.env` konfigurierbar machen, in Produktion default leer/strikt.
- SSE-Connections pro Client-IP begrenzen (z. B. max. 5 pro IP).
- Globale Request-Timeouts für LLM-Endpoints (bereits teilweise vorhanden, konsistent machen).

### Erwartetes Ergebnis

- API ist gegen Brute-Force und Denial-of-Service geschützt.
- CORS blockiert Anfragen von nicht erlaubten Domains.
- SSE-Verbindungen können nicht das System überlasten.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- Mehr als 120 Requests/Minute von derselben IP liefern `429 Too Many Requests`.
- `curl -H "Origin: https://evil.com" http://127.0.0.1:9220/api/...` liefert CORS-Fehler.
- `pytest` simuliert 10 gleichzeitige SSE-Verbindungen und prüft, dass nur 5 erlaubt sind.
- `slowapi` ist in `requirements.txt` enthalten und in `main.py` standardmäßig aktiviert.

---

## Finding 8 — Keine automatisierten Tests

### Problem

Es gibt keine eigenen Unit-Tests oder Integrationstests im Projekt. Die einzigen gefundenen Testdateien gehören zu installierten Abhängigkeiten in `.venv`. Bei einem so komplexen System (SOP-Engine, Worker-Loop, Sub-Agenten) ist das ein hohes Risiko für Regressionen.

### Belege im Code

- Keine `test_*.py` oder `*_test.py` in `backend/` außerhalb von `.venv`.
- Keine `*.test.ts/tsx` in `frontend/src/`.
- `.gitignore` ignoriert zwar Test-Coverage-Ordner, aber es existieren keine.

### Anforderung (was gemacht werden muss)

- Testordner `backend/tests/` anlegen mit Unterordnern `unit/`, `integration/`, `fixtures/`.
- Unit-Tests für `TaskService`, `SOPEngine`, `pricing_service`, `llm_service` (Mock).
- Integrationstests für alle Router mit In-Memory-SQLite (`sqlite:///:memory:`).
- Frontend-Tests mit `vitest` und `@testing-library/react`.
- Code-Coverage-Tool (`pytest-cov`) einrichten.
- CI-Pipeline (GitHub Actions oder GitLab CI) erstellen, die Tests bei jedem Push ausführt.

### Erwartetes Ergebnis

- Jeder wichtige Code-Pfad ist durch Tests abgedeckt.
- Änderungen können ohne manuelles Testen validiert werden.
- CI blockiert Pull-Requests bei fehlgeschlagenen Tests.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `cd backend && pytest` läuft erfolgreich durch.
- Testabdeckung liegt über 70 % (`pytest --cov`).
- `cd frontend && npm test` läuft erfolgreich durch.
- CI-Status-Badge im `README.md` ist grün.

---

## Finding 9 — Frontend verwendet `any` überall und hat keine Input-Sanitierung

### Problem

`frontend/src/api.ts` nutzt durchgehend `any` für Request/Response-Typen. Es gibt keine zentrale Fehlerbehandlung, keine Retry-Strategie mit Exponential Backoff, keine XSS-Schutzmaßnahmen. Benutzereingaben (Task-Titel, Description, SOP-Steps) werden ohne Sanitizing an das Backend gesendet und teilweise als Markdown gerendert.

### Belege im Code

- `frontend/src/api.ts` Zeile 4, 33–38: `request<T>` und API-Methoden mit `any`.
- Zeile 33–421: Keine generischen Typen, keine Response-Validierung.
- `frontend/src/App.tsx`: Kein Error Boundary.

### Anforderung (was gemacht werden muss)

- In `frontend/src/api.ts` alle `any`-Typen durch konkrete TypeScript-Interfaces ersetzen.
- API-Response-Typen zentral definieren (z. B. `types/api.ts`).
- React Error Boundary um die App legen.
- DOMPurify für gerendertes Markdown/HTML verwenden.
- Zentrale Fehlerbehandlung mit Retry-Strategie (Exponential Backoff).
- `tsc --noEmit` im Build-Prozess erzwingen.

### Erwartetes Ergebnis

- Frontend ist typsicher und validiert API-Daten.
- XSS durch benutzerdefinierte Inhalte ist nicht mehr möglich.
- Runtime-Fehler werden abgefangen und dem Nutzer angezeigt.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `grep -r "any" frontend/src/api.ts` liefert keine Treffer mehr.
- `npm run build` (bzw. `tsc --noEmit`) läuft ohne TypeScript-Fehler.
- `npm test` enthält Tests für XSS-Versuche in Task-Description.
- Die App zeigt bei einem API-Fehler eine freundliche Fehlermeldung statt weißer Seite.

---

## Finding 10 — Duplizierte Abhängigkeiten, Build-Artefakte im Repo, hartkodierte Pfade

### Problem

`requirements.txt` enthält `sse-starlette==2.1.3` doppelt. `frontend/dist/` ist Teil des Repos (obwohl `.gitignore` `dist/` ignoriert). Es gibt hartkodierte Pfade wie `C:/Users/uwean/.pi/agent/...` im Code. Der Frontend-Port 5181 bleibt häufig blockiert, weil Prozesse nicht sauber beendet werden.

### Belege im Code

- `backend/requirements.txt` Zeile 14–15: `sse-starlette` doppelt.
- `backend/app/services/sub_agent.py` Zeile 52: `C:/Users/uwean/.pi/agent/extensions/swarm-spawner/spawn.sh`.
- `frontend/dist/index.html` existiert im Repo.
- `backend/app/config.py` Zeile 56: `PI_AGENT_DIR` default aus `~/.pi/agent`.

### Anforderung (was gemacht werden muss)

- `backend/requirements.txt` bereinigen: doppelte Einträge entfernen, Versionen konsistent prüfen.
- Optional `requirements-dev.txt` und `requirements.txt` trennen.
- `frontend/dist/` aus dem Git-Repository entfernen und `.gitignore` prüfen.
- Alle hartkodierten Pfade (`C:/Users/uwean/.pi/agent/...`) durch `.env`-Konfiguration ersetzen.
- Graceful Shutdown für Backend und Frontend implementieren, damit Ports sauber freigegeben werden.
- Prozess-Management verbessern: PID-Dateien oder bessere Signal-Handler.

### Erwartetes Ergebnis

- Repository enthält keine generierten Build-Artefakte.
- Abhängigkeiten sind eindeutig und konsistent.
- Die App ist auf jedem Rechner ohne Code-Änderungen lauffähig.
- Ports werden nach Beenden der App zuverlässig freigegeben.

### Nachweis (woran man erkennt, dass es gut umgesetzt wurde)

- `git ls-files | grep "frontend/dist"` liefert keine Treffer.
- `pip install -r backend/requirements.txt` läuft ohne Warnungen zu doppelten Paketen.
- `grep -r "uwean" backend/app/` liefert keine Treffer mehr.
- Nach `Strg+C` auf dem Dev-Server ist Port 5181 innerhalb von 5 Sekunden frei (`netstat` zeigt nichts mehr).
- `npm run build` erzeugt `dist/` neu, wird aber nicht committed.

---

## Empfohlene Umsetzungsreihenfolge

| Phase | Findings | Begründung |
|---|---|---|
| **Sofort** | 1, 5 | Sicherheitsrisiken schließen, bevor die App öffentlich erreichbar ist |
| **Kurzfristig** | 2, 3, 4 | RCE-Pfade und Eingabevalidierung absichern |
| **Mittelfristig** | 6, 7, 8 | Produktionsreife und Testabdeckung verbessern |
| **Langfristig** | 9, 10 | Frontend-Qualität und Wartbarkeit erhöhen |

---

*Dokument erstellt von Kimi Code CLI am 20.06.2026.*
