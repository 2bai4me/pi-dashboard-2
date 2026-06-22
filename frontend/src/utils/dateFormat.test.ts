/**
 * Tests fuer dateFormat-Utility (Task 13b322a2b926).
 *
 * User-Direktive 22.06.2026: "Alter des Eintrags sichtbar" — kompakte
 * Darstellung + ausfuehrliche Variante + Farbcode.
 */

import { describe, it, expect } from "vitest"
import {
  formatAge,
  ageColor,
  formatRelativeTime,
  formatTimestampDE,
  formatTimestampDEFull,
  diffSeconds,
  AGE_THRESHOLDS,
} from "./dateFormat"

// Fixes "now" fuer deterministische Tests: 2026-06-22 16:00:00 UTC
const NOW_MS = Date.UTC(2026, 5, 22, 16, 0, 0) // Monat 5 = Juni (0-indexed)

function iso(secondsAgo: number): string {
  return new Date(NOW_MS - secondsAgo * 1000).toISOString()
}

describe("diffSeconds", () => {
  it("gibt 0 fuer leeren String", () => {
    expect(diffSeconds("", NOW_MS)).toBe(0)
  })

  it("gibt 0 fuer null/undefined", () => {
    expect(diffSeconds(null, NOW_MS)).toBe(0)
    expect(diffSeconds(undefined, NOW_MS)).toBe(0)
  })

  it("gibt 0 fuer ungueltigen ISO-String", () => {
    expect(diffSeconds("not-a-date", NOW_MS)).toBe(0)
  })

  it("berechnet Sekunden-Differenz korrekt", () => {
    expect(diffSeconds(iso(0), NOW_MS)).toBe(0)
    expect(diffSeconds(iso(60), NOW_MS)).toBe(60)
    expect(diffSeconds(iso(3600), NOW_MS)).toBe(3600)
  })

  it("clampt negative Diffs (Zukunft) auf 0", () => {
    expect(diffSeconds(iso(-100), NOW_MS)).toBe(0)
  })
})

describe("formatAge", () => {
  it("gibt em-dash fuer leeren Wert", () => {
    expect(formatAge("", NOW_MS)).toBe("—")
    expect(formatAge(null, NOW_MS)).toBe("—")
  })

  it("formatiert Sekunden", () => {
    expect(formatAge(iso(0), NOW_MS)).toBe("0s")
    expect(formatAge(iso(30), NOW_MS)).toBe("30s")
    expect(formatAge(iso(59), NOW_MS)).toBe("59s")
  })

  it("formatiert Minuten", () => {
    expect(formatAge(iso(60), NOW_MS)).toBe("1m")
    expect(formatAge(iso(60 * 5), NOW_MS)).toBe("5m")
    expect(formatAge(iso(60 * 59), NOW_MS)).toBe("59m")
  })

  it("formatiert Stunden", () => {
    expect(formatAge(iso(3600), NOW_MS)).toBe("1h")
    expect(formatAge(iso(3600 * 2), NOW_MS)).toBe("2h")
    expect(formatAge(iso(3600 * 23), NOW_MS)).toBe("23h")
  })

  it("formatiert Tage (< 7)", () => {
    expect(formatAge(iso(86400), NOW_MS)).toBe("1d")
    expect(formatAge(iso(86400 * 3), NOW_MS)).toBe("3d")
    expect(formatAge(iso(86400 * 6), NOW_MS)).toBe("6d")
  })

  it("formatiert Wochen (< 5)", () => {
    expect(formatAge(iso(86400 * 7), NOW_MS)).toBe("1w")
    expect(formatAge(iso(86400 * 14), NOW_MS)).toBe("2w")
    expect(formatAge(iso(86400 * 28), NOW_MS)).toBe("4w")
  })

  it("formatiert Monate (< 12)", () => {
    expect(formatAge(iso(86400 * 35), NOW_MS)).toBe("1mo") // 35d ~ 1mo
    expect(formatAge(iso(86400 * 60), NOW_MS)).toBe("2mo")
    expect(formatAge(iso(86400 * 330), NOW_MS)).toBe("11mo")
  })

  it("formatiert Jahre", () => {
    expect(formatAge(iso(86400 * 365), NOW_MS)).toBe("1y")
    expect(formatAge(iso(86400 * 730), NOW_MS)).toBe("2y")
  })
})

describe("ageColor", () => {
  it("gibt Text-Secondary fuer leeren Wert", () => {
    expect(ageColor("", NOW_MS)).toContain("text-secondary")
  })

  it("gibt Accent (gruen) fuer < 1h", () => {
    expect(ageColor(iso(0), NOW_MS)).toContain("accent")
    expect(ageColor(iso(AGE_THRESHOLDS.FRESH - 1), NOW_MS)).not.toContain("danger")
  })

  it("gibt Acccent-Blue fuer < 24h", () => {
    expect(ageColor(iso(AGE_THRESHOLDS.FRESH), NOW_MS)).toContain("accent-blue")
    expect(ageColor(iso(AGE_THRESHOLDS.TODAY - 1), NOW_MS)).toContain("accent-blue")
  })

  it("gibt Accent-Orange fuer < 7d", () => {
    expect(ageColor(iso(AGE_THRESHOLDS.TODAY), NOW_MS)).toContain("accent-orange")
    expect(ageColor(iso(AGE_THRESHOLDS.THIS_WEEK - 1), NOW_MS)).toContain("accent-orange")
  })

  it("gibt Danger (rot) fuer >= 7d", () => {
    expect(ageColor(iso(AGE_THRESHOLDS.THIS_WEEK), NOW_MS)).toContain("danger")
    expect(ageColor(iso(86400 * 30), NOW_MS)).toContain("danger")
  })
})

describe("formatRelativeTime", () => {
  it("gibt em-dash fuer leeren Wert", () => {
    expect(formatRelativeTime("", NOW_MS)).toBe("—")
    expect(formatRelativeTime(null, NOW_MS)).toBe("—")
  })

  it("formatiert 'gerade eben' fuer < 30s", () => {
    expect(formatRelativeTime(iso(0), NOW_MS)).toBe("gerade eben")
    expect(formatRelativeTime(iso(15), NOW_MS)).toBe("gerade eben")
  })

  it("formatiert Minuten mit Einzahl/Mehrzahl", () => {
    expect(formatRelativeTime(iso(60), NOW_MS)).toBe("vor 1 Minute")
    expect(formatRelativeTime(iso(60 * 5), NOW_MS)).toBe("vor 5 Minuten")
    expect(formatRelativeTime(iso(60 * 59), NOW_MS)).toBe("vor 59 Minuten")
  })

  it("formatiert Stunden", () => {
    expect(formatRelativeTime(iso(3600), NOW_MS)).toBe("vor 1 Stunde")
    expect(formatRelativeTime(iso(3600 * 2), NOW_MS)).toBe("vor 2 Stunden")
  })

  it("formatiert Tage", () => {
    expect(formatRelativeTime(iso(86400), NOW_MS)).toBe("vor 1 Tag")
    expect(formatRelativeTime(iso(86400 * 3), NOW_MS)).toBe("vor 3 Tagen")
  })

  it("formatiert Wochen", () => {
    expect(formatRelativeTime(iso(86400 * 7), NOW_MS)).toBe("vor 1 Woche")
    expect(formatRelativeTime(iso(86400 * 14), NOW_MS)).toBe("vor 2 Wochen")
  })

  it("formatiert Monate", () => {
    expect(formatRelativeTime(iso(86400 * 35), NOW_MS)).toBe("vor 1 Monat")
    expect(formatRelativeTime(iso(86400 * 90), NOW_MS)).toBe("vor 3 Monaten")
  })

  it("formatiert Jahre", () => {
    expect(formatRelativeTime(iso(86400 * 365), NOW_MS)).toBe("vor 1 Jahr")
    expect(formatRelativeTime(iso(86400 * 730), NOW_MS)).toBe("vor 2 Jahren")
  })

  it("erkennt Zukunfts-Timestamps (Clock-Skew)", () => {
    expect(formatRelativeTime(iso(-100), NOW_MS)).toBe("in der Zukunft")
  })
})

describe("formatTimestampDE", () => {
  it("gibt em-dash fuer leeren Wert", () => {
    expect(formatTimestampDE("")).toBe("—")
    expect(formatTimestampDE(null)).toBe("—")
  })

  it("gibt em-dash fuer ungueltigen Wert", () => {
    expect(formatTimestampDE("not-a-date")).toBe("—")
  })

  it("formatiert deutsches Locale dd.mm.yyyy hh:mm", () => {
    // 2026-06-22 16:00:00 UTC
    const result = formatTimestampDE("2026-06-22T16:00:00.000Z")
    // de-DE toLocaleString gibt "22.06.2026, 18:00" (Komma zwischen Datum + Zeit)
    expect(result).toMatch(/^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}$/)
  })
})

describe("formatTimestampDEFull", () => {
  it("enthaelt Sekunden", () => {
    const result = formatTimestampDEFull("2026-06-22T16:00:30.000Z")
    expect(result).toMatch(/^\d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}:\d{2}$/)
  })

  it("gibt em-dash fuer leeren Wert", () => {
    expect(formatTimestampDEFull("")).toBe("—")
  })
})

describe("AGE_THRESHOLDS Konsistenz", () => {
  it("Schwellen sind aufsteigend sortiert", () => {
    expect(AGE_THRESHOLDS.FRESH).toBeLessThan(AGE_THRESHOLDS.TODAY)
    expect(AGE_THRESHOLDS.TODAY).toBeLessThan(AGE_THRESHOLDS.THIS_WEEK)
  })

  it("Schwellen entsprechen den Erwartungen (3600/86400/604800)", () => {
    expect(AGE_THRESHOLDS.FRESH).toBe(3600)
    expect(AGE_THRESHOLDS.TODAY).toBe(86400)
    expect(AGE_THRESHOLDS.THIS_WEEK).toBe(604800)
  })
})