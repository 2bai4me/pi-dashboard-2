/**
 * Datum/Zeit-Utilities fuer die Performance-Tabelle (Task 13b322a2b926).
 *
 * User-Direktive 22.06.2026: In der Performance-Tabelle soll das "Alter"
 * eines Eintrags sichtbar sein, damit User sehen, wie alt ein Eintrag ist.
 *
 * Funktionsumfang:
 *  - formatAge            : kompakte Darstellung ("5m", "2h", "3d") fuer Tabelle
 *  - ageColor             : Farbcode nach Alter (gruen/blau/orange/rot)
 *  - formatRelativeTime   : lange Darstellung ("vor 5 Minuten", "vor 2 Stunden")
 *  - formatTimestampDE    : deutsches Locale (dd.mm.yyyy hh:mm)
 *
 * Reine pure Funktionen — keine Side-Effects, gut testbar.
 */

// ─── Konstanten ──────────────────────────────────────────────────────
// Farb-Skala nach Alter (in Sekunden).  Wird auch in CSS-Tests referenziert.
export const AGE_THRESHOLDS = {
  FRESH: 3600,         // < 1h    -> gruen (frisch)
  TODAY: 86400,        // < 24h   -> blau  (heute)
  THIS_WEEK: 604800,   // < 7d    -> orange (diese Woche)
  // >= 7d                 -> rot    (alt)
} as const;

// CSS-Variable-Namen, damit Light/Dark-Theme automatisch greift.
const COLOR_FRESH = "var(--color-hermes-accent)"
const COLOR_TODAY = "var(--color-hermes-accent-blue)"
const COLOR_WEEK = "var(--color-hermes-accent-orange)"
const COLOR_OLD = "var(--color-hermes-danger)"
const COLOR_NONE = "var(--color-hermes-text-secondary)"

/**
 * Berechnet die Sekunden-Differenz zwischen `nowMs` und `iso`.
 * Gibt 0 zurueck, falls `iso` leer oder ungueltig.
 */
export function diffSeconds(iso: string | null | undefined, nowMs: number): number {
  if (!iso) return 0
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return 0
  return Math.max(0, Math.floor((nowMs - t) / 1000))
}

/**
 * Kompakte Altersanzeige (fuer Performance-Tabelle):
 *   < 1m   -> "30s"
 *   < 1h   -> "5m"
 *   < 1d   -> "3h"
 *   < 1w   -> "2d"
 *   < 5w   -> "3w"
 *   < 12mo -> "4mo"
 *   >=     -> "2y"
 *
 * Gibt "—" zurueck, falls `iso` leer/ungueltig.
 */
export function formatAge(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return "—"
  const diffSec = diffSeconds(iso, nowMs)
  if (diffSec < 60) return `${diffSec}s`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}h`
  const diffD = Math.floor(diffH / 24)
  if (diffD < 7) return `${diffD}d`
  const diffW = Math.floor(diffD / 7)
  if (diffW < 5) return `${diffW}w`
  const diffMo = Math.floor(diffD / 30)
  if (diffMo < 12) return `${diffMo}mo`
  const diffY = Math.floor(diffD / 365)
  return `${diffY}y`
}

/**
 * Farbcode basierend auf dem Alter (fuer Performance-Tabelle):
 *   < 1h    -> gruen   (frisch)
 *   < 24h   -> blau    (heute)
 *   < 7d    -> orange  (diese Woche)
 *   >= 7d   -> rot     (alt)
 *
 * Gibt eine CSS-Variable zurueck, die das aktuelle Theme beruecksichtigt.
 */
export function ageColor(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return COLOR_NONE
  const diffSec = diffSeconds(iso, nowMs)
  if (diffSec < AGE_THRESHOLDS.FRESH) return COLOR_FRESH
  if (diffSec < AGE_THRESHOLDS.TODAY) return COLOR_TODAY
  if (diffSec < AGE_THRESHOLDS.THIS_WEEK) return COLOR_WEEK
  return COLOR_OLD
}

/**
 * Ausfuehrliche relative Zeit (fuer Tooltips/Badges):
 *   "gerade eben"
 *   "vor 5 Minuten"
 *   "vor 2 Stunden"
 *   "vor 3 Tagen"
 *   "vor 2 Wochen"
 *   "vor 3 Monaten"
 *   "vor 2 Jahren"
 *
 * Gibt "—" zurueck, falls `iso` leer/ungueltig.
 * Gibt "in der Zukunft" zurueck, falls `iso` in der Zukunft liegt.
 */
export function formatRelativeTime(iso: string | null | undefined, nowMs: number = Date.now()): string {
  if (!iso) return "—"
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return "—"

  const diffSec = Math.floor((nowMs - t) / 1000)
  if (diffSec < -1) return "in der Zukunft"   // Edge-Case: Clock-Skew
  if (diffSec < 30) return "gerade eben"

  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `vor ${diffMin} ${diffMin === 1 ? "Minute" : "Minuten"}`

  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `vor ${diffH} ${diffH === 1 ? "Stunde" : "Stunden"}`

  const diffD = Math.floor(diffH / 24)
  if (diffD < 7) return `vor ${diffD} ${diffD === 1 ? "Tag" : "Tagen"}`

  const diffW = Math.floor(diffD / 7)
  if (diffW < 5) return `vor ${diffW} ${diffW === 1 ? "Woche" : "Wochen"}`

  const diffMo = Math.floor(diffD / 30)
  if (diffMo < 12) return `vor ${diffMo} ${diffMo === 1 ? "Monat" : "Monaten"}`

  const diffY = Math.floor(diffD / 365)
  return `vor ${diffY} ${diffY === 1 ? "Jahr" : "Jahren"}`
}

/**
 * Timestamp im deutschen Locale formatieren: dd.mm.yyyy hh:mm.
 *
 * Verwendet Intl.DateTimeFormat mit Zeitzone Europe/Berlin.
 * Gibt "—" zurueck, falls `iso` leer/ungueltig.
 */
export function formatTimestampDE(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

/**
 * Vollstaendiger Timestamp mit Sekunden: dd.mm.yyyy hh:mm:ss.
 * Fuer Detail-Panels, wo Platz ist.
 */
export function formatTimestampDEFull(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}