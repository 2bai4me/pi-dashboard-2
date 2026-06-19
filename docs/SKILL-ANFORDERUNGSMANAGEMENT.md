# Skill: Anforderungsmanagement

> **Status:** 📘 Pflicht-Skill für alle Agenten
> **Quelle:** User-Direktive 17.06.2026 (Prio 100)
> **OpenBrain-ID:** `b112ab54-488e-461f-8c92-17062bf06aa0`
> **Gültig für:** PI-Dashboard 2.0, alle Sub-Agenten, alle Sessions

---

## 🎯 Zweck

Dieser Skill definiert die **unverletzlichen Regeln** für die Bearbeitung von Anforderungen im PI-Dashboard. Er stellt sicher, dass:

- **Nichts direkt selbst umgesetzt** wird (immer über das Board)
- **Tasks sofort sichtbar** sind (Cache-Invalidation)
- **Der User informiert** wird (Quittierung)
- **Sub-Agents die Umsetzung** übernehmen (Standard-Workflow)

---

## 📜 Pflicht-Regeln (IMMER einzuhalten)

### 1. IMMER einen Task erstellen
Jede Anforderung, jedes Feature, jeder Bug → wird als Task im PI-Dashboard angelegt. NICHTS direkt selbst umsetzen.

### 2. IMMER minimax M3 als Modell
Standard-Modell: `minimax-direct/minimax-m3` (Cloud).
Für lokale Aufgaben: `ollama/gemma4:12b`.

### 3. IMMER Status "triage"
Neue Tasks starten IMMER in Triage → CIO kann die 4 Pflicht-Prüfungen vornehmen:
1. Task-Typ-Klassifizierung
2. Standardvorgaben-Konformität (OpenBrain)
3. Änderungsbeschreibung
4. Subagent-Readiness

### 4. IMMER Quittigung an User
Direkt nach Task-Erstellung eine Quittung mit:
- Task-ID
- Title
- Status
- Prio
- Projekt

### 5. IMMER durch Sub-Agent umsetzen
Tasks werden NIE im aktuellen Kontext implementiert. Nach Erstellung läuft:
```
triage → todo → in_progress → review → block/rückfrage → done
```
Sub-Agent (pi-coder/-tester/-reviewer/-fixer) übernimmt automatisch.

### 6. Cache-Invalidation sicherstellen
Nach JEDER Änderung muss das Board SOFORT aktualisiert werden — kein manueller Reload.

---

## 🔧 Cache-Invalidation Pattern (WICHTIG)

```jsx
// Nach Task-Mutation IMMER:
qc.invalidateQueries({ queryKey: ["projects"] })      // Project-Liste neu
qc.invalidateQueries({ queryKey: ["tasks", projectId] })  // Task-Liste neu

// Beispiel: Task erstellt
const createMut = useMutation({
  mutationFn: () => api.createProject(data),
  onSuccess: (p: any) => {
    setShowNewProject(false)
    qc.invalidateQueries({ queryKey: ["projects"] })  // ← Pflicht!
    openProject(p.id, "board")
  },
})
```

**Der User muss JEDEN Task SOFORT im Board sehen.**

---

## 📋 Standard-Workflow für Tasks

```
┌──────────┐    ┌──────┐    ┌─────────────┐    ┌────────┐    ┌──────────┐    ┌──────┐
│ TRIAGE   │ →  │ TODO │ →  │ IN_PROGRESS │ →  │ REVIEW │ →  │ RÜCKFRA- │ →  │ DONE │
│  CIO     │    │ CIO  │    │  pi-coder   │    │ pi-test│    │ GE/BLOCK │    │ CIO  │
└──────────┘    └──────┘    └─────────────┘    └────────┘    │   CIO    │    └──────┘
                                                              └──────────┘

   Schritt 0: CIO Triage Review (4 Pruefungen)
   Schritt 1: Worker Assignment (pi-coder)
   Schritt 2: Worker Implementation
   Schritt 3: Tester Code-Review
   Schritt 4: CIO Final-Review
   Schritt 5: Done
```

---

## 📝 Beispiel-Quittung an User

```text
═══════════════════════════════════════════════════════════
  ✅ QUITTIERUNG: Task erstellt
═══════════════════════════════════════════════════════════
  Task-ID:    914609ddfcf4
  Title:      [SKILL] Anforderungsmanagement erstellen
  Status:     triage
  Prio:       100 (NOTFALL)
  Projekt:    PI Dashboard 2
  Worker:     pi-coder (zugewiesen nach Triage)
═══════════════════════════════════════════════════════════
```

---

## 🚫 Was NICHT zu tun ist

- ❌ KEIN direktes Code-Schreiben für Anforderungen
- ❌ KEIN "mache ich schnell selbst"
- ❌ KEINE Tasks überspringen
- ❌ KEINE Tasks ohne Status="triage" anlegen
- ❌ KEINE Tasks ohne Quittung an User
- ❌ KEINE Tasks erstellen OHNE Cache-Invalidation

---

## 🔗 Verwandte Dokumentation

- **OpenBrain-Skill:** ID `b112ab54-488e-461f-8c92-17062bf06aa0` (Tags: skill, anforderungsmanagement)
- **RACI & Workflow:** `docs/RACI-WORKFLOW.md`
- **Standard-Workflow-Task:** SOP `7c86692be939` (6 Schritte)
- **Architektur-Vorgaben:** `architecture_rules`-Tabelle (10 Regeln)
- **Governance-Regeln:** `docs/RACI-WORKFLOW.md#5-governance-regeln`

---

*Dokument erstellt: 17.06.2026 (User-Direktive)*
*Verantwortlich: Owner Andy Amann (Strategie) · CEO-digital (Orchestrierung) · CIO (Umsetzung)*
*Status: PFLICHT für alle Sessions und Sub-Agenten*
