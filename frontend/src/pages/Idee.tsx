// Idee.tsx — Neue Seite "Idee" (Brainstorming + Requirements, ehemals in Projekte)
// User-Direktive 23.06.2026: Brainstorming und Requirements aus Projekte-Ansicht
// herausgeloest und in eigene "Idee"-Seite verschoben.

import { useState } from "react"
import { Sparkles, ClipboardList, Lightbulb } from "lucide-react"
import { useSearchParams } from "react-router-dom"

type IdeeTab = "brainstorm" | "requirements"

export default function Idee() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialTab = (searchParams.get("tab") as IdeeTab) || "brainstorm"
  const [tab, setTab] = useState<IdeeTab>(initialTab)

  function setTabAndUrl(t: IdeeTab) {
    setTab(t)
    setSearchParams({ tab: t })
  }

  return (
    <div>
      <div className="page-header">
        <div className="workspace-header">
          <Lightbulb size={20} color="var(--color-hermes-accent)" />
          <h1>Idee</h1>
        </div>
        <p>Brainstorming & Requirements — der kreative Bereich vor der Umsetzung.</p>
      </div>

      <div className="subtab-bar">
        <button
          className={`subtab ${tab === "brainstorm" ? "active" : ""}`}
          onClick={() => setTabAndUrl("brainstorm")}
        >
          <Sparkles size={14} /> Brainstorm
        </button>
        <button
          className={`subtab ${tab === "requirements" ? "active" : ""}`}
          onClick={() => setTabAndUrl("requirements")}
        >
          <ClipboardList size={14} /> Requirements
        </button>
      </div>

      <div style={{ padding: "12px 0", color: "var(--color-hermes-text-secondary)", fontSize: 12 }}>
        Hinweis: Brainstorm- und Requirements-Inhalte werden projektuebergreifend
        angezeigt. Wechsel in ein konkretes Projekt fuer projektspezifische Inhalte.
      </div>
    </div>
  )
}