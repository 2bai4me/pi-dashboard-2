// kanban.ts — Single Source of Truth fuer Kanban-Phasen (Projekt/Board)
//
// User-Direktive 22.06.2026: 'Die Phasen sollen die Phasen aus dem KANBAN sein.
// Projekt/Board'. Diese Konstanten werden sowohl vom Kanban-Board selbst
// als auch vom SOP-Step-Editor verwendet, damit es nur eine Quelle gibt.
//
// Achtung bei Aenderung: Wenn ein neuer Status im Backend ergaenzt wird
// (siehe backend/app/models/task.py:89 -> status), muss diese Liste
// aktualisiert werden UND eine Migration fuer bestehende Tasks erfolgen.

export interface KanbanPhase {
  /** Datenbank-Key (z.B. fuer API-Filter, task.status) */
  key: string
  /** Anzeige-Label in der UI (lokalisiert) */
  label: string
  /** Beschreibung fuer Tooltips */
  description?: string
}

export const KANBAN_PHASES: readonly KanbanPhase[] = [
  { key: "triage",       label: "Triage",      description: "Neue Tasks werden hier angelegt und vom CIO geprueft" },
  { key: "go",           label: "GO",          description: "Task ist freigegeben und bereit zur Bearbeitung" },
  { key: "in_progress",  label: "In Progress", description: "Task wird aktuell von einem Worker bearbeitet" },
  { key: "review",       label: "Review",      description: "Task wartet auf Code- oder Inhalts-Review" },
  { key: "rueckfrage",   label: "Rückfrage",   description: "Rueckfrage blockiert den Workflow bis zur Klaerung" },
  { key: "warten",       label: "Warten",      description: "Task wartet auf externe Bedingung (User, Timer, Service)" },
  { key: "done",         label: "Done",        description: "Task ist erfolgreich abgeschlossen" },
] as const

/** Type-Guard: ist `value` eine gueltige Kanban-Phase (nach key)? */
export function isKanbanPhase(value: string): boolean {
  return KANBAN_PHASES.some((p) => p.key === value)
}

/** Lookup: findet die Phase zu einem Key. Fallback: synthetische Phase. */
export function findKanbanPhase(key: string): KanbanPhase {
  return (
    KANBAN_PHASES.find((p) => p.key === key) || {
      key,
      label: key,
      description: "Unbekannte Phase — Wert stammt vermutlich aus einer aelteren Version",
    }
  )
}