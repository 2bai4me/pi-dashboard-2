import { Link } from "react-router-dom"
import { Key, Bot } from "lucide-react"

export default function Config() {
  return (
    <div>
      <div className="page-header">
        <h1>Config</h1>
        <p>Konfiguration</p>
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ margin: 0, color: "var(--color-hermes-text-secondary)" }}>
          Verwalte API-Keys und Sub-Agent-Provider-Zuordnungen.
        </p>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <Link to="/api-keys" className="btn btn-primary">
          <Key size={16} /> API-Keys verwalten
        </Link>
        <Link to="/subagents" className="btn btn-primary">
          <Bot size={16} /> Sub-Agenten konfigurieren
        </Link>
      </div>
    </div>
  )
}
