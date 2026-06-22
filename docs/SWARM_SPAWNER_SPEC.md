# Swarm-Spawner Spec — Staged Hybrid Multi-Agent System

> **Version:** 1.0
> **Datum:** 2026-06-22
> **Autor:** KI-Agent
> **Ziel:** Vollautomatischer Prozess von TRIAGE bis DONE + EVALUATION mit höchster Qualität durch Multi-Agent-Swarm

## 1. Übersicht

### 1.1 Vision

Der **Swarm-Spawner** orchestriert mehrere SubAgents parallel oder kompetitiv, um Tasks in höchster Qualität vollautomatisch zu lösen. Statt ein einzelner Agent arbeitet ein **Schwarm** mit verschiedenen Perspektiven und Ansätzen — das beste Ergebnis wird ausgewählt.

### 1.2 Architektur-Prinzipien

| Prinzip | Umsetzung |
|---|---|
| **Staged** | Verschiedene Swarm-Typen pro Stage (parallel/competitive) |
| **Cost-controlled** | Hard-Limits pro Stage + Global Rate-Limit |
| **Self-improving** | Stage 6 captured Learnings in OpenBrain |
| **Auto-recovery** | Bei Score < 90: Auto-Fix-Loop (max 3 Iterationen) |
| **Observable** | SSE-Events + Telemetry für jede Worker-Aktion |

### 1.3 Swarm-Typen

| Typ | Workers | Merge | Wann nutzen |
|---|---|---|---|
| **single** | 1 | n/a | Triage, Planning, Final Approval |
| **parallel** | 2-5 | `reviewer_picks_best` oder `merge_all` | Implementation, Tests |
| **competitive** | 2-3 | `consensus_score` | Review, Architektur-Entscheidungen |

## 2. SOP-Redesign

Aktuelle SOP `7c86692be939` (6 Steps) wird ersetzt durch **8 Steps + Swarm-Configs**:

```
#0  CIO Triage Review            [single]   cost: $0.05
#1  Lead Planning                [single]   cost: $0.10
#2  Swarm Implementation         [parallel] cost: $0.50  (3× pi-coder)
#3  Multi-Test                   [parallel] cost: $0.30  (3× pi-tester)
#4  Competitive Review           [competitive] cost: $0.20 (3× reviewer)
#5  Auto-Fix (Loop)              [single]   cost: $0.30
#6  Final Approval               [single]   cost: $0.05
#7  Self-Evaluation              [single]   cost: $0.05
─────────────────────────────────────────────────
TOTAL                                           $1.55/Task
```

## 3. Datenmodell

### 3.1 Neue Tabelle `swarm_runs`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | VARCHAR(32) PK | Eindeutige Run-ID |
| `task_id` | VARCHAR(32) FK | Referenz auf tasks.id |
| `sop_instance_id` | VARCHAR(32) FK | SOP-Instance, die den Swarm gestartet hat |
| `step_id` | VARCHAR(32) FK | SOP-Step, der den Swarm ausgelöst hat |
| `swarm_type` | VARCHAR(32) | single / parallel / competitive |
| `workers_config` | JSON | Konfiguration der Worker |
| `status` | VARCHAR(32) | pending / running / completed / failed |
| `merge_strategy` | VARCHAR(32) | reviewer_picks_best / merge_all / consensus_score |
| `consensus_threshold` | FLOAT | Score-Schwelle für Auto-Approve (default 75) |
| `auto_approve_threshold` | FLOAT | Score-Schwelle für Auto-Approve (default 90) |
| `result` | JSON | Ergebnis des Swarms (best_output, score, etc.) |
| `total_cost_usd` | FLOAT | Tatsächliche Kosten |
| `started_at` | DATETIME | |
| `completed_at` | DATETIME | |

### 3.2 Neue Tabelle `swarm_workers`

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | VARCHAR(32) PK | Worker-ID |
| `swarm_run_id` | VARCHAR(32) FK | Referenz auf swarm_runs.id |
| `subagent_role` | VARCHAR(64) | z.B. `pi-coder`, `pi-tester` |
| `variant` | VARCHAR(64) | z.B. `minimalist`, `robust`, `performant` |
| `weight` | FLOAT | Gewichtung für Konsens (default 1.0) |
| `status` | VARCHAR(32) | pending / running / completed / failed |
| `output` | JSON | Output des Workers |
| `cost_usd` | FLOAT | Kosten dieses Workers |
| `score` | FLOAT | Bewertung des Outputs (0-100, durch Reviewer) |
| `started_at` | DATETIME | |
| `completed_at` | DATETIME | |

## 4. SubAgent-Rollen (NEU)

| Rolle | Provider | Model | Aufgabe |
|---|---|---|---|
| `pi-architect` | ollama | gemma4:12b | Stage 1: Task-Decomposition |
| `pi-coder-lead` | minimax-direct | minimax-m3 | Stage 2: Swarm-Lead für Implementation |
| `pi-test-lead` | minimax-direct | minimax-m3 | Stage 3: Swarm-Lead für Tests |
| `pi-review-lead` | minimax-direct | minimax-m3 | Stage 4: Swarm-Lead für Review |

## 5. API

### 5.1 POST `/api/swarm/spawn`

Startet einen neuen Swarm.

**Request:**
```json
{
  "task_id": "string",
  "sop_instance_id": "string",
  "step_id": "string",
  "swarm_type": "parallel",
  "workers": [
    {"role": "pi-coder", "variant": "minimalist", "weight": 1.0},
    {"role": "pi-coder", "variant": "robust", "weight": 1.0},
    {"role": "pi-coder", "variant": "performant", "weight": 1.0}
  ],
  "merge_strategy": "reviewer_picks_best",
  "consensus_threshold": 75,
  "auto_approve_threshold": 90,
  "max_cost_usd": 0.50
}
```

**Response:**
```json
{
  "swarm_run_id": "string",
  "status": "running",
  "workers_count": 3
}
```

### 5.2 GET `/api/swarm/runs/{id}`

Liefert aktuellen Status eines Swarms.

### 5.3 POST `/api/swarm/runs/{id}/merge`

Triggert das Merging der Worker-Outputs.

## 6. SSE-Events

| Event | Wann | Payload |
|---|---|---|
| `swarm_started` | Swarm gestartet | `{swarm_run_id, task_id, workers_count}` |
| `swarm_worker_started` | Worker startet | `{swarm_run_id, worker_id, role, variant}` |
| `swarm_worker_completed` | Worker fertig | `{swarm_run_id, worker_id, output, cost_usd}` |
| `swarm_worker_failed` | Worker fehlgeschlagen | `{swarm_run_id, worker_id, error}` |
| `swarm_merge_started` | Merge beginnt | `{swarm_run_id, strategy}` |
| `swarm_completed` | Swarm fertig | `{swarm_run_id, result, score, total_cost_usd}` |
| `swarm_failed` | Swarm fehlgeschlagen | `{swarm_run_id, error, total_cost_usd}` |

## 7. Auto-Fix-Loop

```
Stage 4 (Review) Score < 90
        ↓
   Spawn pi-fixer mit allen Reviewer-Issues
        ↓
   pi-fixer implementiert Fixes
        ↓
   Zurück zu Stage 3 (Multi-Test)
        ↓
   Iteration-Counter + 1
        ↓
   Counter >= 3? → Eskalation an User (Status = warten)
```

## 8. KANBAN-Erweiterung

Neue Sub-States für `in_progress`:
- `swarm_implementing` — Stage 2 läuft
- `swarm_testing` — Stage 3 läuft
- `swarm_reviewing` — Stage 4 läuft
- `swarm_fixing` — Stage 5 (Auto-Fix-Loop) läuft

Anzeige im Detail-Panel: **Swarm-Status-Card** mit allen Workern und Fortschrittsbalken.

## 9. Cost-Control

### 9.1 Per-Task-Limits (Hard)

| Stage | Limit |
|---|---|
| #0 Triage | $0.05 |
| #1 Planning | $0.10 |
| #2 Implementation | $0.50 |
| #3 Testing | $0.30 |
| #4 Review | $0.20 |
| #5 Fix | $0.30 |
| #6 Final | $0.05 |
| #7 Evaluation | $0.05 |
| **Total** | **$1.55** |

### 9.2 Global Rate-Limit

- $5.00/Stunde über alle laufenden Swarms
- Soft-Warning bei 80%, Hard-Stop bei 100%

## 10. Phasen-Plan

| # | Phase | Status |
|---|---|---|
| 0 | Spec | ✅ |
| 1 | SubAgent-Rollen | 🔄 |
| 2 | SwarmSpawner-Klasse | 🔄 |
| 3 | SOP-Redesign | 🔄 |
| 4 | Merge/Consensus | ⏳ |
| 5 | Auto-Fix-Loop | ⏳ |
| 6 | KANBAN-Erweiterung | ⏳ |
| 7 | Metriken | ⏳ |
| 8 | Cost-Guard | ⏳ |
| 9 | Tests | ⏳ |
| 10 | Eval | ⏳ |

## 11. Beispiel: Performance-Tabelle-Task

```
14:08  Stage 0: CIO Triage → OK (keine Konflikte)
14:09  Stage 1: Lead Planning → 3 Sub-Tasks definiert
14:10  Stage 2: 3 pi-coder parallel
        ├─ minimalist: 234 tokens, $0.04
        ├─ robust:     412 tokens, $0.07
        └─ performant: 367 tokens, $0.06
14:12  Stage 2 Merge: reviewer_picks_best → robust (Score 87)
14:13  Stage 3: 3 pi-tester parallel
        ├─ unit:        Coverage 92% ✅
        ├─ integration: 8/8 Tests ✅
        └─ performance: 142ms p95 ✅
14:14  Stage 4: 3 Reviewer parallel
        ├─ code-quality: 88/100
        ├─ bug-finding:  91/100
        └─ robustness:   86/100
        Konsens-Score: 88.3 (≥ 90 → Auto-Approve? NEIN, < 90)
14:14  Stage 5: Auto-Fix mit 3 Reviewer-Issues
14:15  Stage 3 (Re-Run): Tests ✅
14:16  Stage 4 (Re-Run): Score 92.7 ✅
14:16  Stage 6: Final Approval → done
14:16  Stage 7: Self-Evaluation → OpenBrain-Capture
TOTAL COST: $0.91
TOTAL TIME: 8 Minuten (vs. vorher: manuell oft >30 Min)
```