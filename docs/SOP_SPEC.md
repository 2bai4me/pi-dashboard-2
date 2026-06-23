# SOP-Specifikation — Stand 23.06.2026

> **Version:** 2.0 (Multi-Agent-Swarm mit Decomposition + Port-Management)
> **Datum:** 2026-06-23
> **Autor:** KI-Agent

---

## 1. Übersicht

Das **PI-Dashboard 2.0 Standard-Workflow Development** SOP durchläuft **9 Phasen** mit folgenden Features:

- **Multi-Agent-Swarm** (3 Swarm-Typen)
- **Task-Decomposition** (Phase Go — User-Direktive 23.06.2026)
- **Port-Management** (OpenBrain-konform — User-Direktive 23.06.2026)
- **Auto-Fix-Loop** (bei Score < 90)
- **SSE-Live-Updates**

---

## 2. Die 9 SOP-Phasen

| # | Phase | Status | Agent | Action | Cost | Besonderheit |
|---|---|---|---|---|---|---|
| 0 | **Triage** | `triage` | CIO | `review_task` | $0.05 | **Decompose-Check** (User-Direktive 23.06.2026) |
| 1 | **Lead Planning** | `go` | pi-architect | `llm_call` | $0.10 | |
| 1.5 | **Decompose** (optional) | `go` (Parent) | CIO | `decompose_task` | $0 | Subtasks werden erstellt, Parent bleibt in `go` |
| 2 | **Swarm Implementation** | `in_progress` | pi-coder-lead | `spawn_swarm` | $0.50 | Parallel (3× pi-coder), **Port-Reservation** |
| 3 | **Multi-Test** | `review` | pi-test-lead | `spawn_swarm` | $0.30 | Parallel (3× pi-tester) |
| 4 | **Competitive Review** | `review` | pi-review-lead | `spawn_swarm` | $0.20 | Konsens-Score, Auto-Approve ≥90 |
| 5 | **Auto-Fix** (loop) | `in_progress` | pi-fixer | `llm_call` | $0.30 | Bei Score < 90, max 3 Iter. |
| 6 | **Final Approval** | `block` | CIO | `cio_final_review` | $0.05 | |
| 7 | **Self-Evaluation** | `done` | CIO | `evaluate_outcome` | $0.05 | Konsolidierung + **Port-Release** |

**Total: $1.55/Task**

---

## 3. Phase-Detail

### Phase 0: Triage (CIO)
- **Action:** `review_task`
- **Was passiert:**
  1. CIO-Heuristik prüft 4 Kriterien
  2. **Decompose-Check** (User-Direktive 23.06.2026):
     - Heuristik analysiert Titel + Description
     - Erkennt Themen-Marker (frontend, backend, tests, deployment, ...)
     - Wenn ≥2 Themen + Description ≥100 Zeichen + mehrere Sätze → **Split empfohlen**
- **Output:** `ok: true/false`, `decomposition: {decomposed, subtask_count, themes}`
- **Status-Übergang:** `triage → in_progress` (Bugfix 23.06.2026)

### Phase 1: Lead Planning (pi-architect)
- **Action:** `llm_call`
- **Was passiert:**
  - Architektur-Plan wird erstellt
  - Sub-Tasks und Akzeptanzkriterien werden definiert
- **Output:** Plan + AI-Instructions

### Phase 1.5: Decompose (optional, bei mehrteiligen Tasks)
- **Action:** `decompose_task`
- **Was passiert** (automatisch bei Phase 0 erkannt):
  1. Subtasks werden in DB erstellt (mit `parent_id`)
  2. **Parent-Task bleibt in `go`** (User-Direktive 23.06.2026)
  3. Subtasks erhalten `status=triage` und durchlaufen eigene SOP-Pipeline
  4. Jeder Subtask hat eigene Planung in `task.meta.plan`
- **Wann greift:** Wenn `review_task` `should_decompose=True` zurückgibt
- **Beispiel:** Login-System mit Frontend + Backend + Tests + Deployment → 4 Subtasks

### Phase 2: Swarm Implementation (pi-coder-lead)
- **Action:** `spawn_swarm`
- **Was passiert:**
  1. **Port-Reservation** (User-Direktive 23.06.2026, Task 4bf7146b0780):
     - Sucht freien 10er-Block für `pi-dashboard-2`
     - Reserviert via `port_manager.reserve_block()`
     - Speichert Block-ID in `task.meta.port_allocations`
  2. Startet 3 parallele pi-coder (minimalist / robust / performant)
- **Merge:** `reviewer_picks_best` (Mock: erstes Worker-Output)
- **Status-Übergang:** `go → in_progress`

### Phase 3: Multi-Test (pi-test-lead)
- **Action:** `spawn_swarm`
- **Was passiert:** 3 parallele pi-tester (unit / integration / performance)
- **Merge:** `merge_all` (alle Outputs kombinieren)

### Phase 4: Competitive Review (pi-review-lead)
- **Action:** `spawn_swarm`
- **Was passiert:** 3 kompetitive Reviewer (quality / bugs / robustness)
- **Merge:** `consensus_score` (gewichteter Durchschnitt)
- **Schwellen:**
  - `consensus_threshold = 75` (Bestanden)
  - `auto_approve_threshold = 90` (Auto-Approve ohne CIO)
- **Bei Score < 90:** Auto-Fix-Loop wird getriggert

### Phase 5: Auto-Fix (loop, pi-fixer)
- **Action:** `llm_call`
- **Was passiert:**
  - Bei Score < 90: pi-fixer implementiert die Reviewer-Issues
  - Zurück zu Phase 3 (Multi-Test)
  - Max 3 Iterationen
- **Status-Übergang:** `review → in_progress`

### Phase 6: Final Approval (CIO)
- **Action:** `cio_final_review`
- **Was passiert:**
  - Prüft Acceptance-Criteria + Consensus-Score
  - Bei `consensus_score ≥ 90` → Auto-Approve
  - Sonst: Eskalation an User

### Phase 7: Self-Evaluation (CIO)
- **Action:** `evaluate_outcome`
- **Was passiert:**
  1. **Konsolidierung** aller Swarm-Outputs in `task.meta.swarm_consolidated`
  2. **Port-Release** (User-Direktive 23.06.2026):
     - Alle für diese Task reservierten Port-Blöcke werden freigegeben
     - `port_manager.release_block()`
  3. OpenBrain-Capture für Lern-Insights
  4. **Status-Übergang:** → `done`

---

## 4. Sub-Task-Tracking (Phase 1.5 + Auto-Complete-Parent)

### Wenn Decompose ausgelöst wird:

```
Haupttask (z.B. Login-System)
├── Status: go (bleibt während Subtasks laufen)
├── Plan in task.meta (vom pi-architect)
└── Subtasks (jeder eigene SOP-Pipeline):
    ├── Subtask 1: Frontend-Teil
    │   ├── Status: triage → in_progress → review → done
    │   ├── Eigene Planung (task.meta.plan.steps)
    │   ├── Eigene Session-ID
    │   ├── Eigene TokenUsage (mit parent_task_id)
    │   └── Eigenes Port-Allocation
    ├── Subtask 2: Backend-Teil (analog)
    ├── Subtask 3: Tests-Teil (analog)
    └── Subtask 4: Deployment-Teil (analog)
```

### Auto-Complete-Parent:
- Wenn **alle Subtasks** den Status `done` erreicht haben
- Und **Consensus-Score ≥ 90** für jeden Subtask
- → Haupttask wird automatisch auf `done` gesetzt

---

## 5. Port-Management (OpenBrain-konform)

### Port-Allokations-Tabelle

| App | Port-Range | Status |
|---|---|---|
| pi-dashboard-2 | 9220-9229 | active |
| pi-dashboard-2 | 9230-9239 | active (Erweiterung) |
| openbrain | 9300-9309 | active |
| smproducer | 9400-9409 | active |
| youtube-analyzer | 9500-9509 | active |
| generic | 10000-10009 | active (Reserve) |

### API-Endpoints

| Method | Pfad | Zweck |
|---|---|---|
| POST | `/api/ports/check` | Prüfen ob Block frei ist (ohne Reservierung) |
| POST | `/api/ports/reserve` | Neuen Block reservieren |
| POST | `/api/ports/{id}/release` | Block freigeben |
| GET | `/api/ports` | Liste aller Allokationen |
| GET | `/api/ports/by-task/{task_id}` | Blöcke eines Tasks |

### Port-Lifecycle

```
1. Subagent-Spawn startet
2. reserve_block(app_name, task_id, count=10) → block_id
3. Port-Info in task.meta.port_allocations ablegen
4. ... Task läuft ...
5. Task-Completion (Phase 7)
6. release_block(block_id) → Port wieder verfügbar
```

---

## 6. Auto-Fix-Loop (Phase 5)

```
Phase 4: Competitive Review
   ↓ Score < 90
Phase 5: Auto-Fix (pi-fixer implementiert Issues)
   ↓
Phase 3 (RE-RUN): Multi-Test Swarm
   ↓
Phase 4 (RE-RUN): Competitive Review
   ↓ Score >= 90 oder iteration_count >= 3
Phase 6: Final Approval
```

**Iteration-Counter** wird in `task.meta.swarm_iteration_count` gespeichert.
Bei `iteration_count >= 3` und Score < 90 → **Eskalation an User**.

---

## 7. Kosten-Übersicht

| Phase | Kosten |
|---|---|
| 0 Triage | $0.05 |
| 1 Lead Planning | $0.10 |
| 2 Implementation | $0.50 |
| 3 Multi-Test | $0.30 |
| 4 Competitive Review | $0.20 |
| 5 Auto-Fix | $0.30 |
| 6 Final Approval | $0.05 |
| 7 Self-Evaluation | $0.05 |
| **Total** | **$1.55** |

**Global Rate-Limit:** $5/Stunde (alle Swarms kombiniert)

---

## 8. Status-Übergänge

```
triage ─┐
        ├── (Decompose) → Subtasks erstellen, Parent bleibt in go
        ↓
        go (Planung + Decompose)
        ↓
        in_progress (Implementation + Tests)
        ↓
        review (Tests + Review)
        ↓
        block (Final Approval)
        ↓
        done (Self-Evaluation)
```

**Subtasks** durchlaufen denselben Flow, aber **getrennt** vom Parent.

**Parent bleibt in `go`** bis alle Subtasks `done` sind.

---

## 9. Frontend-Integration

| Anzeige | Wo |
|---|---|
| Sub-Task-Count, Cost-Badge, Token-Badge | TaskDetailPanel (PlanungSection) |
| Sub-Task-Details (Plan, Agent, Session-ID) | PlanningSection-Card |
| Port-Belegungen | Task-Detail (Phase 2) |
| Swarm-Worker-Progress | SwarmStatusCard |
| Live-Updates | SSE `/api/swarms/{id}/events` |

---

## 10. Versionen

| Version | Datum | Änderungen |
|---|---|---|
| 2.0 | 23.06.2026 | Phase 1.5 (Decompose), Port-Management, Auto-Fix-Loop, SSE |
| 1.0 | 22.06.2026 | Multi-Agent-Swarm Phase 0-2 |