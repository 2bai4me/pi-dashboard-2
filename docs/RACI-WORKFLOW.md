# RACI & Standard-Workflow — Software-Entwicklung

> **Quelle:** Aggregiert aus OpenBrain (16.06.2026)
> **Status:** 📘 Referenz-Dokument
> **Gültig für:** ME4 / PI-Dashboard 2.0 / alle Sub-Projekte der Hermes-Infrastruktur

---

## 1. Hierarchie & Rollen

```
                         Owner (Andy Amann)
                                │
                          CEO-digital 👑
                  Orchestrator — NIE Code-Entwicklung!
                       /      │       \
                    CIO 🏗️  CFO 💰   CMO 📢
                       │  (Triage,     (Budget)   (Marketing)
                  Standards, Workers)
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   pi-coder 💻   pi-tester 🧪   pi-reviewer 👁️
   (Code,         (Tests,         (Code-Review
    Edits)         Bug-Suche)      vor Merge)
        │
   pi-fixer 🔧
   (Bug-Behebung)
```

### Rollen-Detail

| Rolle | Emoji | Provider / Model | Hauptaufgabe | Perspektive |
|---|---|---|---|---|
| **Owner** | — | Mensch | Strategische Entscheidungen, Vision, Budget | Extern |
| **CEO-digital** | 👑 | minimax-m3 | Orchestrierung, NIEMALS Code | Strategisch |
| **CIO** | 🏗️ | ollama/gemma4:12b | Triage, Standards-Check, Worker-Assignment, Final-Review | Taktisch |
| **CFO** | 💰 | ollama/gemma4:12b | Finanzen, Budget-Kontrolle, Cost-Tracking | Taktisch |
| **CMO** | 📢 | ollama/gemma4:12b | Marketing, externe Kommunikation | Taktisch |
| **pi-coder** | 💻 | minimax-m3 | Code schreiben, editieren, implementieren | Operativ |
| **pi-tester** | 🧪 | minimax-m3 | Tests schreiben, Code-Review, Bug-Suche | Operativ |
| **pi-reviewer** | 👁️ | minimax-m3 | Code-Review vor Merge | Operativ |
| **pi-fixer** | 🔧 | minimax-m3 | Bug-Behebung, Refactoring | Operativ |

---

## 2. RACI-Matrix

> **RACI-Prinzip:** Jeder Task hat **GENAU EINEN** Verantwortlichen (R + A in einer Person).
> Keine unklaren Zuständigkeiten. Der Verantwortliche meldet Status und Abschluss.

| Aktivität | Owner | CEO-digital | CIO | pi-coder | pi-tester | OpenBrain |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Strategische Vision | **A** | R | C | — | — | I |
| Neue Anforderung stellen | **A, R** | I | I | — | — | I |
| Task in Triage einreihen | I | A | **R** | I | I | C |
| Task-Typ klassifizieren | I | I | **A, R** | — | — | C |
| Standards-Check (Architektur) | I | I | **A, R** | — | — | C |
| Worker zuweisen | I | A | **R** | I | I | — |
| Code implementieren | I | I | A | **R** | — | — |
| Tests schreiben | I | I | A | C | **R** | — |
| Code-Review | I | I | A | I | **R** | — |
| Final-Review / Freigabe | I | I | **A, R** | I | I | C |
| Status-Reporting | I | I (C-Board) | **A, R** | I | I | I |
| Architektur-Vorgaben | C | C | **A** | I | I | **R** |
| Prozess-Verstoß melden | A | R | **R** | I | I | I |

**Legende:** A = Accountable (Ergebnis-Verantwortung) · R = Responsible (Ausführung) · C = Consulted · I = Informed

---

## 3. Standard-Workflow (SOP "Standard-Workflow Task" v1)

### 3.1 6-Phasen-Flow

```
 ┌──────────┐   ┌──────┐   ┌─────────────┐   ┌────────┐   ┌──────────┐   ┌──────┐
 │ TRIAGE   │ → │ TODO │ → │ IN_PROGRESS │ → │ REVIEW │ → │ RÜCKFRA- │ → │ DONE │
 │  CIO     │   │ CIO  │   │  pi-coder   │   │ pi-test│   │ GE/BLOCK │   │ CIO  │
 └──────────┘   └──────┘   └─────────────┘   └────────┘   │   CIO    │   └──────┘
       │              │              │              │           └──────────┘
       └──────────────┴──────────────┴──────────────┘              │
                    (5s Delay pro Schritt)                          ↓
                                                       Auto-Create
                                                       Freigabe-Task
                                                            │
                                                            ↓
                                                       CIO prüft nochmal
                                                            │
                                                            ↓
                                                          DONE
```

### 3.2 Schritt 0: CIO Triage Review (4 Prüfungen)

Bevor ein Task das Board durchläuft, prüft CIO **vier Pflicht-Punkte**:

#### Prüfung 1: Task-Typ-Klassifizierung

| Typ | Farbe | Bedeutung | Beispiel |
|---|---|---|---|
| `new_request` | 🟢 grün | Komplett neue Anforderung | "Neue API für Auth" |
| `change` | 🔵 blau | Änderung an Bestehendem | "Login-Button-Farbe ändern" |
| `ticket` | 🟠 orange | User meldet was nicht funktioniert | "Suche liefert keine Ergebnisse" |
| `bugfix` | 🔴 rot | Von Agenten gefunden (interner Fehler) | "Memory-Leak im Worker" |

#### Prüfung 2: Standardvorgaben-Konformität (OpenBrain-Prüfung)

CIO prüft die Anforderung gegen **10 Architektur-Regeln** (geseedet aus OpenBrain):

| Regel | Beschreibung | Severity |
|---|---|---|
| `arch-soa` | Service-Oriented Architecture | high |
| `arch-microservices` | Microservices-Architektur (Schema-per-Tenant) | high |
| `arch-fastapi` | Python 3.11+ / FastAPI als Standard | medium |
| `arch-no-nodejs` | KEIN Node.js (Konsistenz mit FastAPI-Ökosystem) | medium |
| `arch-llm-primary` | minimax-m3 als PRIMARY, Ollama als Fallback | high |
| `arch-swarm-roles` | Sub-Agent-Rollen-Set (pi-*, CIO, CEO) | high |
| `arch-cost-tracking` | Token-Budget + Cost-Limit pro Sub-Agent | high |
| `arch-git-branch` | Eigener Git-Branch pro Task (Rollback) | medium |
| `arch-task-locking` | Task-Locking (keine Doppelbearbeitung) | medium |
| `arch-multi-tenant` | Multi-Tenant-Architektur (Schema-per-Tenant) | high |

> ⚠️ **Wichtig:** Falls eine Vorgabe fehlt, MUSS sie in OpenBrain ergänzt werden, BEVOR die Anforderung umgesetzt wird.

#### Prüfung 3: Änderungsbeschreibung (strukturiert)

| Feld | Pflicht? | Beschreibung |
|---|---|---|
| `files` | ✅ required | Liste der zu ändernden Dateien |
| `notes` | ✅ required | Detaillierte Beschreibung der Änderung |
| `routes` | optional | Neue/geänderte API-Routen |
| `api_changes` | optional | Request/Response-Schema-Änderungen |
| `database_changes` | optional | Schema-Migrationen, neue Tabellen |

#### Prüfung 4: Subagent-Readiness (Swarm-Anforderungen)

| Feld | Pflicht? | Beschreibung |
|---|---|---|
| `model` | ✅ required | Provider + Model (z.B. `minimax-m3`) |
| `branch` | ✅ required | Git-Branch für die Implementierung |
| `context_files` | ✅ required | Relevante Dateien für Kontext |
| `success_criteria` | ✅ required | Kriterien, wann der Task als "done" gilt |
| `token_budget` | optional | Maximale Token für LLM-Aufrufe |
| `cost_limit_usd` | optional | Maximale Kosten in USD |
| `tools` | optional | Tool-Whitelist (read, write, bash, etc.) |
| `timeout_s` | optional | Timeout in Sekunden |

**Wenn unvollständig:** BLOCK + Frage an User  
**Wenn OK:** Weiter zu Schritt 1 (Worker Assignment)

### 3.3 Schritte 1-5 im Detail

| # | Status-Übergang | Agent | Aktion |
|---|---|---|---|
| 1 | `triage` → `todo` | **CIO** | Triage-Approve: alle 4 Prüfungen OK |
| 1b | `todo` (Worker zuweisen) | **CIO** | `assign worker=pi-coder` (oder pi-tester/-reviewer/-fixer) |
| 2 | `todo` → `in_progress` | **pi-coder** (auto-claim) | Implementiert auf eigenem Branch, committet |
| 3 | `in_progress` → `review` | **pi-coder** (submit-review) | Implementierung fertig, übergibt an Tester |
| 3b | `review` → `rueckfrage/block` | **pi-tester** (tester-approve) | Bei OK: → BLOCK + Auto-Create `[FREIGABE]`-Sub-Task |
| 3c | `review` → `in_progress` (loop) | **pi-tester** (tester-reject) | Bei Reject: Bugs dokumentieren, zurück zu Worker |
| 4 | `rueckfrage` → `done` | **CIO** (cio-approve) | Final-Review gegen Standards, Freigabe |
| 4b | `rueckfrage` → `in_progress` (loop) | **CIO** (cio-reject) | Bei Reject: zurück zur Korrektur |

**Delay:** 5 Sekunden pro Status-Übergang (User-Transparenz)

---

## 4. Governance-Regeln

| # | Regel | Konsequenz bei Verstoß |
|---|---|---|
| 1 | **CEO(digital) entwickelt NIE selbst Code** — NUR Orchestrierung | SOFORT Complaint-Task + Fix-Task im cio-board |
| 2 | **Alle Entwicklung läuft über KANBAN → CIO → PI-Agenten** | Task wird zurück in Triage geschoben |
| 3 | **JEDER KANBAN-Task MUSS Präfix "BUGFIX:" oder "NEW:" im Titel haben** | Task wird abgelehnt |
| 4 | **Bei Prozessverstoß (Direktentwicklung):** Sofort eskalieren | Keine Ausnahme — auch nicht bei Dringlichkeit |
| 5 | **RACI-Prinzip:** Genau 1 Verantwortlicher pro Task | Klärungs-Aktion, bis Eindeutigkeit herrscht |

### Eskalations-Pfade

- **Architektur-Frage** → CEO-Review (via CEO-digital)
- **Security-Issue** → PI-IT via CIO
- **Finanzen/Budget-Überschreitung** → CFO
- **Prozessverstoß** → SOFORT Complaint-Task im cio-board

---

## 5. DevOps Best Practices (Quick Wins → Strategisch)

### 5.1 Sofort umsetzbar (Quick Wins)

| # | Maßnahme | Aufwand | Effekt |
|---|---|---|---|
| 1 | **Pre-Commit-Hooks** (ruff, eslint, prettier, gitleaks) | 1 Tag | Fängt Fehler Minuten statt Stunden nach dem Schreiben |
| 2 | **Type-Checking in CI/CD** (mypy --strict, tsc --noEmit) | 1 Tag | Pflicht-Gate vor Merge in main |
| 3 | **Structured Error-Logging** mit Business-Kontext (video_id, user_id, service, trace_id) | 2 Tage | Schnellere Debug-Suche |

### 5.2 Mittelfristig (1-2 Wochen)

| # | Maßnahme | Aufwand | Effekt |
|---|---|---|---|
| 4 | **OpenTelemetry Traces** (opentelemetry-instrumentation-flask + express) | 1 Woche | Verteilter Trace über alle Services |
| 5 | **RED-Metriken pro Service** (Rate/Errors/Duration p50/p95/p99) | 1 Woche | Prometheus-Dashboards + Alerting |

### 5.3 Strategisch

| # | Maßnahme | Aufwand | Effekt |
|---|---|---|---|
| 6 | **SLOs + Error-Budget-Alerting** | 2 Wochen | Alert nur bei Budget-Burn, nicht bei Einzelfehlern |
| 7 | **Feature-Flags** | 1 Woche | Neue Endpoints hinter Flags → instant Rollback |
| 8 | **Centralized Error-Tracking (Sentry)** | 3 Tage | Alle Services + Frontend in einem Dashboard |

---

## 6. Goldene Regeln (SRE-Buch)

> 1. **Kürzester Feedback-Loop = Schnellster Bug-Fix**
> 2. **Härte im Git-Workflow** (Pre-Commit + CI-Gates = Fehler nie im main)
> 3. **Sichtbarkeit im Betrieb** (Traces + Dashboards + Alerts)
> 4. **Nur auf Budget-Burn alerten, nie auf Noise**
> 5. **Trace-ID ist das Rückgrat** — ohne sie kein Cross-Service-Debugging

**Quellen:** Google SRE Book, OpenTelemetry Docs, GitLab/Google DevOps State Reports 2024-2025

---

## 7. Cheat-Sheet: Wer macht was?

```
"Was willst du?"
  │
  ├── Neue Funktion bauen     → Task "NEW: ..." → CEO-digital → CIO-Triage → pi-coder
  ├── Bug fixen               → Task "BUGFIX: ..." → CEO-digital → CIO-Triage → pi-fixer
  ├── Etwas funktioniert nicht (User) → Task "TICKET: ..." → CEO-digital → CIO-Triage → pi-tester (diagnose) → pi-fixer (fix)
  ├── Etwas ändern            → Task "CHANGE: ..." → CEO-digital → CIO-Triage → pi-coder
  │
"Was prüft wer?"
  │
  ├── Vor der Bearbeitung:   CIO (Schritt 0: 4 Prüfungen)
  ├── Während der Bearbeitung: pi-coder (-tester, -reviewer) implementiert
  ├── Nach der Bearbeitung:   pi-tester (Code-Review + Tests)
  ├── Vor dem Done:           CIO (Final-Review gegen Standards)
  │
"Was passiert bei Fehlern?"
  │
  ├── Tester findet Bug       → zurück zu pi-coder (Iteration++)
  ├── CIO findet Standard-Verstoß → zurück zu pi-coder (CIO-Reject)
  ├── User meldet Bug         → neuer TICKET-Task → kompletter Loop
  │
"Was passiert bei Prozess-Verstoß?"
  │
  └── JEDER Verstoß → SOFORT Complaint-Task im cio-board
```

---

*Dokument erstellt: 16.06.2026*
*Quelle: OpenBrain bB (Suchdistanz 0.5)*
*Verantwortlich: Owner Andy Amann (Strategie), CEO-digital (Orchestrierung), CIO (Umsetzung)*
