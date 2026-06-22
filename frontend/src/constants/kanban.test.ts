// Tests fuer KANBAN_PHASES — Single Source of Truth der Kanban-Phasen
// User-Direktive 22.06.2026: Phasen aus Kanban/Projekt/Board

import { describe, it, expect } from "vitest"
import { KANBAN_PHASES, isKanbanPhase, findKanbanPhase } from "./kanban"

describe("KANBAN_PHASES", () => {
  it("enthaelt alle 7 erwarteten Standard-Phasen", () => {
    const keys = KANBAN_PHASES.map((p) => p.key)
    expect(keys).toEqual([
      "triage",
      "go",
      "in_progress",
      "review",
      "rueckfrage",
      "warten",
      "done",
    ])
  })

  it("jede Phase hat key, label und description", () => {
    for (const p of KANBAN_PHASES) {
      expect(p.key).toBeTruthy()
      expect(p.label).toBeTruthy()
      expect(p.description).toBeTruthy()
    }
  })

  it("keys sind eindeutig", () => {
    const keys = KANBAN_PHASES.map((p) => p.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it("labels sind eindeutig", () => {
    const labels = KANBAN_PHASES.map((p) => p.label)
    expect(new Set(labels).size).toBe(labels.length)
  })
})

describe("isKanbanPhase", () => {
  it("true fuer gueltige Phase", () => {
    expect(isKanbanPhase("triage")).toBe(true)
    expect(isKanbanPhase("done")).toBe(true)
  })

  it("false fuer unbekannte Phase", () => {
    expect(isKanbanPhase("unknown")).toBe(false)
    expect(isKanbanPhase("")).toBe(false)
  })

  it("false fuer Legacy-Werte (Task, Decision, Sub-SOP, End, Wait, Notification)", () => {
    // Diese Werte waren in der vorherigen Version hartcodiert.
    // Sie sind NICHT mehr in den Kanban-Phasen.
    expect(isKanbanPhase("Task")).toBe(false)
    expect(isKanbanPhase("Decision")).toBe(false)
    expect(isKanbanPhase("Sub-SOP")).toBe(false)
    expect(isKanbanPhase("End")).toBe(false)
    expect(isKanbanPhase("Wait")).toBe(false)
    expect(isKanbanPhase("Notification")).toBe(false)
  })
})

describe("findKanbanPhase", () => {
  it("findet existierende Phase", () => {
    const phase = findKanbanPhase("review")
    expect(phase.key).toBe("review")
    expect(phase.label).toBe("Review")
    expect(phase.description).toBeTruthy()
  })

  it("Fallback fuer unbekannte Phase", () => {
    const phase = findKanbanPhase("legacy-value")
    expect(phase.key).toBe("legacy-value")
    expect(phase.label).toBe("legacy-value")
    expect(phase.description).toContain("Unbekannt")
  })
})