import { Key } from "lucide-react"

export default function ApiKeys() {
  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Key size={22} color="var(--color-hermes-accent-blue)" />
          <h1 style={{ margin: 0 }}>API Keys</h1>
        </div>
        <p>API-Keys fuer externe Provider (minimax, OpenRouter, etc.)</p>
      </div>
      <div className="card">
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          API-Key-Management folgt in v2.1. Aktuell werden Keys in
          <code style={{ marginLeft: 4, padding: "1px 4px", background: "var(--color-hermes-muted)", borderRadius: 3 }}>
            ~/.pi/agent/models.json
          </code>{" "}
          verwaltet.
        </p>
      </div>
    </div>
  )
}
