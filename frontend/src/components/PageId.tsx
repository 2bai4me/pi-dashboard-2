/**
 * PageId-Komponente (User-Direktive 24.06.2026)
 *
 * Zeigt eine eineindeutige Seiten-ID unterhalb des Seitentitels an.
 * Klick auf die ID kopiert sie in die Zwischenablage.
 *
 * Verwendung:
 *   <h1>Kanban-Board</h1>
 *   <PageId id="PG-001-KANBAN" />
 *
 * Format-Konvention: PG-<NNN>-<KATEGORIE>
 *   PG-001 = Kanban-Board
 *   PG-002 = SOPs
 *   PG-003 = Cost/Performance
 *   ...
 *
 * Diese IDs sollen auch in der Dokumentation und im Code verwendet werden,
 * um schnell die richtige Stelle zu finden.
 */
import { useState } from "react"
import { Hash, Copy, Check } from "lucide-react"

interface PageIdProps {
  id: string
}

export function PageId({ id }: PageIdProps) {
  const [copied, setCopied] = useState(false)

  async function copyToClipboard() {
    try {
      await navigator.clipboard.writeText(id)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch (e) {
      // Fallback: select + execCommand
      const ta = document.createElement("textarea")
      ta.value = id
      document.body.appendChild(ta)
      ta.select()
      document.execCommand("copy")
      document.body.removeChild(ta)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <div
      onClick={copyToClipboard}
      title={`Klicken zum Kopieren: ${id}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        margin: "2px 0 8px 0",
        background: copied ? "rgba(46, 160, 67, 0.15)" : "rgba(124, 58, 237, 0.08)",
        border: `1px solid ${copied ? "var(--color-hermes-accent)" : "rgba(124, 58, 237, 0.3)"}`,
        borderRadius: 4,
        cursor: "pointer",
        userSelect: "none",
        fontSize: 10,
        fontFamily: "var(--font-mono)",
        color: copied ? "var(--color-hermes-accent)" : "var(--color-hermes-text-secondary)",
        transition: "all 0.15s",
        fontWeight: 500,
        letterSpacing: "0.3px",
      }}
    >
      {copied ? (
        <Check size={10} />
      ) : (
        <Hash size={10} />
      )}
      <span style={{ fontWeight: 600 }}>{id}</span>
      <span style={{ marginLeft: 4, opacity: 0.6 }}>
        {copied ? "✓ kopiert!" : <Copy size={9} />}
      </span>
    </div>
  )
}
